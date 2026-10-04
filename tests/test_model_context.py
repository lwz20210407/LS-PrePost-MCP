import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.model_context import verify_loaded_model
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.sessions import Sessions


@pytest.mark.parametrize("reported", [r"f:\cases\staged/", "F:/cases/staged/model.k"])
def test_keyword_file_or_unique_native_directory_can_identify_staged_source(reported):
    proof = verify_loaded_model(dict(model="F:/cases/staged/model.k"),
                                dict(model_directory=reported, counts=dict(nodes=10, states=1)))
    assert proof["active_source_verified"]


@pytest.mark.parametrize("reported", [None, "", "model.k", "F:cases/staged/model.k",
                                     "F:/cases/old/", "F:/cases/staged/other.k"])
def test_nonempty_old_or_unidentified_model_is_not_a_successful_open(reported):
    with pytest.raises(ValueError):
        verify_loaded_model(dict(model="F:/cases/staged/model.k"),
                            dict(model_directory=reported, counts=dict(nodes=2957, elements=3005, states=3)))


def test_reset_requires_empty_entities_and_new_context(tmp_path):
    request = dict(action="gui_new", job_directory=str(tmp_path))
    for counts in (dict(nodes=1, elements=0), dict(nodes=0, elements=1), dict(nodes=0), dict(nodes=False, elements=0)):
        with pytest.raises(ValueError):
            verify_loaded_model(request, dict(model_directory=str(tmp_path), counts=counts))
    assert verify_loaded_model(request, dict(model_directory=str(tmp_path/"initial.k"),
                                            counts=dict(nodes=0, elements=0, states=1)))["empty_model_verified"]


def test_matching_directory_does_not_turn_attached_result_into_keyword_model():
    with pytest.raises(ValueError, match="multi-state"):
        verify_loaded_model(dict(model="F:/staged/model.k", file_type="keyword"),
                            dict(model_directory="F:/staged/model.k", counts=dict(nodes=2957, states=3)))


def fixture(tmp_path, monkeypatch, *, old_context=False, new_error=False, delay=False):
    import ls_prepost_mcp.sessions as module

    source = tmp_path / "target.k"
    source.write_text("*KEYWORD\n*NODE\n1,0,0,0\n*END\n")
    manager = Sessions(Settings(tmp_path, timeout=0.01))
    sid = "a" * 32
    directory = manager.directory(sid)
    directory.mkdir(parents=True)
    meta = dict(session_id=sid, process=dict(pid=123, create_time=1, exe="fake"),
                state="ready", dirty=False, model_kind="d3plot", source="old-d3plot",
                staged_model=str(tmp_path/"old"/"d3plot"), model_generation="old-generation",
                selection_buffers={"old": {}}, managed_fringe={"status": "old"})
    manager.save(sid, meta)
    log = directory/"lspost.msg"
    log.write_text("Invalid entity ID! ** Prog Error: from previous request\n")
    monkeypatch.setattr(module, "alive", lambda _: True)
    monkeypatch.setattr(module, "process_identity", lambda _: meta["process"])

    class Transport:
        def __init__(self, pid):
            assert pid == 123

        def preflight(self):
            pass

        def submit(self, command):
            request_dir = next((directory/"requests").iterdir())
            request = json.loads((request_dir/"request.json").read_text())
            if delay:
                return
            with log.open("a") as stream:
                stream.write("Invalid entity ID! ** Prog Error:\n" if new_error else "Finished reading model\n")
            observed = str(tmp_path/"old") if old_context else request["model"]
            atomic_json(request_dir/"complete.json", dict(job_id=request_dir.name, ok=True,
                data=dict(model_directory=observed, counts=dict(nodes=2957, elements=3005, states=1))))

    monkeypatch.setattr(module, "WindowsCommandTransport", Transport)
    service = Service(manager.settings)
    monkeypatch.setattr(service, "_session_manager", lambda: manager)
    return service, manager, sid, source


@pytest.mark.parametrize("failure", ["old_context", "new_error"])
def test_open_does_not_advance_model_identity_on_false_native_success(tmp_path, monkeypatch, failure):
    service, manager, sid, source = fixture(tmp_path, monkeypatch, **{failure: True})
    result = service.open_in_gui_session(sid, str(source))
    assert result["status"] == "failed"
    meta = manager.read(sid)
    assert meta["state"] == "uncertain"
    assert meta["source"] == "old-d3plot" and meta["model_kind"] == "d3plot"
    assert meta["model_generation"] == "old-generation"
    assert meta["active_request"] is None
    # Correlated raw completion is evidence, not an unquestioned success verdict.
    assert json.loads((Path(result["job_directory"])/"complete.json").read_text())["ok"] is True


def test_old_log_error_does_not_reject_a_new_verified_source(tmp_path, monkeypatch):
    service, manager, sid, source = fixture(tmp_path, monkeypatch)
    result = service.open_in_gui_session(sid, str(source))
    assert result["status"] == "succeeded" and result["model_context"]["active_source_verified"]
    assert manager.read(sid)["source"] == str(source)
    assert "previous request" not in (Path(result["job_directory"])/"model-load.log").read_text()


@pytest.mark.parametrize("matches", [False, True])
def test_delayed_open_requires_same_source_verification_as_immediate_open(tmp_path, monkeypatch, matches):
    service, manager, sid, source = fixture(tmp_path, monkeypatch, delay=True)
    with pytest.raises(TimeoutError):
        service.open_in_gui_session(sid, str(source))
    meta = manager.read(sid)
    request_dir = manager.directory(sid)/"requests"/meta["active_request"]
    request = json.loads((request_dir/"request.json").read_text())
    observed = request["model"] if matches else str(tmp_path/"old")
    atomic_json(request_dir/"complete.json", dict(job_id=request_dir.name, ok=True,
        data=dict(model_directory=observed, counts=dict(nodes=2957, elements=3005, states=1))))
    result = service.recover_gui_session(sid)
    assert result["active_request"] is None
    if matches:
        assert result["state"] == "ready" and result["source"] == str(source)
    else:
        assert result["state"] == "uncertain" and result["source"] == "old-d3plot"
        assert result["model_kind"] == "d3plot" and result["model_generation"] == "old-generation"
        assert json.loads((request_dir/"recovery.json").read_text())["status"] == "failed"


def test_log_truncation_is_not_silently_treated_as_a_clean_open(tmp_path, monkeypatch):
    from ls_prepost_mcp.model_context import load_diagnostics

    request = tmp_path/"sessions"/"session"/"requests"/"request"
    request.mkdir(parents=True)
    (request.parent.parent/"lspost.msg").write_text("short")
    with pytest.raises(ValueError, match="truncated"):
        load_diagnostics(request, dict(model_load_log=dict(existed=True, offset=100)))
