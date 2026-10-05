"""I10/E5: collect independent execution/render lanes, with actual desktop state."""

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import struct
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


def session_flags_state(buffer, session_id):
    """Windows x64 WTSINFOEXW Level1 prefix; never infer lock from desktop name."""
    if len(buffer) < 20 or struct.unpack_from("<I", buffer)[0] != 1:
        return "unknown"
    current_id, connection, flags = struct.unpack_from("<III", buffer, 8)
    if current_id != session_id:
        return "unknown"
    if connection == 4:
        return "rdp_disconnected"
    return {0: "locked", 1: "unlocked"}.get(flags, "unknown")


def desktop_state():
    if os.name != "nt":
        return "unsupported"
    from ctypes import wintypes

    wts = ctypes.WinDLL("wtsapi32")
    kernel = ctypes.WinDLL("kernel32")
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
    # WTSINFOEXW's union is aligned to 8 bytes on this Windows x64 target.
    # https://learn.microsoft.com/windows/win32/api/wtsapi32/ns-wtsapi32-wtsinfoex_level1_w
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        return "unsupported"
    if wts.WTSQuerySessionInformationW(None, sid.value, 25, ctypes.byref(data), ctypes.byref(size)):
        try:
            return session_flags_state(ctypes.string_at(data, min(size.value, 20)), sid.value)
        finally:
            wts.WTSFreeMemory(data)
    return "unknown"


def client_protocol_type():
    """Read current WTS client protocol: 0 console, 2 RDP; no client identifiers."""
    if os.name != "nt":
        return None
    from ctypes import wintypes

    sid = wintypes.DWORD()
    ctypes.WinDLL("kernel32").ProcessIdToSessionId(os.getpid(), ctypes.byref(sid))
    wts = ctypes.WinDLL("wtsapi32")
    data, size = ctypes.c_void_p(), wintypes.DWORD()
    wts.WTSQuerySessionInformationW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD),
    ]
    wts.WTSFreeMemory.argtypes = [ctypes.c_void_p]
    if wts.WTSQuerySessionInformationW(None, sid.value, 16, ctypes.byref(data), ctypes.byref(size)):
        try:
            return ctypes.cast(data, ctypes.POINTER(ctypes.c_ushort))[0] if size.value >= 2 else None
        finally:
            wts.WTSFreeMemory(data)
    return None


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
    if args.desktop == "rdp_disconnected" and client_protocol_type() != 2:
        raise ValueError(
            "RDP test requires this runner's Windows session to be connected through actual Remote Desktop before arming"
        )
    cells = json.loads((args.directory / "matrix.json").read_text())
    selected = [
        c
        for c in cells
        if c["desktop"] == args.desktop
        and c["version"] == args.version
        and (args.mode == "all" or c["mode"] == args.mode)
        and (args.language == "all" or c["language"] == args.language)
    ]
    service = None
    sid = None
    if any(c["mode"] == "session" and c["language"] != "macro" for c in selected):
        workspace = args.directory / ("session-" + args.desktop)
        service = Service(Settings(workspace, args.executable, (args.directory,), timeout=60))
        sid = service.start_gui_session()["session_id"]
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
            evidence = dict(cell=cell, lanes={}, protocol_type_at_start=client_protocol_type())
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
                        if sid is None:
                            sid = service.start_gui_session()["session_id"]
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
                finally:
                    if service and sid and args.desktop == "unlocked":
                        service.close_gui_session(sid, save_checkpoint=False)
                        sid = None
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
    p.add_argument("--language", choices=["all", "command", "cfile", "scl", "python", "macro"], default="all")
    a = p.parse_args()
    a.directory = a.directory.resolve()
    a.executable = a.executable.resolve(strict=True)
    run(a)
