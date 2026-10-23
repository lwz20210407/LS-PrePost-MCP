"""P1-3: the second native open must see the actual saved tree, not aliases."""
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.service import Service


@pytest.mark.parametrize("search", [None, "*INCLUDE_PATH", "*INCLUDE_PATH_RELATIVE"])
def test_save_reopens_raw_tree_with_original_cards_and_relative_main(tmp_path, monkeypatch, search):
    root = tmp_path / "source"
    root.mkdir()
    mesh = root / "assets" if search else root
    mesh.mkdir(exist_ok=True)
    (root / "unused").mkdir()
    child = mesh / "nodes.k"
    child.write_bytes(b"*NODE\n1,0,0,0\n")
    main = root / "main.k"
    main.write_text("*KEYWORD\n" + (search + "\nassets\nunused\n" if search else "")
                    + "*INCLUDE\nnodes.k\n*END\n")
    before = {p: p.read_bytes() for p in (main, child)}
    exe = tmp_path / "lsprepost4.13.exe"
    exe.touch()
    service = Service(Settings(tmp_path / "work", exe, (root,)))
    seen = []

    def execute(executable, cfile, directory, **kwargs):
        request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
        native_main = Path(request["model"])
        seen.append(request)
        if len(seen) == 2:
            assert native_main.name == "main.k", "Native reopened a normalized alias instead of saved main.k"
            assert native_main.read_bytes() == before[main]
            assert (native_main.parent / ("assets/nodes.k" if search else "nodes.k")).read_bytes() == before[child]
            if search:
                assert (native_main.parent / "unused").is_dir()
            assert request["absolute_keyword_path"] is False
            assert request["raw_keyword_tree"] is True
            (native_main.parent / "lspost.db").write_bytes(b"native generated auxiliary database")
        observation = {"counts": {"nodes": 1, "elements": 0}, "part_ids": []}
        if len(seen) == 2:
            observation["input_open"] = {"cwd": str(native_main.parent), "load_name": native_main.name,
                                         "resolved_main": str(native_main), "normalized": False}
        (directory / "response.json").write_text(json.dumps({"job_id": directory.name, "ok": True, "data": observation}))
        return JobResult(operation=kwargs["operation"], job_id=directory.name, status="unverified",
                         data={"returncode": 0, "timed_out": False})

    monkeypatch.setattr("ls_prepost_mcp.service.run_batch", execute)
    result = service.save_model(str(main))
    assert result["status"] == "succeeded", result.get("error")
    assert len(seen) == 2 and Path(seen[1]["model"]) == Path(result["data"]["main"])
    assert result["data"]["observations"]["after_reopen"]["input_open"]["normalized"] is False
    assert not (Path(result["data"]["main"]).parent / "lspost.db").exists()
    after_job = service.jobs.get(result["data"]["observations"]["after_reopen"]["job_id"])
    assert after_job["native_open_auxiliary"]["name"] == "lspost.db"
    assert (Path(after_job["job_directory"]) / after_job["native_open_auxiliary"]["relocated_to"]).read_bytes() == b"native generated auxiliary database"
    assert {p: p.read_bytes() for p in before} == before


def test_private_raw_tree_path_refuses_unowned_inputs_before_launch(tmp_path, monkeypatch):
    main = tmp_path / "user.k"
    main.write_bytes(b"*KEYWORD\n*NODE\n1,0,0,0\n*END\n")
    exe = tmp_path / "lsprepost4.13.exe"
    exe.touch()
    service = Service(Settings(tmp_path / "work", exe, (tmp_path,)))
    monkeypatch.setattr("ls_prepost_mcp.service.run_batch", lambda *a, **kw: pytest.fail("unowned raw tree launched"))
    with pytest.raises(ValueError, match="owned"):
        service._native("inspect_model", {}, model=str(main), raw_keyword_tree=True)


def test_raw_open_cannot_overwrite_an_existing_lspost_database_asset(tmp_path, monkeypatch):
    exe = tmp_path / "lsprepost4.13.exe"
    exe.touch()
    service = Service(Settings(tmp_path / "work", exe))
    directory, _ = service.jobs.create("save_model", {})
    root = directory / "deck"
    root.mkdir()
    main = root / "main.k"
    main.write_bytes(b"*KEYWORD\n*NODE\n1,0,0,0\n*END\n")
    existing = root / "lspost.db"
    existing.write_bytes(b"saved asset must survive")
    monkeypatch.setattr("ls_prepost_mcp.service.run_batch", lambda *a, **kw: pytest.fail("collision launched"))
    with pytest.raises(ValueError, match="reserves lspost.db"):
        service._native("inspect_model", {}, model=str(main), raw_keyword_tree=True)
    assert existing.read_bytes() == b"saved asset must survive"
