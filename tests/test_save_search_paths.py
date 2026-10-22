"""P11 search paths retain their raw cards and complete directory layout."""
import copy
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.domain.model import preflight_includes
from ls_prepost_mcp.service import Service

pytest.importorskip("ansys.dyna.core")


def source(root, directive, path="assets"):
    project = root / "project"
    (project / "assets").mkdir(parents=True)
    (project / "assets/nodes.k").write_bytes(b"*NODE\r\n1,0,0,0\r\n")
    main = project / "main.k"
    main.write_text("*KEYWORD\n" + directive + "\n" + path + "\n*INCLUDE\nnodes.k\n*END\n")
    return main


def fake_reader(service, monkeypatch):
    def native(action, parameters, model=None, **kwargs):
        # Exercise real shared tree lookup on both original and saved layouts.
        tree = preflight_includes(model)
        assert tree["ok"] and len(tree["files"]) == 2
        assert all(p["kind"] != "missing_search_dir" for p in tree["problems"])
        return copy.deepcopy({"status": "succeeded", "job_id": "native-observation",
                              "data": {"counts": {"nodes": 1, "elements": 0}, "part_ids": []}})

    monkeypatch.setattr(service, "_native", native)


@pytest.mark.parametrize("directive", ["*INCLUDE_PATH", "*INCLUDE_PATH_RELATIVE"])
def test_save_model_preserves_relative_search_paths(tmp_path, monkeypatch, directive):
    main = source(tmp_path, directive)
    before = main.read_bytes()
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path / "project",)))
    fake_reader(service, monkeypatch)
    result = JobResult.model_validate_json(json.dumps(service.save_model(str(main))))
    assert result.status == "succeeded", result.error
    assert Path(result.data["main"]).read_bytes() == before and main.read_bytes() == before
    assert (Path(result.data["main"]).parent / "assets/nodes.k").is_file()


def test_unused_upward_search_directory_is_preserved_inside_owned_output(tmp_path, monkeypatch):
    main = source(tmp_path, "*INCLUDE_PATH", "assets\n../unused")
    (tmp_path / "unused").mkdir()
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    fake_reader(service, monkeypatch)
    result = JobResult.model_validate_json(json.dumps(service.save_model(str(main))))
    assert result.status == "succeeded", result.error
    saved = Path(result.data["main"])
    assert (saved.parent / "../unused").resolve().is_relative_to(service.jobs.root / result.job_id)
    assert (saved.parent / "../unused").is_dir()


def test_absolute_search_dependency_stays_explicitly_external(tmp_path, monkeypatch):
    main = source(tmp_path, "*INCLUDE_PATH")
    main.write_text(main.read_text().replace("\nassets\n", "\n" + str(main.parent / "assets") + "\n"))
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    fake_reader(service, monkeypatch)
    result = JobResult.model_validate_json(json.dumps(service.save_model(str(main))))
    assert result.status == "succeeded", result.error
    assert result.data["external_unchanged"] == [str(main.parent / "assets/nodes.k")]
