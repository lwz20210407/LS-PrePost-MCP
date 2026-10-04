import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.recording_compiler import compile_commands
from ls_prepost_mcp.registry import SERVICE_TOOLS
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.sessions import Sessions
from ls_prepost_mcp.workflows import resolve, set_parameter_binding


def test_registry_is_unique_and_resolves():
    assert len(SERVICE_TOOLS) == len(set(SERVICE_TOOLS))
    assert all(callable(getattr(Service, name)) for name in SERVICE_TOOLS)


def test_recording_opaque_scripts_and_incomplete_mesh_block_replay():
    r = compile_commands('top\nrunpython "opaque.py"\nmeshing boxsolid create 0 0 0 2 2 2 2 2 2 0', "mm")
    assert len(r["unrecognized_commands"]) == 2
    assert r["steps"][0]["action"] == "set_gui_display"
    clean = compile_commands(
        'meshing boxsolid create 0 0 0 2 3 4 2 3 4 0\nmeshing boxsolid accept 1 1 1 boxsolid\nsave keyword "original.k"',
        "mm",
    )
    assert not clean["unrecognized_commands"]
    assert clean["steps"][0]["arguments"]["size"] == [2, 3, 4]
    assert clean["steps"][1] == {"id": "step2", "action": "checkpoint", "arguments": {}}


def test_workflow_bindings_and_failure_stop(tmp_path, monkeypatch):
    assert resolve(
        {"x": {"$param": "width"}, "p": {"$artifact": "first"}},
        {"width": 3},
        {"first": {"artifacts": [{"path": "model.k"}]}},
    ) == {"x": 3, "p": "model.k"}
    with pytest.raises(ValueError):
        resolve({"$artifact": "future"}, {}, {})
    with pytest.raises(ValueError):
        set_parameter_binding({"size": [1, 2, 3]}, ["size", -1], "width")
    s = Service(Settings(tmp_path))
    called = []

    def fail(**kwargs):
        called.append(kwargs)
        return {"status": "failed"}

    monkeypatch.setattr(s, "inspect_model", fail)
    r = s.create_workflow(
        "stop test",
        [
            dict(id="first", action="inspect_model", arguments={"model": "a"}),
            dict(id="second", action="inspect_model", arguments={"model": "b"}),
        ],
    )
    result = s.run_workflow(r["artifacts"][0]["path"])
    assert result["status"] == "failed" and len(called) == 1


def test_parameterize_preserves_recording_review_gate_and_result_type(tmp_path):
    p = tmp_path / "recording.json"
    atomic_json(
        p,
        dict(
            schema_version=1,
            name="review",
            defaults={},
            steps=[dict(id="first", action="set_gui_display", arguments={"state": 1})],
            requires_gui_session=True,
            initial_model="d3plot",
            initial_file_type="d3plot",
            unrecognized_commands=[{"reason": "opaque script"}],
        ),
    )
    s = Service(Settings(tmp_path))
    r = s.parameterize_workflow(str(p), [dict(step_id="first", path=["state"], parameter="state")])
    updated = json.loads(Path(r["artifacts"][0]["path"]).read_text())
    assert updated["requires_gui_session"] and updated["initial_file_type"] == "d3plot"
    with pytest.raises(ValueError, match="review"):
        s.run_workflow(r["artifacts"][0]["path"], session_id="a" * 32)


def session_fixture(tmp_path, monkeypatch, state="ready"):
    import ls_prepost_mcp.sessions as module

    manager = Sessions(Settings(tmp_path, timeout=0.01))
    sid = "a" * 32
    directory = manager.directory(sid)
    directory.mkdir(parents=True)
    meta = dict(
        session_id=sid,
        process={"pid": 123, "create_time": 1, "exe": "fake"},
        state=state,
        dirty=False,
        model_kind="keyword",
    )
    manager.save(sid, meta)
    monkeypatch.setattr(module, "alive", lambda _: True)
    monkeypatch.setattr(module, "process_identity", lambda _: meta["process"])
    return manager, sid, module


