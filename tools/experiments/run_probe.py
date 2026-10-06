"""I10: run an owned E1-E4 process after the agreed GUI window starts."""

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from ls_prepost_mcp.native_config import isolate_preferences  # noqa: E402


def run(directory, executable):
    config = json.loads((directory / "config.json").read_text(encoding="utf8"))
    if (directory / "host-result.json").exists():
        raise ValueError("Existing experiment evidence; prepare a fresh directory")
    env, preferences = isolate_preferences(executable, directory)
    (directory / "tmp").mkdir()
    env.update(TEMP=str(directory / "tmp"), TMP=str(directory / "tmp"))
    with (directory / "stdout.log").open("wb") as out, (directory / "stderr.log").open("wb") as err:
        process = subprocess.Popen(
            [str(executable), "c=" + str(directory / "start.cfile"), "w=1024x768"],
            cwd=directory,
            env=env,
            stdout=out,
            stderr=err,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        started = time.monotonic()
        sent = False
        try:
            while process.poll() is None and time.monotonic() - started < config["timeout"] + 20:
                if (directory / "complete.json").exists():
                    break
                if config["experiment"] == "E3" and (directory / "started.json").exists() and not sent:
                    for i in range(1000):
                        (directory / "requests" / ("%04d.json" % i)).write_text(
                            json.dumps(dict(request_id=config["request_id"], index=i)), encoding="utf8"
                        )
                    sent = True
                if config["experiment"] == "E4" and (directory / "socket.json").exists() and not sent:
                    port = json.loads((directory / "socket.json").read_text())["port"]
                    with socket.create_connection(("127.0.0.1", port), timeout=10) as connection:
                        for i in range(1000):
                            connection.sendall(
                                (json.dumps(dict(request_id=config["request_id"], index=i)) + "\n").encode()
                            )
                    sent = True
                time.sleep(0.05)
            result = dict(
                experiment=config["experiment"],
                pid=process.pid,
                elapsed=time.monotonic() - started,
                preferences=preferences,
                exited=process.poll(),
                native_complete=(directory / "complete.json").exists(),
                gui_responsive="unverified",
                status="unverified",
            )
            if result["native_complete"]:
                receipt = json.loads((directory / "complete.json").read_text())
                if receipt["request_id"] != config["request_id"]:
                    raise ValueError("Wrong request receipt")
                result["native"] = receipt
            if (directory / "probe.png").exists():
                from PIL import Image, ImageStat

                with Image.open(directory / "probe.png") as im:
                    im.load()
                    result["png_decoded_nonblank"] = max(ImageStat.Stat(im.convert("RGB")).stddev) > 1
            # GUI response is an operator observation, never inferred from a file.
            (directory / "host-result.json").write_text(json.dumps(result, indent=2), encoding="utf8")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--executable", type=Path, required=True)
    a = p.parse_args()
    run(a.directory.resolve(), a.executable.resolve(strict=True))
