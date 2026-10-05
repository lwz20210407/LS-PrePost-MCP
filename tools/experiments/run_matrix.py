"""I10/E5: collect independent execution/render lanes, with actual desktop state."""

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from ls_prepost_mcp.config import Settings  # noqa: E402
from ls_prepost_mcp.native_config import isolate_preferences  # noqa: E402
from ls_prepost_mcp.programs import native_errors  # noqa: E402
from ls_prepost_mcp.service import Service  # noqa: E402


def desktop_state():
    if os.name != "nt":
        return "unsupported"
    from ctypes import wintypes

    wts = ctypes.WinDLL("wtsapi32")
    kernel = ctypes.WinDLL("kernel32")
    user = ctypes.WinDLL("user32")
    sid = wintypes.DWORD()
    kernel.ProcessIdToSessionId(os.getpid(), ctypes.byref(sid))
    data = ctypes.c_void_p()
    size = wintypes.DWORD()
    wts.WTSQuerySessionInformationW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD),
    ]
    wts.WTSFreeMemory.argtypes = [ctypes.c_void_p]
    if wts.WTSQuerySessionInformationW(None, sid.value, 8, ctypes.byref(data), ctypes.byref(size)):
        try:
            if ctypes.cast(data, ctypes.POINTER(ctypes.c_int))[0] == 4:
                return "rdp_disconnected"
        finally:
            wts.WTSFreeMemory(data)
    user.OpenInputDesktop.restype = wintypes.HANDLE
    user.CloseDesktop.argtypes = [wintypes.HANDLE]
    handle = user.OpenInputDesktop(0, False, 1)
    if not handle:
        return "locked"
    try:
        name = ctypes.create_unicode_buffer(256)
        needed = wintypes.DWORD()
        user.GetUserObjectInformationW.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        if user.GetUserObjectInformationW(handle, 2, name, ctypes.sizeof(name), ctypes.byref(needed)):
            return "unlocked" if name.value.lower() == "default" else "locked"
        return "unknown"
    finally:
        user.CloseDesktop(handle)


def check_outputs(cell, lane, started):
    directory = Path(cell["directory"])
    receipt = directory / "receipt.txt"
    if not receipt.exists() or receipt.stat().st_mtime_ns < started:
        raise ValueError("Missing fresh receipt")
    if receipt.read_text().split() != [cell["request_id"], str(cell["expected_nodes"])]:
        raise ValueError("Receipt identity/count mismatch")
    evidence = {}
    if cell["language"] != "scl":
        model = directory / "model.k"
        if not model.exists() or model.stat().st_mtime_ns < started:
            raise ValueError("Missing fresh keyword export")
        # Native saved text is parsed independently from the receipt.
        count = 0
        block = ""
        for line in model.read_text(errors="replace").splitlines():
            stripped = line.strip()
            if stripped.startswith("*"):
                block = stripped.upper()
            elif block == "*NODE" and stripped and not stripped.startswith("$"):
                count += 1
        if count != cell["expected_nodes"]:
            raise ValueError("Saved keyword node count mismatch")
        evidence["keyword_sha256"] = hashlib.sha256(model.read_bytes()).hexdigest()
    if lane == "png":
        from PIL import Image, ImageStat

        image = directory / "image.png"
        if not image.exists() or image.stat().st_mtime_ns < started:
            raise ValueError("Missing fresh PNG")
        with Image.open(image) as im:
            im.load()
            if max(ImageStat.Stat(im.convert("RGB")).stddev) <= 1:
                raise ValueError("Blank PNG")
            evidence["image_size"] = im.size
    if lane == "mp4":
        movie = directory / "movie.mp4"
        if not movie.exists() or movie.stat().st_mtime_ns < started:
            raise ValueError("Missing fresh MP4")
        if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
            raise ValueError("ffprobe/ffmpeg unavailable for decode validation")
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-count_frames",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,nb_read_frames,r_frame_rate",
                "-of",
                "json",
                str(movie),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        stream = json.loads(probe.stdout)["streams"][0]
        if (stream["width"], stream["height"], int(stream["nb_read_frames"]), stream["r_frame_rate"]) != (
            640,
            480,
            3,
            "5/1",
        ):
            raise ValueError("MP4 frame/size/rate mismatch")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(movie), "-f", "null", "-"],
            capture_output=True,
            timeout=30,
            check=True,
        )
        evidence["movie"] = stream
    return evidence


