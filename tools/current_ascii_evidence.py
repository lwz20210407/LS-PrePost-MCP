"""Resolve explicitly selected Q06 evidence without rewriting historical captures."""
from __future__ import annotations

import hashlib
import json
import re
import stat
from pathlib import Path, PurePosixPath

CONTEXT = Path("docs/decisions/evidence/q06-current.json")
ROLES = frozenset(("sleout", "nodout", "spcforc"))


def _safe_file(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts or parts.parts[:3] != ("docs", "decisions", "evidence"):
        raise ValueError("Evidence reference leaves the evidence directory")
    cursor = root.resolve()
    # Reject links before traversing the next component, including a network link target.
    for part in parts.parts:
        cursor /= part
        info = cursor.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Evidence references cannot traverse links or reparse points")
    if not stat.S_ISREG(info.st_mode) or info.st_size > 512 * 1024:
        raise ValueError("Evidence file must be regular and no larger than 512 KiB")
    return cursor


def _context(root: Path) -> dict:
    value = json.loads(_safe_file(root, CONTEXT.as_posix()).read_text(encoding="utf8"))
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValueError("Unsupported Q06 evidence context")
    return value


def _entry(root: Path, item: dict) -> dict:
    relative = item["path"]
    if not isinstance(relative, str) or not re.fullmatch(r"[a-z0-9_./-]+/evidence\.json", relative):
        raise ValueError("Evidence reference must be a repository-relative JSON path")
    target = _safe_file(root, relative)
    raw = target.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(raw).hexdigest() != item["evidence_sha256_lf"]:
        raise ValueError("Selected evidence JSON differs from its recorded LF identity")
    report_path = PurePosixPath(relative).parent / "report.md"
    report = _safe_file(root, report_path.as_posix()).read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(report).hexdigest() != item["report_sha256_lf"]:
        raise ValueError("Selected evidence report differs from its recorded LF identity")
    value = json.loads(raw)
    # Historical raw hashes keep their original meaning; compare an explicit LF field only.
    recorded_report = value.get("report_sha256_lf")
    if recorded_report is not None and recorded_report != item["report_sha256_lf"]:
        raise ValueError("Evidence and context disagree on the published report LF identity")
    return value


def read_current_ascii_evidence(root: Path, database: str) -> dict:
    """Read a sealed current record; consumers still check current product Git/LF sources."""
    if database not in ROLES:
        raise ValueError("No current Q06 evidence role for this database")
    context = _context(root)
    return _entry(root, context["current"][database])


def read_historical_ascii_evidence(root: Path, name: str) -> dict:
    """Verify archived bytes and read their original revision; never imply current code."""
    context = _context(root)
    return _entry(root, context["history"][name])
