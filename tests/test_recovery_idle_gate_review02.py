"""Host-preparation failure does not prove a live Apply thread is responsive."""
import json

import pytest

from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service
from tests.test_sessions_workflows import session_fixture


def pending(tmp_path, monkeypatch):
    manager, sid, module = session_fixture(tmp_path, monkeypatch, "uncertain")
    rid = "b" * 32
    directory = manager.directory(sid) / "requests" / rid
    directory.mkdir(parents=True)
    meta = manager.read(sid)
    meta.update(active_request=rid, last_checkpoint="trusted.k", engine_transport="win32")
    manager.save(sid, meta)
    atomic_json(directory / "request.json", dict(job_id=rid, action="gui_mesh_state", host_preparation=True))
    atomic_json(directory / "host-preparation-failed.json", dict(job_id=rid, phase="host_preparation",
        dispatch_submitted=False, error=dict(message="Apply outcome remains uncertain")))
    return manager, sid, module, rid, directory


@pytest.mark.parametrize("reply", [RuntimeError("Busy or blocked"), {},
    {"pid": 123, "responsive": True, "enabled": False}, {"pid": 999, "responsive": True, "enabled": True}])
def test_busy_or_unconfirmed_gui_keeps_request_and_checkpoint(tmp_path, monkeypatch, reply):
    manager, sid, module, rid, directory = pending(tmp_path, monkeypatch)
    probes = []
    class Transport:
        def __init__(self, pid):
            assert pid == 123
        def probe_idle(self):
            probes.append("read_only")
            if isinstance(reply, Exception):
                raise reply
            return reply
        def submit(self, command):
            pytest.fail("Recovery must not issue any new native command")
    monkeypatch.setattr(module, "WindowsCommandTransport", Transport)
    result = Service(manager.settings).recover_gui_session(sid)
    assert result["active_request"] == rid, "Request cleared before a successful read-only response probe"
    assert result["state"] == "uncertain" and result["requires_host_validation"]
    assert manager.read(sid)["last_checkpoint"] == "trusted.k"
    assert probes == ["read_only"] and result["recovery_probe"]["status"] == "blocked"
    assert not (directory / "complete.json").exists()


def test_responsive_gui_is_only_a_request_gate_not_model_validation(tmp_path, monkeypatch):
    manager, sid, module, _, directory = pending(tmp_path, monkeypatch)
    probes = []
    class Transport:
        def __init__(self, pid):
            pass
        def probe_idle(self):
            probes.append("WM_NULL")
            return dict(pid=123, responsive=True, enabled=True, probe="WM_NULL")
    monkeypatch.setattr(module, "WindowsCommandTransport", Transport)
    result = Service(manager.settings).recover_gui_session(sid)
    assert probes == ["WM_NULL"]
    assert result["active_request"] is None and result["state"] == "uncertain"
    assert result["requires_host_validation"] and result["dirty"]
    assert result["last_checkpoint"] == "trusted.k"
    saved = json.loads((directory / "recovery.json").read_text(encoding="utf8"))
    assert saved["status"] == "failed" and saved["idle_probe"]["responsive"] is True
    assert saved["requires_host_validation"] and saved["replayed"] is False


def test_exited_identity_does_not_touch_windows_or_replay(tmp_path, monkeypatch):
    manager, sid, module, _, _ = pending(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "alive", lambda identity: False)
    monkeypatch.setattr(module, "WindowsCommandTransport", lambda *args: pytest.fail("Exited process probe"))
    result = Service(manager.settings).recover_gui_session(sid)
    assert result["state"] == "exited" and result["active_request"] is None
    assert result["recovery_probe"]["status"] == "process_exited"


def test_retry_only_probes_again_and_replaces_stale_probe_record(tmp_path, monkeypatch):
    manager, sid, module, rid, directory = pending(tmp_path, monkeypatch)
    replies = [RuntimeError("Apply busy"), dict(pid=123, responsive=True, enabled=True, probe="WM_NULL")]
    class Transport:
        def __init__(self, pid):
            pass
        def probe_idle(self):
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        def submit(self, command):
            pytest.fail("No replay on a response-probe retry")
    monkeypatch.setattr(module, "WindowsCommandTransport", Transport)
    assert Service(manager.settings).recover_gui_session(sid)["active_request"] == rid
    assert json.loads((directory / "recovery-probe.json").read_text())["status"] == "blocked"
    result = Service(manager.settings).recover_gui_session(sid)
    assert result["active_request"] is None and result["requires_host_validation"]
    assert json.loads((directory / "recovery-probe.json").read_text())["status"] == "responded"
    assert not replies and not (directory / "complete.json").exists()


def test_process_identity_change_during_probe_cannot_release_request(tmp_path, monkeypatch):
    manager, sid, module, rid, _ = pending(tmp_path, monkeypatch)
    class Transport:
        def __init__(self, pid):
            pass
        def probe_idle(self):
            monkeypatch.setattr(module, "alive", lambda identity: False)
            return dict(pid=123, responsive=True, enabled=True, probe="WM_NULL")
    monkeypatch.setattr(module, "WindowsCommandTransport", Transport)
    result = Service(manager.settings).recover_gui_session(sid)
    assert result["active_request"] == rid and result["requires_host_validation"]
    assert result["recovery_probe"]["status"] == "blocked"
