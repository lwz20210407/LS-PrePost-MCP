"""One owned LS-PrePost process per job. No shell or ambient cwd."""
import os
import subprocess
import time
from pathlib import Path


def decode(value) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else (value or "")


def execute(executable: Path, cfile: Path, directory: Path, *, timeout: float, graphics: bool) -> dict:
    args = [str(executable), "c=" + str(cfile)]
    if graphics:
        args.append("w=1024x768")
    else:
        args.append("-nographics")
    env = os.environ.copy()
    temp = directory / "tmp"
    temp.mkdir()
    env.update(TEMP=str(temp), TMP=str(temp))
    start = time.monotonic()
    proc = subprocess.Popen(args, cwd=directory, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, check=False, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        proc.kill()
        stdout, stderr = proc.communicate(timeout=15)
    (directory / "stdout.log").write_text(decode(stdout), encoding="utf-8")
    (directory / "stderr.log").write_text(decode(stderr), encoding="utf-8")
    return {"returncode": proc.returncode, "timed_out": timed_out, "pid": proc.pid,
            "elapsed_seconds": round(time.monotonic() - start, 3), "argv": args,
            "cwd": str(directory), "graphics": graphics}
