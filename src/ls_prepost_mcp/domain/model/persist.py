"""Diff and save for :class:`~ls_prepost_mcp.domain.model.deck.KeywordDeck`."""
from __future__ import annotations

import difflib
import hashlib
import os
import re
import stat
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from . import access
from .blocks import SourceFile
from .includes import identity
from .text import split_lines

if TYPE_CHECKING:
    from .deck import KeywordDeck


def modified_files(deck: KeywordDeck) -> list[SourceFile]:
    """Files whose current bytes differ from what was read."""
    return [f for f in deck.files.values() if f.modified and f.data() != f.original]


def diff(deck: KeywordDeck) -> str:
    """Unified diff of every modified file."""
    parts: list[str] = []
    for source in modified_files(deck):
        parts.extend(_unified(split_lines(source.original_text()), split_lines(source.text()),
                              str(source.path), str(source.path) + " (edited)"))
    return "".join(parts)


def diff_preview(deck: KeywordDeck, limit: int) -> tuple[str, bool]:
    """The first ``limit`` characters of :func:`diff` and whether anything was cut.

    A change region of more than PREVIEW_LINES lines (clean_coordinates over 564000 nodes plus a
    564000-line insert: about 210 s of difflib) is diffed only over its first PREVIEW_LINES lines
    on each side; that preview is what the caller keeps anyway.
    """
    parts: list[str] = []
    cut, size = False, 0
    files = modified_files(deck)
    for number, source in enumerate(files, 1):
        lines, partial = _unified(split_lines(source.original_text()), split_lines(source.text()),
                                  str(source.path), str(source.path) + " (edited)", window=PREVIEW_LINES,
                                  with_flag=True)
        parts.extend(lines)
        size += sum(map(len, lines))
        cut = cut or partial
        if size > limit:
            cut = cut or number < len(files)
            break
    text = "".join(parts)
    return text[:limit], cut or len(text) > limit


PREVIEW_LINES = 5000
_HUNK = re.compile(r"^@@ -(\d+)(,\d+)? \+(\d+)(,\d+)? @@")


def _unified(old: list[str], new: list[str], fromfile: str, tofile: str, context: int = 3,
             window: int | None = None, with_flag: bool = False) -> list[str] | tuple[list[str], bool]:
    """``difflib.unified_diff`` of the part between the common first and last lines, renumbered.

    Edits touch a few blocks of large decks; difflib over the whole of a 564000-line file took
    about 220 s, the trimmed middle takes milliseconds. Output equals difflib's on the full lists.
    With ``window`` only the first ``window`` lines of each side of the change region are diffed
    (a preview; ``with_flag`` also returns whether it was cut).
    """
    head, limit = 0, min(len(old), len(new))
    while head < limit and old[head] == new[head]:
        head += 1
    tail = 0
    while tail < limit - head and old[len(old) - 1 - tail] == new[len(new) - 1 - tail]:
        tail += 1
    start, keep = max(0, head - context), max(0, tail - context)
    old_part, new_part = old[start:len(old) - keep], new[start:len(new) - keep]
    partial = window is not None and max(len(old_part), len(new_part)) > window
    if partial:
        old_part, new_part = old_part[:window], new_part[:window]
    lines = list(difflib.unified_diff(old_part, new_part, fromfile=fromfile, tofile=tofile, n=context))

    def shift(match: re.Match) -> str:  # empty ranges (",0") name the line before: the same shift applies
        a, b, c, d = match.groups()
        return f"@@ -{int(a) + start}{b or ''} +{int(c) + start}{d or ''} @@"

    renumbered = [_HUNK.sub(shift, line) if line.startswith("@@") else line for line in lines]
    return (renumbered, partial) if with_flag else renumbered


