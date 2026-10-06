"""Fresh job directories, atomic manifests and content validation."""
import hashlib
import json
import math
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    # Reserve an exclusive sibling without repeating a potentially long target
    # name. Replacement stays on the same volume and remains atomic.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=".", suffix=".tmp",
                                     dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        stream.write(text)
    try:
        for attempt in range(6):
            try:
                tmp.replace(path)
                return
            except PermissionError as exc:
                # Readers/indexers can briefly deny replacement on Windows.
                # Never retry syntax, missing-path or unrelated I/O failures.
                if getattr(exc, "winerror", None) not in (5, 32, 33) or attempt == 5:
                    raise
                time.sleep(0.02 * (2 ** attempt))
    finally:
        if tmp.exists():
            tmp.unlink()


def fingerprint(path: Path) -> dict:
    stat = path.stat()
    result = {"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    if stat.st_size <= 64 * 1024 * 1024:
        result["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        result["sha256"] = None
        result["hash_note"] = "Files over 64 MiB use size/mtime identity in this release"
    return result


class Jobs:
    def __init__(self, workspace: Path):
        self.root = workspace / "jobs"

    def create(self, action: str, parameters: dict) -> tuple[Path, dict]:
        ident = uuid.uuid4().hex
        directory = self.root / ident
        directory.mkdir(parents=True, exist_ok=False)
        manifest = {"job_id": ident, "action": action, "status": "created", "created_at": now(),
                    "parameters": parameters, "artifacts": [], "warnings": []}
        atomic_json(directory / "job.json", manifest)
        return directory, manifest

    def get(self, ident: str) -> dict:
        if not re.fullmatch(r"[a-f0-9]{32}", ident):
            raise ValueError("Invalid job ID")
        return json.loads((self.root / ident / "job.json").read_text(encoding="utf-8"))

    def list(self, limit: int = 20) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be 1..100")
        files = sorted(self.root.glob("*/job.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        return [json.loads(p.read_text(encoding="utf-8")) for p in files[:limit]]


def check_artifact(path: Path, kind: str) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Missing or empty artifact: " + path.name)
    metadata = {}
    if kind == "npz":
        from .array_artifacts import inspect_npz
        metadata = inspect_npz(path)
    elif kind == "png":
        from PIL import Image, ImageStat
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            if min(im.size) < 32 or max(im.size) > 8192:
                raise ValueError("Unexpected image dimensions")
            if max(ImageStat.Stat(im.convert("RGB")).var) == 0:
                raise ValueError("Image contains no variation")
    elif kind == "csv":
        import csv
        with path.open(encoding="utf-8", newline="") as f:
            rows = csv.reader(f)
            header = next(rows)
            count = 0
            for row in rows:
                if len(row) != len(header) or not all(math.isfinite(float(v)) for v in row):
                    raise ValueError("Malformed/nonfinite numeric CSV")
                count += 1
            if not count:
                raise ValueError("CSV has no data rows")
    elif kind == "keyword":
        text = path.read_text(encoding="utf-8", errors="replace").upper()
        if "*KEYWORD" not in text or "*END" not in text:
            raise ValueError("Invalid keyword artifact")
    elif kind == "json":
        json.loads(path.read_text(encoding="utf-8"))
    result = {**fingerprint(path), **metadata, "kind": kind, "validated": True}
    if kind == "npz":
        result.pop("hash_note", None)
    return result