def run(args):
    cells = json.loads((args.directory / "matrix.json").read_text())
    selected = [
        c
        for c in cells
        if c["desktop"] == args.desktop
        and c["version"] == args.version
        and (args.mode == "all" or c["mode"] == args.mode)
    ]
    service = None
    sid = None
    if any(c["mode"] == "session" for c in selected):
        workspace = args.directory / ("session-" + args.desktop)
        service = Service(Settings(workspace, args.executable, (args.directory,), timeout=60))
        session = service.start_gui_session()
        sid = session["session_id"]
        result = service.open_in_gui_session(sid, str(args.directory / "fixture/d3plot"), file_type="d3plot")
        if result.get("status") != "succeeded":
            raise ValueError("Experimental session could not load fixture")
    try:
        deadline = time.monotonic() + 300
        print("Ready; waiting for actual desktop state: " + args.desktop, flush=True)
        while desktop_state() != args.desktop:
            if time.monotonic() > deadline:
                raise TimeoutError("Requested desktop condition was not observed")
            time.sleep(0.25)
        for cell in selected:
            directory = Path(cell["directory"])
            report = directory / "matrix-result.json"
            if report.exists():
                raise FileExistsError("Prepare a new matrix before rerunning")
            evidence = dict(cell=cell, lanes={})
            for lane in ("execution", "png", "mp4"):
                state_before = desktop_state()
                started = time.time_ns()
                item = dict(status="failed", desktop_before=state_before)
                run_dir = directory / lane
                run_dir.mkdir()
                try:
                    if state_before != args.desktop:
                        raise ValueError("Desktop condition changed before lane")
                    if cell["language"] == "macro":
                        from macro_probe import run as run_macro_probe

                        item["native_macro"] = run_macro_probe(cell, args.executable, lane, run_dir)
                    elif cell["mode"] == "session":
                        result = service._session_manager().dispatch(
                            sid,
                            "inspect_model",
                            {},
                            native_commands=[
                                'openc command "' + str(directory / (lane + ".cfile")) + '" nodialog'
                            ],
                        )
                        item["native_result"] = result
                        if result.get("status") != "succeeded":
                            raise ValueError("Session request failed")
                    else:
                        env, meta = isolate_preferences(args.executable, run_dir)
                        (run_dir / "tmp").mkdir()
                        env.update(TEMP=str(run_dir / "tmp"), TMP=str(run_dir / "tmp"))
                        argv = [
                            str(args.executable),
                            ("runc=" if cell["mode"] == "runc" else "c=")
                            + str(directory / (lane + ".cfile")),
                        ]
                        if cell["mode"] == "nographics":
                            argv.append("-nographics")
                        item.update(argv=argv, preferences=meta)
                        with (
                            (run_dir / "stdout.log").open("wb") as out,
                            (run_dir / "stderr.log").open("wb") as err,
                        ):
                            process = subprocess.Popen(
                                argv,
                                cwd=run_dir,
                                env=env,
                                stdout=out,
                                stderr=err,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                            )
                            try:
                                code = process.wait(timeout=60)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait(timeout=10)
                                raise
                        if code:
                            raise ValueError("Native exit code " + str(code))
                        logs = "\n".join(p.read_text(errors="replace") for p in run_dir.glob("*.log"))
                        if (run_dir / "lspost.msg").exists():
                            logs += "\n" + (run_dir / "lspost.msg").read_text(errors="replace")
                        if native_errors(logs):
                            raise ValueError("Native error log detected")
                    item["artifacts"] = check_outputs(cell, lane, started)
                    if desktop_state() != args.desktop:
                        raise ValueError("Desktop changed during lane; repeat under requested condition")
                    item["status"] = "succeeded"
                except Exception as exc:
                    item["error"] = str(exc)
                item["desktop_after"] = desktop_state()
                item["elapsed_seconds"] = (time.time_ns() - started) / 1e9
                evidence["lanes"][lane] = item
                report.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf8")
                print(cell["id"], lane, item["status"], flush=True)
    finally:
        if service and sid:
            service.close_gui_session(sid, save_checkpoint=False)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--executable", type=Path, required=True)
    p.add_argument("--version", choices=["4.13", "4.10"], required=True)
    p.add_argument("--desktop", choices=["unlocked", "locked", "rdp_disconnected"], required=True)
    p.add_argument("--mode", choices=["all", "runc", "nographics", "session"], default="all")
    a = p.parse_args()
    a.directory = a.directory.resolve()
    a.executable = a.executable.resolve(strict=True)
    run(a)