def _relocation_plan(deck: KeywordDeck, out_dir: Path) -> tuple[dict[Path, Path], list[str], dict[Path, Path]]:
    # Only the lookup that won *at this reference* determines whether a raw
    # save retains an external source. A later path card cannot act retroactively,
    # nor can an unused absolute candidate override an including_dir match.
    active_absolute = [p.is_absolute() for p in deck.base_search_dirs]
    external_refs: set[int] = set()
    for ref in deck.includes:
        if ref.kind == "path":
            active_absolute.append(Path(ref.name).is_absolute())
            continue
        res = ref.resolution
        if res is not None and (res.rule == "absolute" or (
                res.rule == "include_path" and res.search_directory_index is not None
                and res.search_directory_index < len(active_absolute)
                and active_absolute[res.search_directory_index])):
            external_refs.add(id(ref))
    absolute = {identity(r.child.path) for r in deck.includes if r.child and id(r) in external_refs}
    # An external parent also keeps its relative descendants external. Otherwise
    # their edited output copies would be disconnected from the saved main deck.
    while True:
        descendants = {identity(r.child.path) for r in deck.includes
                       if r.child and identity(r.parent.path) in absolute
                       and r.resolution is not None and r.resolution.rule == "including_dir"}
        expanded = absolute | descendants
        if expanded == absolute:
            break
        absolute = expanded
    external = [str(source.path) for key, source in deck.files.items() if key in absolute]
    for key in absolute:
        if deck.files[key].modified:
            raise ValueError(f"{deck.files[key].path} is included by absolute path or search path and was edited; save in place")
    reachable = {identity(deck.main.path)} | {identity(r.child.path) for r in deck.includes if r.child}
    # A repeated source may have both external and local incoming references.
    # The local spelling still needs its own unchanged copy in the saved tree.
    local = {identity(deck.main.path)}
    while True:
        expanded = local | {
            identity(r.child.path) for r in deck.includes if r.child and id(r) not in external_refs
            and r.resolution is not None and (identity(r.parent.path) in local
                                             or r.resolution.rule in {"main_dir", "include_path"})}
        if expanded == local:
            break
        local = expanded
    movable = [f.path for k, f in deck.files.items() if k in reachable and (k not in absolute or k in local)]
    opaque = []
    for ref in deck.includes:
        if ref.kind != "opaque" or not ref.resolution or not ref.resolution.path:
            continue
        path = ref.resolution.path
        external_ref = (id(ref) in external_refs
                        or (identity(ref.parent.path) in absolute and ref.resolution.rule == "including_dir"))
        if external_ref:
            external.append(str(path))
        if not external_ref or (id(ref) not in external_refs and identity(ref.parent.path) in local):
            opaque.append(path)
    external = list(dict.fromkeys(external))
    directories = []
    for ref in deck.includes:
        if ref.kind != "path" or Path(ref.name).is_absolute() or ref.error:
            continue
        directory = deck.main_dir / ref.name
        access.require(directory)
        if directory.is_dir():
            directories.append(directory)
    # A link inside the relative layout cannot be recreated by resolving paths:
    # lib/x.k would be copied beneath real_lib while the raw card still says lib.
    # Reject before physical commonpath (also before cross-drive junction errors).
    lexical = Path(os.path.commonpath([str(p.absolute().parent) for p in movable + opaque]
                                     + [str(p.absolute()) for p in directories]))
    for path in movable + opaque + directories:
        access.require(path)
        current = path.absolute()
        while current != lexical:
            info = current.lstat()  # metadata of an already-admitted input's ancestry, not file contents
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("save_as does not support symlink/junction paths inside the relative layout")
            parent = current.parent
            if parent == current:
                break
            current = parent
    directories = [p.resolve() for p in directories]
    # Empty relative search directories also determine layout. Omitting them
    # can leave an unchanged path card dangling after a successful save-as.
    locations = [str(p.parent.resolve()) for p in movable + opaque] + [str(p) for p in directories]
    root = Path(os.path.commonpath(locations))
    plan = {p: out_dir / p.resolve().relative_to(root) for p in movable + opaque}
    directory_plan = {p: out_dir / p.relative_to(root) for p in directories}
    return plan, external, directory_plan


def save_as(deck: KeywordDeck, out_dir: str | os.PathLike[str], overwrite: bool = False) -> dict:
    """Write the deck to a new directory keeping relative layout; untouched files are copied verbatim.

    Nothing is written if any destination exists (unless ``overwrite``) or would be an input file.
    The written deck is reloaded as a check.
    """
    out = Path(out_dir)
    plan, external, directories = _relocation_plan(deck, out)
    sources = {identity(f.path): f for f in deck.files.values()}
    for source, dest in plan.items():
        if identity(dest) == identity(source):
            raise ValueError("Output directory would overwrite the input files; use save_in_place")
        if dest.exists() and not overwrite:
            raise FileExistsError(f"{dest} exists")
    for dest in directories.values():
        dest.mkdir(parents=True, exist_ok=True)
    written = []
    for source, dest in plan.items():
        dest.parent.mkdir(parents=True, exist_ok=True)
        item = sources.get(identity(source))
        if item is None:
            access.require(source)  # opaque targets (*INCLUDE_BINARY, ...) are copied unread
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
            "search_directories": [{"source": str(p), "dest": str(d)} for p, d in directories.items()],
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
        try:
            atomic_write(source.path, data)
        except OSError as exc:
            # Only when the file still holds the backed-up bytes is this call's backup
            # redundant; drop it then, so that a retry is not refused above.
            try:
                unchanged = _retry_sharing(source.path.read_bytes) == source.original
            except OSError:
                unchanged = False
            if not (unchanged and _discard(backup)):
                exc.add_note(f"{backup} was kept; it holds the bytes read before this save")
            raise
        report.append({"path": str(source.path), "backup": str(backup), "sha256": hashlib.sha256(data).hexdigest()})
        source.original, source.modified = data, False
    return {"written": report}


# Antivirus and indexers can briefly hold a handle that denies replacing, reading or deleting
# a file that was just written or read (WinError 5/32/33). Total backoff 0.62 s; other errors
# are never retried.
SHARING_DELAYS = (0.02, 0.04, 0.08, 0.16, 0.32)
T = TypeVar("T")


def _retry_sharing(operation: Callable[[], T]) -> T:
    for delay in SHARING_DELAYS:
        try:
            return operation()
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in (5, 32, 33):
                raise
            time.sleep(delay)
    return operation()


def _discard(path: Path) -> bool:
    """Best-effort removal of a file this module created; never masks the caller's error."""
    try:
        _retry_sharing(lambda: path.unlink(missing_ok=True))
    except OSError:
        return False
    return True


def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        tmp.write_bytes(data)
        _retry_sharing(lambda: os.replace(tmp, path))
    except BaseException:
        _discard(tmp)
        raise
