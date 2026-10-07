"""I01: real loopback sockets with a controlled application main thread."""

import json
import os
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from ls_prepost_mcp.engine import SessionEngine, SessionJob
from ls_prepost_mcp.engine import embedded_queue as bridge
from ls_prepost_mcp.engine.queue_transport import QueueTransport


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    pytest.fail("Queue condition did not arrive")


def request(root, ident, command):
    path = root / "requests" / ident
    path.mkdir(parents=True)
    (path / "queue-job.json").write_text(json.dumps(dict(job_id=ident, commands=[command], python=[])))
    return path


def test_full_queue_produces_definite_failure_without_replay(tmp_path, monkeypatch):
    original_cwd = os.getcwd()
    running, release, queued = threading.Event(), threading.Event(), threading.Event()
    ids = [digit * 32 for digit in "abc"]
    paths = [request(tmp_path, ident, command) for ident, command in zip(ids, ["BLOCK", "SECOND", "NEVER"])]
    calls = []
    real_queue = bridge.queue.Queue

    class ObservedQueue(real_queue):
        def put_nowait(self, ident):
            super().put_nowait(ident)
            if ident == ids[1]:
                queued.set()

    def execute(command):
        calls.append((command, threading.get_ident()))
        if command == "BLOCK":
            running.set()
            assert release.wait(10)

    monkeypatch.setattr(bridge.queue, "Queue", ObservedQueue)
    monkeypatch.setitem(sys.modules, "LsPrePost", SimpleNamespace(execute_command=execute))
    worker = threading.Thread(target=bridge.run, args=(tmp_path, "d" * 32, "e" * 64))
    worker.start()
    try:
        wait_for(lambda: (tmp_path / "ready.json").exists())
        transport = QueueTransport(json.loads((tmp_path / "ready.json").read_text()), 1)
        transport.submit(ids[0])
        assert running.wait(5)
        transport.submit(ids[1])
        assert queued.wait(5)
        result = SessionEngine().run(SessionJob("third", paths[2], 2,
            lambda: transport.submit(ids[2]), lambda: worker.is_alive()))
        assert result.status == "failed" and result.error["type"] == "QueueBusy"
        assert result.error["executed"] is False
        assert not (paths[2] / "queue-started.json").exists()
        rejected = (paths[2] / "complete.json").read_bytes()
        release.set()
        wait_for(lambda: any(command == "SECOND" for command, _ in calls))
        # A later notification for the rejected identity cannot replay it.
        transport.submit(ids[2])
        time.sleep(0.1)
        assert calls == [("BLOCK", worker.ident), ("SECOND", worker.ident)]
        assert (paths[2] / "complete.json").read_bytes() == rejected
    finally:
        release.set()
        (tmp_path / "STOP").touch()
        worker.join(timeout=5)
        os.chdir(original_cwd)
        assert not worker.is_alive()


def test_nonexistent_request_does_not_crash_listener(tmp_path, monkeypatch):
    original_cwd = os.getcwd()
    calls = []
    monkeypatch.setitem(sys.modules, "LsPrePost", SimpleNamespace(execute_command=calls.append))
    ident = "a" * 32
    request(tmp_path, ident, "VALID")
    worker = threading.Thread(target=bridge.run, args=(tmp_path, "d" * 32, "e" * 64))
    worker.start()
    try:
        wait_for(lambda: (tmp_path / "ready.json").exists())
        transport = QueueTransport(json.loads((tmp_path / "ready.json").read_text()), 1)
        transport.submit("b" * 32)
        transport.submit(ident)
        wait_for(lambda: "VALID" in calls)
        assert worker.is_alive() and not (tmp_path / "requests" / ("b" * 32)).exists()
    finally:
        (tmp_path / "STOP").touch()
        worker.join(timeout=5)
        os.chdir(original_cwd)
        assert not worker.is_alive()


@pytest.mark.parametrize("ident", [None, "", "a" * 31, "A" * 32, "../request", 5])
def test_bad_request_id_is_rejected_before_connect(monkeypatch, ident):
    monkeypatch.setattr("socket.create_connection", lambda *a, **k: pytest.fail("No connection for invalid ID"))
    transport = QueueTransport(dict(port=1234, token="e" * 64, session_id="d" * 32), 1)
    with pytest.raises(ValueError, match="request ID"):
        transport.submit(ident)
