"""Original installation fixtures only; never read a real vendor installation."""

import json
import shutil
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.jobs import fingerprint
from ls_prepost_mcp.service import Service

TEMPLATE = "*KEYWORD\n*PARAMETER_EXPRESSION\nRT, 10\nRDOUBLE, T*2\n*CONTROL_TERMINATION\n&T\n*END\n"
MODEL = "*KEYWORD\n*MAT_001_TITLE\nOriginal\n1,1,100,.3\n*END\n"


@pytest.fixture
def installed(tmp_path, monkeypatch):
    root = tmp_path / "installation"
    template = root / "kwtemplate" / "Original Control" / "template.k"
    template.parent.mkdir(parents=True)
    template.write_text(TEMPLATE, encoding="utf8")
    filters = root / "kwfilter"
    filters.mkdir()
    (filters / "Original Materials.txt").write_text("*MAT_001\n", encoding="utf8")
    monkeypatch.setenv("LSPP_TEMPLATE_ROOT", str(root))
    workspace = tmp_path / "work"
    workspace.mkdir()
    model = workspace / "input.k"
    model.write_text(MODEL, encoding="utf8")
    service = Service(Settings(workspace))
    monkeypatch.setattr(service, "inspect_model", lambda *a, **kw: pytest.fail("unexpected native reopen"))
    monkeypatch.setattr(Settings, "native_executable", lambda *a: pytest.fail("unexpected native probe"))
    return service, root, model


def test_installation_discovery_gap(installed):
    service, _, _ = installed
    assets = service.list_installation_assets()
    assert len(assets["templates"]) == len(assets["filters"]) == 1
    found = service.find_recipe("Original", include_candidates=True)
    assert {row["resource"]["id"] for row in found} == {
        row["id"] for group in assets.values() for row in group
    }
    assert all(row["reference"].startswith("installed:") for row in found)


def test_installation_execution_gap_and_legacy_equivalence(installed):
    service, _, model = installed
    asset = service.list_installation_assets()["templates"][0]
    old = service.instantiate_installed_template(asset["id"], {"T": 20}, "test", native_check=False)
    assert old["status"] == "succeeded"
    # The direct ID route resolves the current resource; discovery also pins its content.
    result = service.run_recipe("installed:" + asset["id"], {"values": {"T": 20}, "units": "test"})
    JobResult.model_validate(result)
    assert result["status"] == "succeeded"
    assert result["data"]["parameters"] == old["data"]["parameters"] == {"T": 20, "DOUBLE": 40}
    assert Path(result["artifacts"][0]["path"]).read_bytes() == Path(old["artifacts"][0]["path"]).read_bytes()
    filter_id = service.list_installation_assets()["filters"][0]["id"]
    old_filter = service.apply_keyword_filter(str(model), filter_id)
    selected = service.run_recipe("installed:" + filter_id, model=str(model))
    assert selected["status"] == "succeeded"
    assert selected["data"]["matches"] == old_filter["matches"] == [{"block_index": 1, "keyword": "*MAT_001_TITLE"}]
    assert model.read_text(encoding="utf8") == MODEL


def row_for(service, kind):
    return next(row for row in service.find_recipe(include_candidates=True)
                if row.get("adapter_kind") == "installed_" + kind)


def test_discovery_schema_filters_defaults_and_all_catalog_items(installed):
    service, root, _ = installed
    for index in range(6):
        folder = root / "kwtemplate" / f"extra-{index}"
        folder.mkdir()
        (folder / "template.k").write_text(TEMPLATE, encoding="utf8")
    original = row_for(service, "template")
    assert original["channel"] is None and original["tier"] == "candidate"
    assert original["versions_verified"] == [] and original["l2_case"] is None
    values = original["parameters"]["properties"]["values"]
    assert values["properties"]["DOUBLE"]["expression"] == "T*2"
    assert values["properties"]["DOUBLE"]["default"] == 20
    assert original["parameters"]["properties"]["native_check"]["default"] is False
    assert len(service.find_recipe()) == 5
    all_rows = service.find_recipe(task_id="A08", include_candidates=True, limit=50)
    assert len(all_rows) == 13
    assert not service.find_recipe("installed", task_id="A01", include_candidates=True)
    for channel in ("cfile", "scl", "python", "command"):
        assert not service.find_recipe("installed", channel=channel, include_candidates=True)
    assert service.find_recipe("安装 模板", include_candidates=True)
    assert service.find_recipe(include_candidates=True, limit=2) == all_rows[:2]
    assert row_for(service, "template")["reference"] == original["reference"]
    assert not service.jobs.root.exists()


