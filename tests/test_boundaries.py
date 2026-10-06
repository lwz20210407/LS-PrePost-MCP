import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings, command_path
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.jobs import check_artifact
from ls_prepost_mcp.service import Service


def test_path_and_include_boundary(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    external = tmp_path / "private.k"
    external.write_text("*KEYWORD\n*END")
    settings = Settings(allowed)
    with pytest.raises(ValueError, match="outside"):
        settings.input_path(str(external))
    model = allowed / "model.k"
    model.write_text("*KEYWORD\n*INCLUDE\n../private.k\n*END")
    with pytest.raises(ValueError, match="outside"):
        settings.check_keyword_includes(model)
    model.write_text("*KEYWORD\n*INCLUDE\nmodel.k\n*END")
    with pytest.raises(ValueError, match="Cyclic"):
        settings.check_keyword_includes(model)


def test_keyword_relative_includes(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "part.k").write_text("*KEYWORD\n*END")
    model = root / "model.k"
    model.write_text("*KEYWORD\n*INCLUDE\npart.k\n*END")
    Settings(root).check_keyword_includes(model)


def test_command_path_rejects_newlines():
    with pytest.raises(ValueError):
        command_path(Path('bad\nexit'))
    with pytest.raises(ValueError):
        command_path(Path('bad"name'))


@pytest.mark.parametrize("params", [
    {"nx": True, "ny": 2, "size": [1, 1], "units": "mm"},
    {"nx": 500, "ny": 500, "size": [1, 1], "units": "mm"},
    {"nx": 2, "ny": 2, "size": [float('nan'), 1], "units": "mm"},
    {"nx": 2, "ny": 2, "size": [1, 1], "units": ""},
])
def test_mesh_validation_before_native_launch(tmp_path, params):
    with pytest.raises(ValueError):
        Service(Settings(tmp_path)).create_shell_plate(**params)
    assert not (tmp_path / "jobs").exists()


def test_artifact_not_just_nonempty(tmp_path):
    image = tmp_path / "fake.png"
    image.write_text("this is not an image")
    with pytest.raises(Exception):
        check_artifact(image, "png")
    curve = tmp_path / "curve.csv"
    curve.write_text("time,value\n0,nan\n")
    with pytest.raises(ValueError, match="nonfinite"):
        check_artifact(curve, "csv")
    curve.write_text("time,value\n")
    with pytest.raises(ValueError, match="no data"):
        check_artifact(curve, "csv")


def test_old_output_never_satisfies_new_job(tmp_path, monkeypatch):
    old = tmp_path / "model.k"
    old.write_text("*KEYWORD\n*END")
    def fake(exe, cfile, directory, **kwargs):
        request = json.loads((directory / "request.json").read_text())
        (directory / "response.json").write_text(json.dumps({"job_id": request["job_id"], "ok": True, "data": {}}))
        return JobResult(operation=kwargs["operation"], job_id=directory.name, status="unverified", data=dict(returncode=0, timed_out=False))
    monkeypatch.setattr("ls_prepost_mcp.service.run_batch", fake)
    service = Service(Settings(tmp_path, old))
    result = service.export_keyword(str(old))
    assert result["status"] == "failed"
    assert "Missing" in result["error"]["message"]
    assert old.read_text() == "*KEYWORD\n*END"


def test_native_exit_zero_without_response_fails(tmp_path, monkeypatch):
    exe = tmp_path / "fake"
    exe.touch()
    monkeypatch.setattr("ls_prepost_mcp.service.run_batch", lambda *a, **k: JobResult(operation=k["operation"], job_id=a[2].name, status="unverified", data=dict(returncode=0, timed_out=False)))
    result = Service(Settings(tmp_path, exe)).probe_environment()
    assert result["status"] == "failed"
    assert "no response" in result["error"]["message"]


def test_response_is_bound_to_job(tmp_path, monkeypatch):
    exe = tmp_path / "fake"
    exe.touch()
    def fake(exe, cfile, directory, **kwargs):
        (directory / "response.json").write_text(json.dumps({"job_id": "stale", "ok": True, "data": {}}))
        return JobResult(operation=kwargs["operation"], job_id=directory.name, status="unverified", data=dict(returncode=0, timed_out=False))
    monkeypatch.setattr("ls_prepost_mcp.service.run_batch", fake)
    result = Service(Settings(tmp_path, exe)).probe_environment()
    assert result["status"] == "failed"
    assert "different job" in result["error"]["message"]


def test_include_export_refused_before_any_write(tmp_path):
    child = tmp_path / "part.k"
    child.write_text("*KEYWORD\n*END")
    model = tmp_path / "main.k"
    model.write_text("*KEYWORD\n*INCLUDE\npart.k\n*END")
    with pytest.raises(ValueError, match="staged include"):
        Service(Settings(tmp_path, model)).export_keyword(str(model))
    assert not (tmp_path / "jobs").exists()


def test_mpp_shards_are_not_silently_partially_read(tmp_path):
    (tmp_path / "binout0000").write_bytes(b"one")
    (tmp_path / "binout0001").write_bytes(b"two")
    with pytest.raises(ValueError, match="MPP"):
        Service(Settings(tmp_path)).inspect_binout(str(tmp_path / "binout0000"))


def test_version_dispatch_preserves_global_selection(tmp_path, monkeypatch):
    default = tmp_path / "default.exe"
    alternate = tmp_path / "alternate.exe"
    settings = Settings(tmp_path, default, profiles={"4.8": alternate})
    selected = []
    def fake(self, *args, **kw):
        selected.append(self.settings.executable)
        return {"status": "succeeded"}
    monkeypatch.setattr(Service, "_native", fake)
    service = Service(settings)
    result = service.run_on_version("4.8", "probe_environment", {})
    assert result["installation_profile"] == "4.8"
    assert selected == [alternate]
    assert settings.executable == default
    with pytest.raises(ValueError):
        service.run_on_version("4.8", "__getattribute__", {})


@pytest.mark.parametrize("second", ["../private.k", "missing.k"])
def test_every_include_filename_card_is_checked(tmp_path, second):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (tmp_path / "private.k").write_text("*KEYWORD\n*END\n")
    (allowed / "first.k").write_text("*KEYWORD\n*END\n")
    model = allowed / "main.k"
    model.write_text("*KEYWORD\n*INCLUDE\nfirst.k\n" + second + "\n*END\n")
    with pytest.raises(ValueError, match="outside|missing.*main.k.*name_line=4"):
        Settings(allowed).check_keyword_includes(model)


@pytest.mark.parametrize("name,message", [
    ("&name.k", "Parameterized"), ("%name%.k", "Parameterized"),
    ("//invalid-host/share/deck.k", "network_path"),
])
def test_later_include_policy_and_network_rejection(tmp_path, name, message):
    (tmp_path / "first.k").write_text("*KEYWORD\n*END\n")
    model = tmp_path / "main.k"
    model.write_text("*KEYWORD\n*INCLUDE\nfirst.k\n" + name + "\n*END\n")
    with pytest.raises(ValueError, match=message):
        Settings(tmp_path).check_keyword_includes(model)


@pytest.mark.parametrize("keyword", ["*INCLUDE_TRANSFORM", "*INCLUDE_PATH", "*INCLUDE_BINARY"])
def test_preflight_does_not_expand_native_include_policy(tmp_path, keyword):
    (tmp_path / "child.k").write_text("*KEYWORD\n*END\n")
    model = tmp_path / "main.k"
    model.write_text("*KEYWORD\n" + keyword + "\nchild.k\n*END\n")
    with pytest.raises(ValueError, match="Only plain"):
        Settings(tmp_path).check_keyword_includes(model)


def test_unselected_preflight_candidate_must_be_allowed(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain import model as api
    root = tmp_path / "allowed"
    root.mkdir()
    main = root / "main.k"
    main.write_text("*KEYWORD\n*INCLUDE\nchild.k\n*END\n")
    (root / "child.k").write_text("*KEYWORD\n*END\n")
    outside = tmp_path / "outside.k"
    outside.write_text("*KEYWORD\n*END\n")
    report = api.preflight_includes(main)
    report["references"][0]["candidates"].append(str(outside))
    monkeypatch.setattr(api, "preflight_includes", lambda source: report)
    with pytest.raises(ValueError, match="outside"):
        Settings(root).check_keyword_includes(main)


@pytest.mark.parametrize("allowed_alternate", [False, True])
def test_native_cwd_alternative_cannot_bypass_preflight(tmp_path, allowed_alternate):
    root = tmp_path / "source"
    root.mkdir()
    cwd = tmp_path / "job"
    cwd.mkdir()
    main = root / "main.k"
    main.write_text("*KEYWORD\n*INCLUDE\nchild.k\n*END\n")
    (root / "child.k").write_text("*KEYWORD\n*END\n")
    (cwd / "child.k").write_text("*KEYWORD\n*INCLUDE\nprivate.k\n*END\n")
    settings = Settings(root, allowed_roots=(cwd,) if allowed_alternate else ())
    with pytest.raises(ValueError, match="outside|different file"):
        settings.check_keyword_includes(main, native_cwd=cwd)


@pytest.mark.parametrize("keyword,name", [("*INCLUDE_TRANSFORM", "missing.k"), ("*INCLUDE", "%missing%.k")])
def test_policy_failure_keeps_first_preflight_error_location(tmp_path, keyword, name):
    main = tmp_path / "main.k"
    main.write_text("*KEYWORD\n" + keyword + "\n" + name + "\n*END\n")
    with pytest.raises(ValueError, match="kind=missing, relative=main.k, name_line=3, reason=not_found"):
        Settings(tmp_path).check_keyword_includes(main)
