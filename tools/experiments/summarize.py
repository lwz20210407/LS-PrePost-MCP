"""I10: publishable, path-free summary of native experiment evidence.

Only explicit result metadata and file hashes leave the local job directories.
Raw logs, paths, screenshots and input data remain local.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def reason(text):
    if text.startswith("Native exit code "):
        return text
    for token, name in [
        ("frame/size/rate", "movie_contract_mismatch"),
        ("fresh receipt", "missing_fresh_receipt"),
        ("fresh keyword", "missing_fresh_keyword"),
        ("node count", "keyword_count_mismatch"),
        ("native panel", "macro_panel_not_found"),
        ("Desktop", "desktop_condition_changed"),
        ("desktop", "desktop_unavailable"),
        ("Native error log", "native_log_error"),
        ("Session request", "session_request_failed"),
        ("timed out", "timeout"),
    ]:
        if token in text:
            return name
    return "other_failure_in_local_evidence" if text else None


def summarize(roots):
    cells = {}
    for root in roots:
        for path in sorted(root.glob("*/matrix-result.json")):
            result = json.loads(path.read_text(encoding="utf8"))
            cell = result["cell"]
            data = {key: cell[key] for key in ("id", "version", "mode", "language", "desktop")}
            data["evidence_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            data["lanes"] = {}
            for lane, item in result["lanes"].items():
                data["lanes"][lane] = {
                    key: item.get(key)
                    for key in ("status", "desktop_before", "desktop_after", "elapsed_seconds")
                }
                data["lanes"][lane]["reason"] = reason(item.get("error", ""))
                if item.get("artifacts"):
                    data["lanes"][lane]["artifacts"] = item["artifacts"]
            movie = path.parent / "movie.mp4"
            if movie.exists():
                proc = subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-count_frames",
                        "-select_streams",
                        "v:0",
                        "-show_entries",
                        "stream=codec_name,width,height,nb_read_frames,r_frame_rate",
                        "-of",
                        "json",
                        str(movie),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if proc.returncode == 0:
                    data["observed_movie"] = json.loads(proc.stdout)["streams"]
                data["movie_sha256"] = hashlib.sha256(movie.read_bytes()).hexdigest()
            cells[cell["id"]] = data
    return dict(
        schema_version=1,
        scope="I10 synthetic eight-node keyword / three-state shell result; no solver validation",
        matrix=[cells[key] for key in sorted(cells)],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--roots", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.roots)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(len(result["matrix"]), "matrix cells summarized")
