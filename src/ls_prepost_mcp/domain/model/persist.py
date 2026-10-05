"""Diff and save for :class:`~ls_prepost_mcp.domain.model.deck.KeywordDeck`."""
from __future__ import annotations

import difflib
import hashlib
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from .blocks import SourceFile
from .includes import identity
from .text import decode, split_lines

if TYPE_CHECKING:
    from .deck import KeywordDeck


def modified_files(deck: KeywordDeck) -> list[SourceFile]:
    """Files whose current bytes differ from what was read."""
    return [f for f in deck.files.values() if f.modified and f.data() != f.original]


def diff(deck: KeywordDeck) -> str:
    """Unified diff of every modified file."""
    parts: list[str] = []
    for source in modified_files(deck):
        parts.extend(difflib.unified_diff(split_lines(decode(source.original)), split_lines(source.text()),
                                          fromfile=str(source.path), tofile=str(source.path) + " (edited)"))
    return "".join(parts)


def _relocation_plan(deck: KeywordDeck, out_dir: Path) -> tuple[dict[Path, Path], list[str]]:
    absolute = {identity(r.child.path) for r in deck.includes if r.child and Path(r.name).is_absolute()}
    external = [str(deck.files[k].path) for k in absolute]
    for key in absolute:
        if deck.files[key].modified:
            raise ValueError(f"{deck.files[key].path} is included by absolute path and was edited; save in place")
    reachable = {identity(deck.main.path)} | {identity(r.child.path) for r in deck.includes if r.child}
    movable = [f.path for k, f in deck.files.items() if k not in absolute and k in reachable]
    opaque = [r.resolution.path for r in deck.includes
              if r.kind == "opaque" and r.resolution and r.resolution.path and not Path(r.name).is_absolute()]
    root = Path(os.path.commonpath([str(p.parent.resolve()) for p in movable + opaque]))
    plan = {p: out_dir / p.resolve().relative_to(root) for p in movable + opaque}
    return plan, external


def save_as(deck: KeywordDeck, out_dir: str | os.PathLike[str], overwrite: bool = False) -> dict:
    """Write the deck to a new directory keeping relative layout; untouched files are copied verbatim.

    Nothing is written if any destination exists (unless ``overwrite``) or would be an input file.
    The written deck is reloaded as a check.
    """
    out = Path(out_dir)
    plan, external = _relocation_plan(deck, out)
    sources = {identity(f.path): f for f in deck.files.values()}
    for source, dest in plan.items():
        if identity(dest) == identity(source):
            raise ValueError("Output directory would overwrite the input files; use save_in_place")
        if dest.exists() and not overwrite:
            raise FileExistsError(f"{dest} exists")
    written = []
    for source, dest in plan.items():
        dest.parent.mkdir(parents=True, exist_ok=True)
        item = sources.get(identity(source))
        data = item.data() if item is not None else source.read_bytes()
        atomic_write(dest, data)
        written.append({"source": str(source), "dest": str(dest), "modified": bool(item and item.modified),
                        "sha256": hashlib.sha256(data).hexdigest()})
    main_dest = plan[deck.main.path]
    reloaded = type(deck).load(main_dest)
    planned = {identity(source) for source in plan}
    skipped = [str(f.path) for k, f in deck.files.items() if f.modified and k not in planned
               and str(f.path) not in external]
    return {"main": str(main_dest), "files": written, "external_unchanged": external,
            "skipped_unreferenced_edits": skipped,
            "reload_files": len(reloaded.files), "reload_warnings": reloaded.warnings}


def save_in_place(deck: KeywordDeck, backup_suffix: str = ".orig") -> dict:
    """Overwrite only edited files after writing ``<name><backup_suffix>`` backups."""
    targets = modified_files(deck)
    for source in targets:
        backup = source.path.with_name(source.path.name + backup_suffix)
        if backup.exists():
            raise FileExistsError(f"Backup {backup} exists; refusing to overwrite it")
    report = []
    for source in targets:
        backup = source.path.with_name(source.path.name + backup_suffix)
        atomic_write(backup, source.original)
        data = source.data()
        atomic_write(source.path, data)
        report.append({"path": str(source.path), "backup": str(backup), "sha256": hashlib.sha256(data).hexdigest()})
        source.original, source.modified = data, False
    return {"written": report}


def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