def test_uncertain_session_read_does_not_clear_failure(tmp_path, monkeypatch):
    manager, sid, module = session_fixture(tmp_path, monkeypatch, "uncertain")

    class Transport:
        def __init__(self, pid):
            assert pid == 123

        def preflight(self):
            pass

        def submit(self, command):
            request = next((manager.directory(sid) / "requests").iterdir())
            atomic_json(
                request / "complete.json", dict(job_id=request.name, ok=True, data={"counts": {"nodes": 8}})
            )

    monkeypatch.setattr(module, "WindowsCommandTransport", Transport)
    assert manager.dispatch(sid, "inspect_model", {})["status"] == "succeeded"
    assert manager.read(sid)["state"] == "uncertain"


def test_timeout_blocks_redispatch_until_late_completion_recovered(tmp_path, monkeypatch):
    manager, sid, module = session_fixture(tmp_path, monkeypatch)
    submitted = []

    class Transport:
        def __init__(self, pid):
            pass

        def preflight(self):
            pass

        def submit(self, command):
            submitted.append(command)

    monkeypatch.setattr(module, "WindowsCommandTransport", Transport)
    with pytest.raises(TimeoutError):
        manager.dispatch(sid, "create_box", {})
    with pytest.raises(RuntimeError, match="outstanding"):
        manager.dispatch(sid, "inspect_model", {})
    assert len(submitted) == 1
    request_id = manager.read(sid)["active_request"]
    atomic_json(
        manager.directory(sid) / "requests" / request_id / "complete.json",
        dict(job_id=request_id, ok=True, data={}),
    )
    recovered = Service(manager.settings).recover_gui_session(sid)
    assert recovered["state"] == "ready" and recovered["active_request"] is None
    assert recovered["dirty"] is True
    assert recovered["recovery_mode"] == "validated_native_kernel"
    assert len(submitted) == 1


@pytest.mark.parametrize("process_alive", [True, False])
def test_late_command_readback_does_not_bypass_host_validation(tmp_path, monkeypatch, process_alive):
    manager, sid, module = session_fixture(tmp_path, monkeypatch, "uncertain")
    rid = "b" * 32
    directory = manager.directory(sid) / "requests" / rid
    directory.mkdir(parents=True)
    meta = manager.read(sid)
    meta.update(active_request=rid, last_checkpoint="trusted.k")
    manager.save(sid, meta)
    atomic_json(directory / "request.json", dict(job_id=rid, action="gui_mesh_digest", model=None,
                                                native_commands=["nodeedit transform accept"]))
    atomic_json(directory / "contract.json", dict(artifacts=[], export=False, was_uncertain=False))
    atomic_json(directory / "complete.json", dict(job_id=rid, ok=True, data=dict(counts=dict(nodes=8))))
    monkeypatch.setattr(module, "alive", lambda _: process_alive)
    result = Service(manager.settings).recover_gui_session(sid)
    assert result["state"] == ("uncertain" if process_alive else "exited")
    assert result["dirty"] and result["active_request"] is None
    assert result["requires_host_validation"] and result["last_checkpoint"] == "trusted.k"
    assert json.loads((directory / "recovery.json").read_text())["status"] == "completed_unverified"
    with pytest.raises(ValueError, match="trusted checkpoint"):
        Service(manager.settings).checkpoint_gui_session(sid)
    with pytest.raises(ValueError, match="trusted checkpoint"):
        Service(manager.settings).gui_session_action(sid, "export_keyword", {})
    with pytest.raises(ValueError, match="trusted checkpoint"):
        Service(manager.settings).reset_gui_session(sid)


