"""Application-side E4 queue bridge; compatible with embedded Python 3.9.

Only the main thread touches LsPrePost. The receiver accepts authenticated
request IDs; paths and executable content come from the owned request directory.
This runs trusted user-directed programs, not a sandbox.
"""

import json
import os
import queue
import re
import runpy
import socket
import threading
from pathlib import Path


def publish(path, data):
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_text(json.dumps(data), encoding="utf8")
    os.replace(str(temporary), str(path))


def run(root, session_id, token):
    import LsPrePost as lp

    root = Path(root).resolve()
    pending = queue.Queue(maxsize=1)
    stopped = threading.Event()
    seen = set()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(2)
    listener.settimeout(0.2)

    def receive():
        while not stopped.is_set():
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                with connection:
                    connection.settimeout(2)
                    with connection.makefile("rb") as stream:
                        raw = stream.readline(4097)
                    if len(raw) > 4096 or not raw.endswith(b"\n"):
                        continue
                    message = json.loads(raw)
                    if not isinstance(message, dict):
                        continue
                    if message.get("token") != token or message.get("session_id") != session_id:
                        continue
                    ident = message.get("request_id")
                    if not isinstance(ident, str) or not re.fullmatch(r"[a-f0-9]{32}", ident) or ident in seen:
                        continue
                    directory = (root / "requests" / ident).resolve()
                    if directory.parent != root / "requests" or not (directory / "queue-job.json").is_file():
                        continue
                    complete = directory / "complete.json"
                    if complete.exists() or (directory / "queue-started.json").exists():
                        seen.add(ident)
                        continue
                    try:
                        pending.put_nowait(ident)
                    except queue.Full:
                        # This authenticated request was never accepted. Publish
                        # a terminal, correlated rejection instead of a timeout.
                        publish(complete, dict(job_id=ident, ok=False, error=dict(
                            type="QueueBusy", message="Native queue is full; this request was not accepted",
                            executed=False)))
                    seen.add(ident)
            except (OSError, ValueError):
                continue

    receiver = threading.Thread(target=receive, name="lspp-request-receiver", daemon=True)
    receiver.start()
    publish(root / "ready.json", dict(session_id=session_id, pid=os.getpid(),
                                     port=listener.getsockname()[1], token=token))
    try:
        while not (root / "STOP").exists():
            try:
                ident = pending.get(timeout=0.1)
            except queue.Empty:
                continue
            directory = (root / "requests" / ident).resolve()
            if directory.parent != root / "requests":
                continue
            complete = directory / "complete.json"
            # A duplicate or late notification must never replay a mutation.
            if complete.exists() or (directory / "queue-started.json").exists():
                continue
            publish(directory / "queue-started.json", dict(job_id=ident, pid=os.getpid()))
            try:
                payload = json.loads((directory / "queue-job.json").read_text(encoding="utf8"))
                if payload.get("job_id") != ident:
                    raise ValueError("Queued job identity mismatch")
                os.chdir(str(directory))
                for command in payload["commands"]:
                    # Re-entering runpython from a Python main-thread loop can
                    # deadlock native builds; execute Python files directly.
                    if command.lower().startswith("runpython "):
                        path = command.split(None, 1)[1].strip().strip('"')
                        runpy.run_path(path, run_name="__main__")
                    else:
                        lp.execute_command(command)
                for path in payload["python"]:
                    runpy.run_path(path, run_name="__main__")
            except Exception as exc:
                publish(complete, dict(job_id=ident, ok=False,
                                       error=dict(type=type(exc).__name__, message=str(exc))))
    finally:
        stopped.set()
        listener.close()
        receiver.join(timeout=3)
    # A trailing exit in initialize.cfile is consumed by nested openc command
    # and terminates the live session prematurely. Exit only after STOP.
    lp.execute_command("exit")
