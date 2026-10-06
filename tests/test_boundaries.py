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
