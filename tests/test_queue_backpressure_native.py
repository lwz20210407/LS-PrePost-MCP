"""I01: prepared queue saturation probe; requires an explicit GUI window."""

import json
import socket
import time
import uuid

import psutil
import pytest

from ls_prepost_mcp.engine import SessionEngine, SessionJob
from ls_prepost_mcp.sessions import Sessions
from tests.test_engine_native import native_case  # noqa: F401

pytestmark = [pytest.mark.native, pytest.mark.gui]


def wait_for_file(path, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return
        time.sleep(0.02)
    pytest.fail("Native queue did not produce " + path.name)


def notify_and_wait_for_receiver(ready, ident):
    message = dict(token=ready["token"], session_id=ready["session_id"], request_id=ident)
    with socket.create_connection(("127.0.0.1", ready["port"]), timeout=5) as connection:
        connection.sendall(json.dumps(message).encode("utf8") + b"\n")
        connection.shutdown(socket.SHUT_WR)
        # Receiver closes only after processing the notification. No timing guess
        # between enqueueing the second request and submitting the third one.
        while connection.recv(1024):
            pass


def test_native_queue_rejects_overload_without_late_execution(native_case, pytestconfig):  # noqa: F811
    if not pytestconfig.getoption("--native-gui"):
        pytest.skip("Queue saturation needs an authorized --native-gui window")
    service, _ = native_case
    sessions = Sessions(service.settings)
    started = sessions.start(transport="queue")
    sid = started["session_id"]
    root = sessions.directory(sid)
    release, entered, never = root / "release", root / "entered", root / "never-execute"
    ready = json.loads((root / "ready.json").read_text(encoding="utf8"))
    owner = psutil.Process(ready["pid"])
    requests = []
    try:
        for number in range(4):
            ident = uuid.uuid4().hex
            directory = root / "requests" / ident
            directory.mkdir(parents=True)
            script = directory / "probe.py"
            text = "import json,time\nfrom pathlib import Path\n"
            if number == 0:
                text += "Path(%r).touch()\ndeadline=time.time()+20\n" % str(entered)
                text += "while not Path(%r).exists():\n    if time.time()>deadline: raise RuntimeError('Probe release timed out')\n    time.sleep(0.02)\n" % str(release)
            elif number == 2:
                text += "Path(%r).touch()\n" % str(never)
            text += "Path(%r).write_text(json.dumps(dict(job_id=%r,ok=True)))\n" % (str(directory / "complete.json"), ident)
            script.write_text(text, encoding="utf8")
            (directory / "queue-job.json").write_text(json.dumps(dict(job_id=ident, commands=[], python=[str(script)])), encoding="utf8")
            requests.append((ident, directory))
        notify_and_wait_for_receiver(ready, requests[0][0])
        wait_for_file(entered)
        notify_and_wait_for_receiver(ready, requests[1][0])
        ident, directory = requests[2]
        result = SessionEngine().run(SessionJob("queue_saturation", directory, 5,
            lambda: notify_and_wait_for_receiver(ready, ident), owner.is_running))
        assert result.status == "failed" and result.error["type"] == "QueueBusy", result
        assert result.error["executed"] is False
        release.touch()
        for _, pending in requests[:2]:
            wait_for_file(pending / "complete.json")
            assert json.loads((pending / "complete.json").read_text())["ok"] is True
        notify_and_wait_for_receiver(ready, ident)
        # A completed barrier proves the application drained notifications; do
        # not rely on a short sleep to detect an incorrectly replayed request.
        notify_and_wait_for_receiver(ready, requests[3][0])
        wait_for_file(requests[3][1] / "complete.json")
        assert json.loads((requests[3][1] / "complete.json").read_text())["ok"] is True
        assert not never.exists() and not (directory / "queue-started.json").exists()
    finally:
        release.touch()
        service.close_gui_session(sid, save_checkpoint=False)

