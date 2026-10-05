"""I10: probe actual .mac loading/execution, never the JSON template API.

m= is documented as load-only. The visible-session candidate uses the observed
4.13.4 Macro list/Exec controls with PID, caption and macro-name checks.
Batch candidates record failure/unverified when no execution is observed.
"""

import json
import subprocess
import time
from pathlib import Path


def run(cell, executable, lane, run_dir):
    from ls_prepost_mcp.native_config import isolate_preferences
    from ls_prepost_mcp.windows_transport import WindowsCommandTransport

    directory = Path(cell["directory"])
    source = (directory / "program.mac").read_text(encoding="utf8")
    tail = ""
    if lane == "png":
        tail += 'isometric\nac\nprint png "' + str(directory / "image.png") + '" opaque enlisted "OGL1x1"\n'
    if lane == "mp4":
        tail += 'openc d3plot "' + str(directory.parent / "fixture/d3plot") + '"\n'
        tail += (
            'anim stop\nanim first 1\nanim last 3\nanim incr 1\nmovie MP4/H264 640x480 "'
            + str(directory / "movie")
            + '" 5\n'
        )
    tail += 'runscript "' + str(directory / "receipt.scl") + '"\n'
    macro = run_dir / "probe.mac"
    macro.write_text(source.replace("*macro end", tail + "*macro end"), encoding="utf8")
    start = run_dir / "start.cfile"
    commands = 'open keyword "' + str(directory.parent / "fixture/input.k") + '"\n'
    if cell["mode"] != "session":
        commands += "exit\n"
    start.write_text(commands, encoding="utf8")
    env, preferences = isolate_preferences(executable, run_dir)
    (run_dir / "tmp").mkdir()
    env.update(TEMP=str(run_dir / "tmp"), TMP=str(run_dir / "tmp"))
    argv = [str(executable), "m=" + str(macro), ("runc=" if cell["mode"] == "runc" else "c=") + str(start)]
    if cell["mode"] == "nographics":
        argv.append("-nographics")
    evidence = dict(argv=argv, preferences=preferences, source_kind="native_macro", trigger="m= load")
    began = time.time_ns()
    with (run_dir / "stdout.log").open("wb") as out, (run_dir / "stderr.log").open("wb") as err:
        process = subprocess.Popen(
            argv,
            cwd=run_dir,
            env=env,
            stdout=out,
            stderr=err,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            if cell["mode"] == "session":
                transport = WindowsCommandTransport(process.pid)
                deadline = time.monotonic() + 30
                while True:
                    try:
                        menu = transport.inspect_menu()
                        if any(item["path"] == ["Misc.", "Launch Macro Interface"] for item in menu):
                            break
                    except RuntimeError:
                        pass
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Experimental macro process did not expose the recorded menu")
                    time.sleep(0.1)
                transport.open_menu_item(["Misc.", "Launch Macro Interface"])
                while True:
                    try:
                        handle = transport._panel_control("Macro", 10609, class_name="ListBox")
                        break
                    except RuntimeError:
                        if process.poll() is not None or time.monotonic() > deadline:
                            raise
                        time.sleep(0.1)
                transport.require_interactive_desktop()
                # User32 marshals these standard listbox messages cross-process.
                result = transport.ctypes.c_size_t()
                if not transport.u.SendMessageTimeoutW(
                    handle, 0x018A, 0, 0, 2, 2000, transport.ctypes.byref(result)
                ):
                    raise RuntimeError("Cannot query native macro name length")
                if not 0 < result.value < 256:
                    raise ValueError("Native macro name exceeds bounded read buffer")
                text = transport.ctypes.create_unicode_buffer(256)
                pointer = transport.ctypes.cast(text, transport.ctypes.c_void_p).value
                if not transport.u.SendMessageTimeoutW(
                    handle, 0x0189, 0, pointer, 2, 2000, transport.ctypes.byref(result)
                ):
                    raise RuntimeError("Cannot read native macro list")
                if text.value != "M0Export":
                    raise ValueError("Expected exactly the experimental M0Export macro at first row")
                if not transport.u.SendMessageTimeoutW(
                    handle, 0x0186, 0, 0, 2, 2000, transport.ctypes.byref(result)
                ):
                    raise RuntimeError("Cannot select experimental macro")
                parent = transport.u.GetParent(handle)
                if not transport.u.SendMessageTimeoutW(
                    parent, 0x0111, 10609 | (1 << 16), handle, 2, 2000, transport.ctypes.byref(result)
                ):
                    raise RuntimeError("Macro selection notification timed out")
                transport._click_panel_control("Macro", 10615, "Exec")
                evidence["trigger"] = "native Macro list M0Export + Exec (10615), PID/caption checked"
            deadline = time.monotonic() + 60
            receipt = directory / "receipt.txt"
            while process.poll() is None and time.monotonic() < deadline:
                if receipt.exists() and receipt.stat().st_mtime_ns >= began:
                    # Host checks rendering separately; allow output to finish.
                    if (
                        lane == "execution"
                        or (directory / ("image.png" if lane == "png" else "movie.mp4")).exists()
                    ):
                        break
                time.sleep(0.1)
            evidence["returncode"] = process.poll()
            return evidence
        finally:
            (run_dir / "macro-launch.json").write_text(json.dumps(evidence, indent=2), encoding="utf8")
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
