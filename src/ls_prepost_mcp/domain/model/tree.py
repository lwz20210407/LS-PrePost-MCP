"""Include tree: recursive loading, reading-order traversal and a JSON view."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from . import access
from .blocks import Block, SourceFile
from .includes import Resolution, classify, file_names, identity, is_network, joined, resolve
from .text import deck_format

if TYPE_CHECKING:
    from .deck import KeywordDeck


@dataclass
class IncludeRef:
    parent: SourceFile
    block: Block
    kind: str  # "file" | "path" | "opaque"
    name: str
    resolution: Resolution | None = None
    child: SourceFile | None = None
    cycle: bool = False
    repeated: bool = False
    name_line: int | None = None  # 1-based line of the file-name card
    error: str | None = None  # set only when the deck records unreadable includes
    error_kind: str | None = None  # "unreadable" | "limit" | "network_path" | "reference_limit"


class IncludeLimit(ValueError):
    """More include files than the deck's ``max_files``."""


class ReferenceLimit(ValueError):
    """More include references than the deck's ``max_references`` (counted as :func:`walk` describes)."""


def reference_budget(value: object) -> int | None:
    """Validate a ``max_references`` argument: None (no limit) or an integer >= 0."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"max_references must be None or an integer >= 0, not {value!r}")
    return value


def walk(deck: KeywordDeck, source: SourceFile, stack: list[str]) -> None:
    """Load every include reachable from ``source`` (depth first, in reading order).

    Every file name of an include keyword (and every ``*INCLUDE_PATH`` directory) adds one to
    ``deck.reference_count`` each time LS-DYNA reads it: a repeated include also adds everything
    its file references, because that file is read again. Repeated files are not walked again;
    their count is remembered from the first walk. With ``deck.max_references`` set, the reference
    that takes the count over the limit is recorded (or raised) and the walk stops: neither that
    name nor anything after it is resolved, stat'ed or read.
    """
    start = deck.reference_count
    for block in source.keyword_blocks():
        if block.name == "*KEYWORD" and source is deck.main:
            deck.format = deck_format(block.keyword.extra if block.keyword else "")
        kind = classify(block.name)
        if kind is None:
            continue
        for name, lines in file_names(block.name, block.data()):
            line = block.line_number + lines[0] if lines else None
            if not _count(deck, 1):  # before any file-system access for this name
                _stop(deck, IncludeRef(source, block, kind, name, Resolution(None, "reference_limit"),
                                       name_line=line), listed=False)
                return
            if is_network(name) and (not deck.network or access.active()):
                # A UNC name in an untrusted deck would make Windows contact (and authenticate to)
                # the named host; record it without touching the file system.
                if access.active() and not deck.record_unreadable:
                    access.require(name)  # the guard refuses it before anything resolves the name
                deck.includes.append(IncludeRef(source, block, kind, name, Resolution(None, "network_path"), None,
                                                name_line=line, error="network path not accessed",
                                                error_kind="network_path"))
                deck.warnings.append(f"Network include {name!r} at {deck._where(block)} was not accessed")
                continue
            if kind == "path":
                directory = Path(name)
                deck.search_dirs.append(directory if directory.is_absolute() else joined(deck.main_dir, directory))
                deck.includes.append(IncludeRef(source, block, kind, name, name_line=line))
                continue
            try:
                result = resolve(name, source.path.parent, deck.main_dir, deck.search_dirs)
            except OSError as error:  # e.g. a directory that may not be listed
                if not deck.record_unreadable:
                    raise
                deck.includes.append(IncludeRef(source, block, kind, name, Resolution(None, "unreadable"),
                                                name_line=line, error=str(error), error_kind="unreadable"))
                deck.warnings.append(f"Unreadable include {name!r} at {deck._where(block)}: {error}")
                continue
            ref = IncludeRef(source, block, kind, name, result, name_line=line)
            deck.includes.append(ref)
            if result.ambiguous:
                deck.warnings.append(f"Ambiguous include {name!r} at {deck._where(block)}: {result.candidates}")
            if result.path is None:
                deck.warnings.append(f"Missing include {name!r} at {deck._where(block)}")
                continue
            if kind == "opaque":
                continue
            key = identity(result.path)
            if key in stack:
                ref.cycle = True
                deck.warnings.append(f"Include cycle via {name!r} at {deck._where(block)}")
                continue
            child = deck.files.get(key)
            if child is not None and key in deck._parents:
                ref.child, ref.repeated = child, True
                # Not on the stack, so its first walk has finished and its count is known.
                if not _count(deck, deck._expanded.get(key, 0)):
                    ref.child = None  # not expanded again by iter_blocks either
                    _stop(deck, ref, listed=True)
                    return
                deck.warnings.append(f"{name!r} is included more than once; LS-DYNA reads it each time")
                continue
            if child is None:
                try:
                    if len(deck.files) >= deck.max_files:
                        raise IncludeLimit(f"More than {deck.max_files} include files")
                    child = SourceFile.read(result.path)
                except (OSError, ValueError) as error:
                    if not deck.record_unreadable:
                        raise
                    ref.error = str(error)
                    ref.error_kind = "limit" if isinstance(error, IncludeLimit) else "unreadable"
                    what = "Include over the file limit" if ref.error_kind == "limit" else "Unreadable include"
                    deck.warnings.append(f"{what} {name!r} at {deck._where(block)}: {error}")
                    continue
                deck.files[key] = child
            ref.child = child
            deck._parents[key] = identity(source.path)
            walk(deck, child, stack + [key])
            if deck.reference_stop is not None:
                return
    deck._expanded[identity(source.path)] = deck.reference_count - start


def _count(deck: KeywordDeck, references: int) -> bool:
    """Add ``references`` to the deck's count; False once the count is over ``max_references``."""
    deck.reference_count += references
    return deck.max_references is None or deck.reference_count <= deck.max_references


