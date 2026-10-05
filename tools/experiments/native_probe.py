"""I10 E1-E4 application-side probe. Compatible with embedded Python 3.9.

Executed only in an owned experimental LS-PrePost process with config.json.
No Win32 injection is used after the initial runpython bootstrap.
"""

import json
import os
import queue
import socket
import threading
import time
import traceback
from pathlib import Path


def run(config_path):
    import DataCenter as dc
    import LsPrePost as lp

    config = json.loads(Path(config_path).read_text(encoding="utf8"))
    root = Path(config["directory"])
    request_id = config["request_id"]
    os.chdir(str(root))

    def write(name, data):
        data.update(request_id=request_id)
        target = root / name
        temporary = root / (name + ".new")
        temporary.write_text(json.dumps(data, sort_keys=True), encoding="utf8")
        os.replace(str(temporary), str(target))

    def check_command(index):
        expected = [] if index % 2 == 0 else [11]
        command = "genselect clear" if index % 2 == 0 else "genselect node add node 11"
        lp.execute_command(command)
        count = int(dc.get_data("num_selection"))
        ids = [int(v) for v in dc.get_data("selection_ids", type=0)] if count else []
        if count != len(expected) or sorted(ids) != expected:
            raise ValueError("Selected IDs mismatch at command " + str(index))
        return dict(index=index, command=command, selected_ids=ids)

    def execute_loop(mode):
        observed = []
        started = time.time()
        try:
            for i in range(1000):
                if (root / "STOP").exists():
                    raise RuntimeError("Operator stopped experiment")
                if time.time() - started > config["timeout"]:
                    raise RuntimeError("Probe deadline exceeded")
                if mode == "E3":
                    request = root / "requests" / ("%04d.json" % i)
                    while not request.exists():
                        if time.time() - started > config["timeout"]:
                            raise RuntimeError("Polling request deadline exceeded")
                        time.sleep(0.02)
                    payload = json.loads(request.read_text(encoding="utf8"))
                    if payload != dict(request_id=request_id, index=i):
                        raise ValueError("Request identity mismatch")
                if mode == "E4":
                    payload = work_queue.get(timeout=max(1, config["timeout"] - (time.time() - started)))
                    if payload != dict(request_id=request_id, index=i):
                        raise ValueError("Socket queue request identity mismatch")
                observed.append(check_command(i))
                if i % 25 == 0:
                    write("progress.json", dict(completed=len(observed), elapsed=time.time() - started))
            lp.execute_command('print png "' + str(root / "probe.png") + '" opaque enlisted "OGL1x1"')
            write(
                "complete.json",
                dict(
                    status="commands_verified",
                    count=len(observed),
                    elapsed=time.time() - started,
                    observations=observed,
                    gui_responsive="requires_operator_observation",
                    rendering="requires_host_decode",
                ),
            )
        except Exception:
            write(
                "complete.json",
                dict(
                    status="failed", count=len(observed), error=traceback.format_exc(), observations=observed
                ),
            )

    mode = config["experiment"]
    write("started.json", dict(experiment=mode, thread=threading.current_thread().name))
    if mode == "E2":
        modules = dict(LsPrePost=dir(lp), DataCenter=dir(dc))
        candidates = {
            k: [
                n
                for n in v
                if any(word in n.lower() for word in ("timer", "idle", "callback", "event", "pump"))
            ]
            for k, v in modules.items()
        }
        write(
            "complete.json",
            dict(
                status="unverified",
                modules=modules,
                candidates=candidates,
                registered_callback=False,
                reason="Discovery alone is not successful callback registration; inspect documented signature before calling.",
            ),
        )
        return
    lp.execute_command("genselect target node")
    if mode == "E1":
        thread = threading.Thread(target=execute_loop, args=(mode,), name="M0-native-background")
        thread.daemon = True
        thread.start()
        return
    if mode == "E4":
        work_queue = queue.Queue()

        def receive():
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                listener.settimeout(config["timeout"])
                write("socket.json", dict(port=listener.getsockname()[1]))
                connection, _ = listener.accept()
                with connection, connection.makefile("r") as stream:
                    for line in stream:
                        work_queue.put(json.loads(line))

        thread = threading.Thread(target=receive, name="M0-socket-only")
        thread.daemon = True
        thread.start()
    execute_loop(mode)