def test_late_reopen_clears_previous_model_checkpoint_and_caches(tmp_path, monkeypatch):
    manager, sid, _ = session_fixture(tmp_path, monkeypatch, "uncertain")
    rid = "b" * 32
    directory = manager.directory(sid) / "requests" / rid
    directory.mkdir(parents=True)
    model = manager.directory(sid) / "inputs" / "d3plot"
    model.parent.mkdir()
    model.touch()
    atomic_json(model.parent / "inputs.json", [dict(path="original-result/d3plot")])
    meta = manager.read(sid)
    meta.update(active_request=rid, last_checkpoint="old.k", source="old-original.k", selection_buffers={"1":{}})
    manager.save(sid, meta)
    atomic_json(directory / "request.json", dict(job_id=rid, action="inspect_model", model=str(model),
                                                native_commands=[], file_type="d3plot"))
    atomic_json(directory / "contract.json", dict(artifacts=[], export=False, was_uncertain=True))
    atomic_json(directory / "complete.json", dict(job_id=rid, ok=True, data=dict(counts={})))
    result = Service(manager.settings).recover_gui_session(sid)
    assert result["state"] == "ready" and result["model_kind"] == "d3plot"
    assert result["source"] == "original-result/d3plot" and result["last_checkpoint"] is None
    assert not result["selection_buffers"] and result["model_generation"]


def test_late_invalid_artifact_keeps_pending_request_and_checkpoint(tmp_path, monkeypatch):
    manager, sid, _ = session_fixture(tmp_path, monkeypatch)
    rid = "b" * 32
    directory = manager.directory(sid) / "requests" / rid
    directory.mkdir(parents=True)
    meta = manager.read(sid)
    meta.update(active_request=rid, last_checkpoint="trusted.k")
    manager.save(sid, meta)
    atomic_json(directory / "request.json", dict(job_id=rid, action="export_keyword", model=None, native_commands=[]))
    atomic_json(directory / "contract.json", dict(artifacts=[["model.k","keyword"]], export=True, was_uncertain=False))
    atomic_json(directory / "complete.json", dict(job_id=rid, ok=True, data={}))
    (directory / "model.k").write_text("corrupt output")
    with pytest.raises(ValueError, match="keyword"):
        Service(manager.settings).recover_gui_session(sid)
    result = manager.read(sid)
    assert result["state"] == "uncertain" and result["active_request"] == rid
    assert result["last_checkpoint"] == "trusted.k"


@pytest.mark.parametrize("phase,state,expected", [("succeeded","ready","succeeded"),
    ("restoring","ready","uncertain"), ("succeeded","uncertain","uncertain")])
def test_restart_reuses_known_live_replacement_without_launching(tmp_path, monkeypatch, phase, state, expected):
    manager, sid, module = session_fixture(tmp_path, monkeypatch)
    child = "b" * 32
    manager.directory(child).mkdir()
    old = manager.read(sid)
    old.update(restarted_as=child, restart_status=phase)
    manager.save(sid, old)
    manager.save(child, dict(session_id=child, process=dict(pid=456), state=state, model_kind="keyword", dirty=False))
    monkeypatch.setattr(module, "alive", lambda p: p["pid"] == 456)
    service = Service(manager.settings)
    monkeypatch.setattr(service, "start_gui_session", lambda: pytest.fail("Duplicate replacement GUI"))
    result = service.restart_gui_session(sid)
    assert result["session_id"] == child and result["reused"] and result["status"] == expected


@pytest.mark.parametrize("invalid", ["response_id", "request_id", "missing_success_flag"])
def test_mismatched_late_reply_is_not_a_completion(tmp_path, monkeypatch, invalid):
    manager, sid, _ = session_fixture(tmp_path, monkeypatch)
    rid = "b" * 32
    directory = manager.directory(sid) / "requests" / rid
    directory.mkdir(parents=True)
    meta = manager.read(sid)
    meta.update(active_request=rid)
    manager.save(sid, meta)
    request = dict(job_id=rid, action="inspect_model", model=None, native_commands=[])
    reply = dict(job_id=rid, ok=True, data={})
    if invalid == "response_id":
        reply["job_id"] = "c"*32
    elif invalid == "request_id":
        request["job_id"] = "c"*32
    else:
        reply.pop("ok")
    atomic_json(directory / "request.json", request)
    atomic_json(directory / "contract.json", dict(artifacts=[], export=False, was_uncertain=False))
    atomic_json(directory / "complete.json", reply)
    with pytest.raises((ValueError, RuntimeError)):
        Service(manager.settings).recover_gui_session(sid)
    current = manager.read(sid)
    assert current["state"] == "uncertain" and current["active_request"] == rid