def _stop(deck: KeywordDeck, ref: IncludeRef, *, listed: bool) -> None:
    message = (f"More than {deck.max_references} include references: {deck.reference_count} counted when "
               "reading stopped (each name counts every time it is read, repeated and unresolved ones too)")
    if not deck.record_unreadable:
        raise ReferenceLimit(message)
    ref.error, ref.error_kind = message, "reference_limit"
    if not listed:
        deck.includes.append(ref)
    deck.reference_stop = ref
    deck.warnings.append(f"Include reference limit reached at {deck._where(ref.block)}: {message}")


def iter_blocks(deck: KeywordDeck, source: SourceFile, stack: list[str]) -> Iterator[Block]:
    """Keyword blocks in LS-DYNA reading order, include files expanded in place."""
    by_block: dict[int, list[IncludeRef]] = {}
    for ref in deck.includes:
        if ref.parent is source:
            by_block.setdefault(id(ref.block), []).append(ref)
    for block in source.keyword_blocks():
        yield block
        for ref in by_block.get(id(block), []):
            if ref.child is None or ref.cycle or ref.kind != "file":
                continue
            key = identity(ref.child.path)
            if key not in stack:
                yield from iter_blocks(deck, ref.child, stack + [key])


def include_tree(deck: KeywordDeck) -> dict:
    """Nested include structure with resolution rule and problems for each reference."""
    def node(source: SourceFile, stack: list[str]) -> list[dict]:
        entries = []
        for ref in deck.includes:
            if ref.parent is not source:
                continue
            res = ref.resolution
            entry = {"name": ref.name, "kind": ref.kind, "keyword": ref.block.name, "line": ref.block.line_number,
                     "path": str(ref.child.path) if ref.child else (str(res.path) if res and res.path else None),
                     "rule": res.rule if res else None, "missing": bool(res and res.path is None),
                     "ambiguous": bool(res and res.ambiguous), "cycle": ref.cycle, "repeated": ref.repeated}
            if ref.child and not ref.cycle and not ref.repeated:
                entry["includes"] = node(ref.child, stack + [identity(ref.child.path)])
            entries.append(entry)
        return entries
    return {"path": str(deck.main.path), "includes": node(deck.main, [identity(deck.main.path)])}
