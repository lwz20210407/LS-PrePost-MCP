"""Validate native movie output without transcoding or generating replacement frames."""

import json
import re
import shutil
import subprocess
from fractions import Fraction


def movie_validators():
    paths = {name: shutil.which(name) for name in ("ffprobe", "ffmpeg")}
    if not all(paths.values()):
        raise ValueError(
            "Native MP4 verification requires ffprobe and ffmpeg on PATH; no software is downloaded"
        )
    return paths


def parse_movie_log(text, expected_states):
    starts = text.count("Creating Movie...") - text.count("Finished Creating Movie...")
    frames = [
        (int(state) + 1, int(frame))
        for state, frame in re.findall(r"writing state #(\d+), frame #(\d+)", text)
    ]
    expected = list(zip(expected_states, range(1, len(expected_states) + 1), strict=True))
    if starts != 1 or text.count("Finished Creating Movie...") != 1 or frames != expected:
        raise ValueError("Native movie completion/state/frame evidence does not match the requested sequence")
    return dict(states=[s for s, _ in frames], frame_count=len(frames), native_log_state_index_base=0)


def validate_mp4(path, width, height, fps, frame_count, validators, timeout):
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Native MP4 is missing or empty")
    probe = subprocess.run(
        [
            validators["ffprobe"],
            "-v",
            "error",
            "-select_streams",
            "v",
            "-count_frames",
            "-show_entries",
            "stream=codec_name,width,height,r_frame_rate,nb_read_frames,duration",
            "-of",
            "json",
            str(path),
        ],
        cwd=path.parent,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if probe.returncode or probe.stderr.strip():
        raise ValueError("ffprobe could not validate native MP4: " + probe.stderr[:1000])
    streams = json.loads(probe.stdout).get("streams", [])
    if len(streams) != 1:
        raise ValueError("Expected exactly one native video stream")
    stream = streams[0]
    if (
        stream.get("codec_name") != "h264"
        or stream.get("width") != width
        or stream.get("height") != height
        or Fraction(stream.get("r_frame_rate", "0")) != fps
        or int(stream.get("nb_read_frames", -1)) != frame_count
    ):
        raise ValueError("Native movie codec/dimensions/rate/decoded frame count mismatch")
    duration = float(stream.get("duration", "nan"))
    if not abs(duration - frame_count / fps) <= 1e-4:
        raise ValueError("Native movie duration mismatch")
    decoded = subprocess.run(
        [validators["ffmpeg"], "-v", "error", "-xerror", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"],
        cwd=path.parent,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if decoded.returncode or decoded.stderr.strip():
        raise ValueError("Native video failed full decoding: " + decoded.stderr[:1000])
    return dict(
        codec="h264",
        width=width,
        height=height,
        fps=fps,
        decoded_frames=frame_count,
        duration_seconds=duration,
        full_decode_passed=True,
        transcoded=False,
    )
