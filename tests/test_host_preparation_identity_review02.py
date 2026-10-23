"""Review02 #113: preparation and engine manifests must agree on submission."""
import json

import pytest

from tests.test_sessions_workflows import session_fixture


@pytest.mark.parametrize("message", ["Apply preparation failed", ""])
def test_preparation_exception_cannot_be_reported_as_submitted(tmp_path, monkeypatch, message):
    manager, sid, module = session_fixture(tmp_path, monkeypatch)
    meta = manager.read(sid)
    meta.update(bridge_protocol=4)
    manager.save(sid, meta)
    calls = []

    class Transport:
        def __init__(self, pid):
            pass

        def preflight(self):
            pass

        def submit(self, command):
            calls.append(command)

    def prepare(*args):
        (manager.directory(sid) / "lspost.msg").write_bytes(b"host callback native-side activity\r\n")
        raise RuntimeError(message)

    monkeypatch.setattr(module, "WindowsCommandTransport", Transport)
    with pytest.raises(RuntimeError):
        manager.dispatch(sid, "gui_mesh_state", {}, _before_submit=prepare)
    rid = manager.read(sid)["active_request"]
    directory = manager.directory(sid) / "requests" / rid
    engine = json.loads((directory / "engine-result.json").read_text(encoding="utf8"))
    marker = json.loads((directory / "host-preparation-failed.json").read_text(encoding="utf8"))
    assert marker["dispatch_submitted"] is False and not calls
    assert engine["data"]["submitted"] is False
    assert engine["data"]["phase"] == "host_preparation" and engine["status"] == "failed"
    assert engine["error"]["message"] == marker["error"]["message"] == (message or "RuntimeError")
    assert (directory / "native-session.log").read_bytes() == b"host callback native-side activity\r\n"