def test_no_installation_keeps_bundled_and_legacy_queries(tmp_path, monkeypatch):
    monkeypatch.delenv("LSPP_TEMPLATE_ROOT", raising=False)
    monkeypatch.setattr(Settings, "native_executable", lambda *a: pytest.fail("must not probe"))
    service = Service(Settings(tmp_path))
    assert len(service.find_recipe()) == 5
    with pytest.warns(RuntimeWarning, match="not configured"):
        assert len(service.find_recipe(include_candidates=True)) == 5
    old = service.create_native_macro("legacy", "cfile", "mesh {{width}}", {"width": 2})
    with pytest.warns(RuntimeWarning, match="not configured"):
        assert service.find_recipe("legacy", include_candidates=True)[0]["reference"] == old["artifacts"][0]["path"]
    monkeypatch.setenv("LSPP_TEMPLATE_ROOT", str(tmp_path / "absent"))
    with pytest.warns(RuntimeWarning, match="no supported catalog paths"):
        assert len(service.find_recipe(include_candidates=True)) == 6


@pytest.mark.parametrize("parameters", [
    {}, {"units": ""}, {"units": " "}, {"units": 12}, {"units": "x" * 101},
    {"units": "test", "unknown": 1}, {"units": "test", "native_check": 1},
    {"units": "test", "native_check": "false"}, {"units": "test", "values": []},
    {"units": "test", "values": {1: 2}}, {"units": "test", "values": {"UNKNOWN": 2}},
    {"units": "test", "values": {"T": True}}, {"units": "test", "values": {"T": "1"}},
    {"units": "test", "values": {"T": float("nan")}},
    {"units": "test", "values": {"T": float("inf")}},
    {"units": "test", "values": {"T": 1, "t": 2}}, [],
])
def test_bad_template_parameters_have_no_side_effects(installed, parameters):
    service, _, _ = installed
    reference = row_for(service, "template")["reference"]
    with pytest.raises(ValueError):
        service.run_recipe(reference, parameters)
    assert not service.jobs.root.exists()


@pytest.mark.parametrize("context", [dict(session_id=""), dict(session_id="owned"),
                                    dict(launch_mode="runc"), dict(file_type="d3plot")])
@pytest.mark.parametrize("kind", ["template", "filter"])
def test_unsupported_contexts_reject_before_work(installed, kind, context):
    service, _, model = installed
    reference = row_for(service, kind)["reference"]
    with pytest.raises(ValueError, match="keyword input"):
        service.run_recipe(reference, {"units": "test"} if kind == "template" else {},
                           model=str(model), **context)
    assert not service.jobs.root.exists()


@pytest.mark.parametrize("parameters", [{"units": "test"}, {"values": {}}, {"native_check": False}])
def test_filter_rejects_inapplicable_parameters(installed, parameters):
    service, _, model = installed
    reference = row_for(service, "filter")["reference"]
    with pytest.raises(ValueError):
        service.run_recipe(reference, parameters, model=str(model))
    assert not service.jobs.root.exists()


def test_filter_requires_model_and_enforces_path_boundary(installed, tmp_path):
    service, _, _ = installed
    reference = row_for(service, "filter")["reference"]
    with pytest.raises(ValueError, match="explicit keyword model"):
        service.run_recipe(reference)
    foreign = tmp_path / "outside.k"
    foreign.write_text(MODEL, encoding="utf8")
    with pytest.raises(ValueError, match="allowed roots"):
        service.run_recipe(reference, model=str(foreign))
    assert not service.jobs.root.exists()


@pytest.mark.parametrize("kind", ["template", "filter"])
def test_discovery_reference_detects_changes_and_removal(installed, kind):
    service, _, model = installed
    row = row_for(service, kind)
    path = Path(row["resource"]["path"])
    path.write_text(path.read_text(encoding="utf8") + "$ changed\n", encoding="utf8")
    with pytest.raises(ValueError, match="changed since discovery"):
        service.run_recipe(row["reference"], {"units": "test"} if kind == "template" else {}, model=str(model))
    path.rename(path.with_suffix(".removed"))
    with pytest.raises(ValueError, match="Unknown installation resource"):
        service.run_recipe(row["reference"], {"units": "test"} if kind == "template" else {}, model=str(model))
    assert not service.jobs.root.exists()


@pytest.mark.parametrize("content, reason", [
    ("*KEYWORD\n*PARAMETER\nBAD, 1\n*END\n", "Unsupported parameter"),
    ("*KEYWORD\n*PARAMETER_EXPRESSION\nRA, B\nRB, A\n*END\n", "Cyclic"),
    ("*KEYWORD\n*PARAMETER_EXPRESSION\nRA, MISSING\n*END\n", "Unresolved"),
    ('*KEYWORD\n*PARAMETER_EXPRESSION\nRA, __import__("os")\n*END\n', "Unsupported"),
    ("*CONTROL_TERMINATION\n1\n", "KEYWORD/END"),
])
def test_unsupported_assets_remain_visible_with_reason(installed, content, reason):
    service, root, _ = installed
    path = root / "kwtemplate" / "Original Control" / "template.k"
    path.write_text(content, encoding="utf8")
    row = row_for(service, "template")
    assert row["support"] == "unsupported" and reason in row["reason"]
    with pytest.raises(ValueError, match=reason):
        service.run_recipe(row["reference"], {"units": "test"})
    assert not service.jobs.root.exists()


