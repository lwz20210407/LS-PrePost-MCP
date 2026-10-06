"""Read-only check of an ``*INCLUDE`` tree before a native reader opens the main deck."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PureWindowsPath

from .blocks import SourceFile
from .deck import KeywordDeck
from .includes import classify, identity

# Measured with LS-DYNA R11 on one-element decks (2026-10-06): an included UTF-16 file stops the
# run (Error 10450/10133), while an *INCLUDE without a file-name card is skipped silently.
ERRORS = ("missing", "cycle", "unreadable", "limit", "network_path", "utf16_text")
WARNINGS = ("empty_include", "ambiguous", "repeated", "not_followed", "missing_search_dir")
TREE_SHA256_VERSION = 1


def preflight_includes(path: str | os.PathLike[str], include_paths: tuple[str, ...] = (),
                       max_files: int = 5000, allow_network: bool = False) -> dict:
    """Resolve every include reachable from ``path`` and report problems; never writes and never
    raises for unreadable files.

    ``files``: main deck, keyword includes and existing opaque targets (``*INCLUDE_BINARY``, ...)
    in order of first reference while reading, each with size and SHA-256. ``tree_sha256``
    (scheme :data:`TREE_SHA256_VERSION`) is the SHA-256 of those digests joined by newlines, so
    it identifies the tree's content wherever it is stored. Files are identified by normalized
    absolute path, not by link target.

    ``problems`` is flat: ``kind`` is in :data:`ERRORS` (LS-DYNA cannot read the tree as
    written, or it cannot be checked safely) or :data:`WARNINGS`; ``line`` is the keyword line
    and ``name_line`` the file-name card. ``missing`` has a ``hint``: ``placeholder``,
    ``absolute_path`` or ``not_found``. UNC names are not accessed (``network_path``) unless
    ``allow_network``. ``ok`` means no errors.
    """
    main = Path(path)
    try:
        source = SourceFile.read(main)
    except (OSError, ValueError) as error:
        return _report(main, [], [_problem("unreadable", _at(main.parent, main), reason=str(error))])
    try:
        deck = KeywordDeck(source, [Path(p) for p in include_paths], max_files,
                           record_unreadable=True, network=allow_network)
    except RecursionError:
        files = [_entry(main.parent, main, "main", source.original)]
        reason = "includes nested, or parameter expressions chained, too deeply to follow"
        return _report(main, files, [_problem("limit", _at(main.parent, main), reason=reason)])
    root = deck.main_dir
    files = [_entry(root, deck.main.path, "main", deck.main.original)]
    seen = {identity(deck.main.path)}
    problems: list[dict] = []
    for ref in deck.includes:
        where = _at(root, ref.parent.path, ref.block.line_number, ref.block.name, ref.name, ref.name_line)
        res = ref.resolution
        target = {"path": str(res.path)} if res is not None and res.path is not None else {}
        if ref.error:
            problems.append(_problem(ref.error_kind or "unreadable", where, reason=ref.error, **target))
            continue
        if ref.kind == "path":
            directory = Path(ref.name) if Path(ref.name).is_absolute() else root / ref.name
            if not _is_dir(directory):
                problems.append(_problem("missing_search_dir", where, path=str(directory)))
            continue
        if res is None or res.path is None:
            problems.append(_problem("missing", where, hint=_missing_hint(ref.name)))
            continue
        if res.ambiguous:
            problems.append(_problem("ambiguous", where, rule=res.rule, candidates=list(res.candidates), **target))
        if ref.cycle:
            problems.append(_problem("cycle", where, **target))
        if ref.repeated:
            problems.append(_problem("repeated", where, **target))
        if ref.kind == "opaque":
            problems.append(_problem("not_followed", where, **target))
        if identity(res.path) in seen or (ref.child is None and ref.kind != "opaque"):
            continue
        seen.add(identity(res.path))
        if ref.child is not None:
            files.append(_entry(root, ref.child.path, "include", ref.child.original))
            continue
        try:
            files.append(_entry(root, res.path, "opaque", None))
        except OSError as error:
            problems.append(_problem("unreadable", where, reason=str(error), **target))
    referenced = {id(ref.block) for ref in deck.includes}
    for loaded in deck.files.values():  # each file once, even when it is included repeatedly
        if loaded.wide:
            problems.append(_problem("utf16_text", _at(root, loaded.path),
                                     reason=f"{loaded.wide.upper()} text; LS-DYNA reads 8-bit text"))
        for block in loaded.keyword_blocks():
            if classify(block.name) and id(block) not in referenced:
                # No file-name card; a "$" line such as "${GEOMETRY}" is a comment to LS-DYNA.
                text = "".join(block.lines[1:])
                hint = "placeholder" if "${" in text or "{{" in text else "no_file_card"
                problems.append(_problem("empty_include", _at(root, loaded.path, block.line_number, block.name),
                                         hint=hint))
    return _report(main, files, problems)


def _report(main: Path, files: list[dict], problems: list[dict]) -> dict:
    digest = hashlib.sha256("\n".join(f["sha256"] for f in files).encode("ascii")).hexdigest()
    errors = sum(p["severity"] == "error" for p in problems)
    return {"path": str(main), "ok": errors == 0, "files": files,
            "tree_sha256": digest if files else None, "tree_sha256_version": TREE_SHA256_VERSION,
            "problems": problems, "counts": {"files": len(files), "errors": errors,
                                             "warnings": len(problems) - errors},
            "read_only": True}


def _problem(kind: str, where: dict, **detail: object) -> dict:
    return {"kind": kind, "severity": "error" if kind in ERRORS else "warning", **where, **detail}


def _at(root: Path, file: Path, line: int | None = None, keyword: str | None = None,
        name: str | None = None, name_line: int | None = None) -> dict:
    return {"file": str(file), "relative": _relative(root, file), "line": line, "name_line": name_line,
            "keyword": keyword, "name": name}


def _entry(root: Path, path: Path, role: str, data: bytes | None) -> dict:
    digest, size = hashlib.sha256(), 0
    if data is None:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
                size += len(chunk)
    else:
        digest.update(data)
        size = len(data)
    return {"path": str(path), "relative": _relative(root, path), "role": role, "size": size,
            "sha256": digest.hexdigest()}


def _relative(root: Path, path: Path) -> str | None:
    """POSIX path relative to the main deck's directory, or None outside it."""
    try:
        return Path(os.path.abspath(path)).relative_to(os.path.abspath(root)).as_posix()
    except ValueError:
        return None


def _is_dir(directory: Path) -> bool:
    try:
        return directory.is_dir()
    except OSError:
        return False


def _missing_hint(name: str) -> str:
    if "${" in name or "{{" in name:
        return "placeholder"
    if Path(name).is_absolute() or PureWindowsPath(name).drive or name.startswith(("/", "\\")):
        return "absolute_path"
    return "not_found"
