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
    assert len(submitted) == 1


def test_session_identity_and_directory_boundaries(tmp_path, monkeypatch):
    manager = Sessions(Settings(tmp_path))
    with pytest.raises(ValueError):
        manager.directory("../outside")
    import ls_prepost_mcp.sessions as module

    monkeypatch.setattr(
        module, "process_identity", lambda _: dict(pid=123, exe="different.exe", create_time=10)
    )
    assert not module.alive(dict(pid=123, exe="old.exe", create_time=1))


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