def test_units_and_source_artifact_identities_are_persisted(installed):
    service, _, model = installed
    before = fingerprint(model)
    for kind in ("template", "filter"):
        row = row_for(service, kind)
        result = service.run_recipe(row["reference"], {"units": "mm-ms", "values": {"t": 3}} if kind == "template" else {},
                                    model=str(model))
        validated = JobResult.model_validate(result)
        assert validated.operation == "run_recipe" and result["status"] == "succeeded"
        data = result["data"]
        assert data["inputs"][-1] == before
        assert data["recipe"]["source"] == fingerprint(Path(row["resource"]["path"]))
        assert data["solver_validated"] is data["native_mesh_verified"] is False
        assert data["recipe"]["versions_verified"] == []
        if kind == "template":
            assert data["recipe"]["parameters"]["units"] == "mm-ms"
            assert data["parameters"] == {"T": 3, "DOUBLE": 6}
        for artifact in result["artifacts"] + result["evidence"]:
            assert artifact["sha256"] == fingerprint(Path(artifact["path"]))["sha256"]
        folder = service.jobs.root / result["job_id"]
        assert json.loads((folder / "recipe-result.json").read_text(encoding="utf8")) == result
        if kind == "filter":
            saved = json.loads((folder / "filter-result.json").read_text(encoding="utf8"))
            assert saved["matches"] == data["matches"] and saved["model_modified"] is False
            assert saved["filter_source"] == data["recipe"]["source"]
    assert fingerprint(model) == before


def test_fragment_stays_unverified_even_with_native_check(installed):
    service, _, _ = installed
    result = service.run_recipe(row_for(service, "template")["reference"], {"units": "test", "native_check": True})
    assert result["status"] == "succeeded"
    assert result["data"]["native_mesh_verified"] is False
    assert "fragment" in result["data"]["native_check_note"]


@pytest.mark.parametrize("extra", ["*PARAMETER\nRA, 1\n", "*INCLUDE\nchild.k\n"])
def test_merge_restrictions_reuse_old_api_before_job(installed, extra):
    service, _, model = installed
    model.write_text("*KEYWORD\n" + extra + "*END\n", encoding="utf8")
    (model.parent / "child.k").write_text(MODEL, encoding="utf8")
    with pytest.raises(ValueError, match="flattened and parameter-resolved"):
        service.run_recipe(row_for(service, "template")["reference"], {"units": "test"}, model=str(model))
    assert not service.jobs.root.exists()


@pytest.mark.parametrize("kind", ["template", "filter"])
@pytest.mark.parametrize("change", ["resource", "model", "remove"])
def test_changes_during_delegated_execution_cannot_succeed(installed, monkeypatch, kind, change):
    service, _, model = installed
    row = row_for(service, kind)
    path = Path(row["resource"]["path"])
    method = "instantiate_installed_template" if kind == "template" else "apply_keyword_filter"
    original = getattr(service, method)

    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        target = model if change == "model" else path
        if change == "remove":
            target.rename(target.with_suffix(".removed"))
        else:
            target.write_text(target.read_text(encoding="utf8") + "$ changed\n", encoding="utf8")
        return result

    monkeypatch.setattr(service, method, mutate)
    result = service.run_recipe(row["reference"], {"units": "test"} if kind == "template" else {}, model=str(model))
    assert result["status"] == "failed" and result["error"]["message"]
    JobResult.model_validate(result)


def test_native_reopen_delegates_once_and_propagates_failure(installed, monkeypatch):
    service, _, model = installed
    model.write_text("*KEYWORD\n*NODE\n1,0,0,0\n*END\n", encoding="utf8")
    calls = []

    def inspect(path):
        calls.append(path)
        return dict(job_id="native-stub", status="succeeded", data=dict(counts=dict(nodes=1)))

    monkeypatch.setattr(service, "inspect_model", inspect)
    reference = row_for(service, "template")["reference"]
    result = service.run_recipe(reference, {"units": "test", "native_check": True}, model=str(model))
    assert len(calls) == 1 and calls[0] == result["artifacts"][0]["path"]
    assert result["data"]["native_mesh_verified"] is True
    assert result["data"]["solver_validated"] is False
    assert result["data"]["recipe"]["versions_verified"] == []
    monkeypatch.setattr(service, "inspect_model", lambda path: dict(job_id="failed-stub", status="failed", error="original error"))
    result = service.run_recipe(reference, {"units": "test", "native_check": True}, model=str(model))
    assert result["status"] == "failed" and "original error" in result["error"]["message"]


