"""I04: capture and subsequently verify the 13 transferred UU probe cells.

Experiment evidence verification is distinct from native operation success.
Failed native lanes remain failed in the evidence, even when their recording
and the operator-confirmed remote window validate successfully.
"""

import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

from tools.native_regression import ROOT, cleanup_sessions, python_environment, terminate_owned_tree


def targets():
    return [(version, "runc", language) for version in ("4.13", "4.10")
            for language in ("command", "cfile", "scl", "python", "macro")] + [
                ("4.13", "nographics", "macro"), ("4.10", "nographics", "macro"), ("4.13", "session", "macro")]


def identity(target):
    return "-".join(target) + "-uu_disconnected"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf8"))


def seal_capture(directory):
    """Seal probe reports immediately after capture, before user confirmation."""
    paths = [directory / "uu-result.json", *sorted((directory / "matrix").glob("*/matrix-result.json"))]
    expected = {"-".join(target) + "-unlocked" for target in targets()}
    if {p.parent.name for p in paths[1:]} != expected:
        raise ValueError("Remote capture did not record all 13 requested cells")
    hashes = {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (directory / "capture-hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf8")


def capture(directory, executable, executable_410, fixture, arm, timeout):
    import psutil

    if arm.get("environment") != "UU" or arm.get("phase") != "armed" or arm.get("operator_ready") is not True:
        raise ValueError("Remote capture requires the user's explicit armed UU window")
    runner = directory.parent / "remote-runner"
    runner.mkdir(exist_ok=False)
    command = [sys.executable, "-B", str(ROOT / "tools/experiments/run_remote_probe.py"),
               "--output", str(directory), "--fixture", str(fixture), "--executable-413", str(executable),
               "--executable-410", str(executable_410), "--operator-ready", "--remaining-matrix"]
    try:
        with (runner / "stdout.log").open("wb") as out, (runner / "stderr.log").open("wb") as err:
            process = subprocess.Popen(command, cwd=ROOT, env=python_environment(runner),
                                       stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                owner = psutil.Process(process.pid)
                owner.create_time()
            except psutil.NoSuchProcess:
                owner = None
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                terminate_owned_tree(process, owner)
                raise RuntimeError("UU probe timed out; owned processes stopped") from None
        if code:
            raise RuntimeError("UU capture failed; inspect " + str(runner / "stderr.log"))
        seal_capture(directory)
    finally:
        if directory.exists():
            cleanup_sessions(directory)


def verify_window(report, confirmation):
    if confirmation.get("environment") != "UU" or confirmation.get("phase") != "confirmed":
        raise ValueError("UU disconnection interval still awaits operator confirmation")
    if confirmation.get("operator_confirmed") is not True:
        raise ValueError("Operator must confirm the disconnection interval")
    bounds = [confirmation.get("disconnected_from"), report.get("started_at"),
              report.get("finished_at"), confirmation.get("disconnected_until")]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in bounds):
        raise ValueError("Remote window requires finite Unix timestamps")
    if not bounds[0] <= bounds[1] < bounds[2] <= bounds[3]:
        raise ValueError("Operator's UU window does not cover the complete capture")
    if report.get("environment") != "UU remote" or type(report.get("protocol")) is not int or report["protocol"] != 0:
        raise ValueError("Expected the recorded UU Console environment, not inferred RDP")


def verify_cell(directory, target, confirmation):
    directory = Path(directory).resolve()
    if target not in targets():
        raise ValueError("Unregistered remote probe target")
    hashes = read_json(directory / "capture-hashes.json")
    relative = "matrix/" + "-".join(target) + "-unlocked/matrix-result.json"
    for name in ("uu-result.json", relative):
        if not isinstance(hashes.get(name), str) or hashlib.sha256((directory / name).read_bytes()).hexdigest() != hashes[name]:
            raise ValueError("Remote evidence changed after capture")
    report = read_json(directory / "uu-result.json")
    verify_window(report, confirmation)
    result = read_json(directory / relative)
    cell = result["cell"]
    if (tuple(cell.get(key) for key in ("version", "mode", "language")) != target
            or not isinstance(cell.get("request_id"), str)
            or not re.fullmatch(r"[a-f0-9]{32}", cell["request_id"])):
        raise ValueError("Remote cell identity mismatch")
    if set(result["lanes"]) != {"execution", "png", "mp4"}:
        raise ValueError("Remote cell requires execution, PNG and MP4 records")
    statuses = {}
    for lane, record in result["lanes"].items():
        if record.get("desktop_before") != "unlocked" or record.get("desktop_after") != "unlocked":
            raise ValueError("Desktop condition changed during the UU probe")
        status = record.get("status")
        if status not in ("succeeded", "failed"):
            raise ValueError("Remote lane was not executed")
        if status == "failed" and not record.get("error"):
            raise ValueError("Failed remote lane lacks diagnostics")
        if status == "succeeded" and "artifacts" not in record:
            raise ValueError("Successful remote lane lacks output verification")
        captured = set()
        cell_root = (directory / relative).parent
        for item in record.get("captured_files", []):
            name = item.get("path", "")
            path = (cell_root / name).resolve()
            if not name.startswith(lane + "/artifacts/") or not path.is_relative_to(cell_root):
                raise ValueError("Captured artifact escapes the lane")
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item.get("sha256"):
                raise ValueError("Captured native artifact changed")
            captured.add(path.name)
        if status == "succeeded":
            required = {"receipt.txt"}
            if cell["language"] != "scl":
                required.add("model.k")
            if lane in ("png", "mp4"):
                required.add("image.png" if lane == "png" else "movie.mp4")
            if not required <= captured:
                raise ValueError("Successful lane lacks its immutable artifact copies")
        statuses[lane] = status
    return dict(target=identity(target), scope="probe_evidence_and_remote_window",
                native_lane_statuses=statuses, evidence_sha256=hashes[relative],
                operator_window_verified=True, native_failures_preserved=True)