def test_session_identity_and_directory_boundaries(tmp_path, monkeypatch):
    manager = Sessions(Settings(tmp_path))
    with pytest.raises(ValueError):
        manager.directory("../outside")
    import ls_prepost_mcp.sessions as module

    monkeypatch.setattr(
        module, "process_identity", lambda _: dict(pid=123, exe="different.exe", create_time=10)
    )
    assert not module.alive(dict(pid=123, exe="old.exe", create_time=1))


def test_locked_desktop_rejection_preserves_session_and_creates_no_pending_job(tmp_path, monkeypatch):
    manager, sid, module = session_fixture(tmp_path, monkeypatch)
    class LockedTransport:
        def __init__(self, pid):
            pass

        def preflight(self):
            raise RuntimeError("Interactive desktop is unavailable")

        def submit(self, command):
            raise AssertionError("Must not dispatch or fallback")
    monkeypatch.setattr(module, "WindowsCommandTransport", LockedTransport)
    before = manager.read(sid)
    with pytest.raises(RuntimeError, match="desktop"):
        manager.dispatch(sid, "create_box", {})
    assert manager.read(sid) == before
    assert not (manager.directory(sid)/"requests").exists()


def test_quality_rejects_empty_and_invalid_repetition():
    from ls_prepost_mcp.mesh_quality import quality

    nodes = [[1, 0, 0, 0], [2, 1, 0, 0], [3, 0, 1, 0]]
    assert not quality(nodes, [])["valid_within_scope"]
    assert quality(nodes, [dict(type="shell", id=1, nodes=[1, 2, 3, 3])])["valid_within_scope"]
    assert not quality(nodes, [dict(type="shell", id=1, nodes=[1, 2, 1, 3])])["valid_within_scope"]


@pytest.mark.parametrize("batch_ok", [True, False])
def test_gui_transform_uses_native_checkpoint_then_reopen(tmp_path, monkeypatch, batch_ok):
    from contextlib import nullcontext

    calls = []
    meta = dict(state="ready", model_kind="keyword", dirty=False)

    class Manager:
        def lock(self, sid):
            return nullcontext()

        def read(self, sid):
            return dict(meta)

        def save(self, sid, data):
            meta.update(data)

        def dispatch(self, sid, action, params, **kw):
            calls.append(action)
            return dict(status="succeeded", artifacts=[dict(path=str(tmp_path / "checkpoint.k"))])

        def stage_input(self, sid, path, kind):
            return Path(path)

        def journal(self, sid, data):
            pass

    def native(self, action, p, model=None, **kw):
        assert model == str(tmp_path / "checkpoint.k")
        calls.append("batch_" + action)
        return dict(
            status="succeeded" if batch_ok else "failed",
            job_id="batch",
            data={},
            artifacts=[dict(path=str(tmp_path / "output.k"))],
        )

    monkeypatch.setattr(Service, "_native", native)
    s = Service(Settings(tmp_path))
    monkeypatch.setattr(s, "_session_manager", Manager)
    r = s.gui_session_action(
        "a" * 32, "rotate_mesh_nodes", dict(node_ids=[1], axis="z", angle=90, center=[0, 0, 0], units="mm")
    )
    assert r["execution_mode"] == "native_checkpoint_batch_reopen"
    assert calls == ["export_keyword", "batch_rotate_nodes"] + (["inspect_model"] if batch_ok else [])
    assert r["gui_model_replaced"] == batch_ok