def test_symlink_assets_cannot_escape_installation_root(installed, tmp_path):
    service, root, _ = installed
    outside = tmp_path / "foreign"
    outside.mkdir()
    (outside / "template.k").write_text(TEMPLATE, encoding="utf8")
    link = root / "kwtemplate" / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    assert not any(row.get("resource", {}).get("name") == "escape" for row in service.find_recipe(include_candidates=True))


def test_changed_installation_root_rejects_pinned_content(installed, tmp_path, monkeypatch):
    service, root, _ = installed
    reference = row_for(service, "template")["reference"]
    other = tmp_path / "other-install"
    shutil.copytree(root, other)
    (other / "kwtemplate" / "Original Control" / "template.k").write_text(TEMPLATE.replace("10", "30"), encoding="utf8")
    monkeypatch.setenv("LSPP_TEMPLATE_ROOT", str(other))
    with pytest.raises(ValueError, match="changed since discovery"):
        service.run_recipe(reference, {"units": "test"})
    assert not service.jobs.root.exists()


def test_integer_string_and_computed_values_use_real_declarations(installed):
    service, root, _ = installed
    path = root / "kwtemplate" / "Original Control" / "template.k"
    path.write_text('*KEYWORD\n*PARAMETER\nICOUNT, 2\nSNAME, "original"\n*END\n', encoding="utf8")
    reference = row_for(service, "template")["reference"]
    for values in ({"COUNT": 1.5}, {"COUNT": True}, {"NAME": 3}, {"NAME": "bad\nline"}):
        with pytest.raises(ValueError):
            service.run_recipe(reference, {"units": "test", "values": values})
    assert not service.jobs.root.exists()
    result = service.run_recipe(reference, {"units": "test", "values": {"count": 3.0, "name": "custom"}})
    assert result["data"]["parameters"] == {"COUNT": 3, "NAME": "custom"}


@pytest.mark.parametrize("reference", ["installed:unknown", "installed:template-0000000000000000",
                                        "installed:../template.k", "installed:template-0000000000000000@bad"])
def test_invalid_and_unknown_references_reject_before_job(installed, reference):
    service, _, _ = installed
    with pytest.raises(ValueError):
        service.run_recipe(reference, {"units": "test"})
    assert not service.jobs.root.exists()


def test_source_change_before_legacy_job_capture_is_detected(installed, monkeypatch):
    service, _, _ = installed
    row = row_for(service, "template")
    path = Path(row["resource"]["path"])
    instantiate = service.instantiate_installed_template

    def mutate(*args, **kwargs):
        path.write_text(TEMPLATE.replace("10", "12"), encoding="utf8")
        return instantiate(*args, **kwargs)

    monkeypatch.setattr(service, "instantiate_installed_template", mutate)
    result = service.run_recipe(row["reference"], {"units": "test"})
    assert result["status"] == "failed"


def test_usage_dependency_is_checked_and_cannot_escape(installed, tmp_path):
    service, root, _ = installed
    info = root / "kwtemplate" / "Original Control" / "info.txt"
    info.write_text("Original usage: caller declares units.", encoding="utf8")
    row = row_for(service, "template")
    result = service.run_recipe(row["reference"], {"units": "test"})
    assert result["data"]["inputs"][1] == fingerprint(info)
    info.rename(info.with_suffix(".original"))
    outside = tmp_path / "foreign-info.txt"
    outside.write_text("External usage", encoding="utf8")
    try:
        info.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    row = row_for(service, "template")
    assert row["support"] == "unsupported" and "escaped" in row["reason"]
    with pytest.raises(ValueError, match="escaped"):
        service.run_recipe(row["reference"], {"units": "test"})


def test_model_merge_matches_existing_api_and_preserves_input(installed):
    service, _, model = installed
    model.write_text(MODEL.replace("*END", "*CONTROL_TERMINATION\n1\n*END"), encoding="utf8")
    before = fingerprint(model)
    row = row_for(service, "template")
    old = service.instantiate_installed_template(row["resource"]["id"], {"T": 5}, "test",
                                                model=str(model), native_check=False)
    result = service.run_recipe(row["reference"], {"units": "test", "values": {"T": 5}}, model=str(model))
    assert result["status"] == old["status"] == "succeeded"
    assert Path(result["artifacts"][0]["path"]).read_bytes() == Path(old["artifacts"][0]["path"]).read_bytes()
    assert result["data"]["replaced_keywords"] == ["*CONTROL_TERMINATION"]
    assert fingerprint(model) == before
