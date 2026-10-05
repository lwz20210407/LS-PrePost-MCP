"""Include tree: recursive loading, reading-order traversal and a JSON view."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .blocks import Block, SourceFile
from .includes import Resolution, classify, file_names, identity, resolve
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


def walk(deck: KeywordDeck, source: SourceFile, stack: list[str]) -> None:
    """Load every include reachable from ``source`` (depth first, in reading order)."""
    for block in source.keyword_blocks():
        if block.name == "*KEYWORD" and source is deck.main:
            deck.format = deck_format(block.keyword.extra if block.keyword else "")
        kind = classify(block.name)
        if kind is None:
            continue
        for name, _ in file_names(block.name, block.data()):
            if kind == "path":
                directory = Path(name)
                deck.search_dirs.append(directory if directory.is_absolute() else deck.main_dir / directory)
                deck.includes.append(IncludeRef(source, block, kind, name))
                continue
            result = resolve(name, source.path.parent, deck.main_dir, deck.search_dirs)
            ref = IncludeRef(source, block, kind, name, result)
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
                deck.warnings.append(f"{name!r} is included more than once; LS-DYNA reads it each time")
                continue
            if child is None:
                if len(deck.files) >= deck.max_files:
                    raise ValueError(f"More than {deck.max_files} include files")
                child = SourceFile.read(result.path)
                deck.files[key] = child
            ref.child = child
            deck._parents[key] = identity(source.path)
            walk(deck, child, stack + [key])


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
