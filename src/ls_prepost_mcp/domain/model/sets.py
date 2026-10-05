"""New node / part / element / segment sets (text written in standard format, then verified)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .blocks import Block, SourceFile
from .fields import FieldError

if TYPE_CHECKING:
    from .deck import KeywordDeck

SET_KINDS = {"node": ("*SET_NODE_LIST", "node_set"), "part": ("*SET_PART_LIST", "part_set"),
             "shell": ("*SET_SHELL_LIST", "shell_set"), "solid": ("*SET_SOLID", "solid_set"),
             "segment": ("*SET_SEGMENT", "segment_set")}


def next_id(deck: KeywordDeck, kind: str) -> int:
    """Smallest unused set ID above every existing set of the same kind."""
    defined = deck.references(include_mesh=False).defined.get(SET_KINDS[kind][1], set())
    return max(defined, default=0) + 1


def set_text(kind: str, sid: int, items: list, title: str | None = None) -> str:
    """Keyword text of a set; segments are 4-node rows (triangles repeat the third node)."""
    keyword = SET_KINDS[kind][0] + ("_TITLE" if title else "")
    lines = [keyword] + ([title] if title else []) + [f"{sid:>10}"]
    if kind == "segment":
        for segment in items:
            if len(segment) != 4:
                raise FieldError("Segments need 4 node IDs (repeat the third for triangles)")
            lines.append("".join(f"{int(n):>10}" for n in segment))
    else:
        values = [int(i) for i in items]
        lines += ["".join(f"{v:>10}" for v in values[k:k + 8]) for k in range(0, len(values), 8)]
    return "\n".join(lines) + "\n"


def create_set(deck: KeywordDeck, kind: str, items: list, *, sid: int | None = None, title: str | None = None,
               file: SourceFile | None = None) -> tuple[int, list[Block]]:
    """Insert a new set and verify its members (or segment rows) by reading them back."""
    if kind not in SET_KINDS:
        raise FieldError(f"Unknown set kind {kind!r}; use one of {sorted(SET_KINDS)}")
    if not len(items):
        raise FieldError("The selection is empty; no set created")
    existing = deck.references(include_mesh=False).defined.get(SET_KINDS[kind][1], set())
    if sid is None:
        sid = max(existing, default=0) + 1
    elif sid in existing:
        raise FieldError(f"{SET_KINDS[kind][1]} {sid} already exists")
    target = file or deck.main
    blocks = deck.insert(set_text(kind, sid, list(items), target.to_text(title) if title else None), file=target)
    block = blocks[0]
    if kind == "segment":
        found = len(deck.layout(block).rows)
        expected = len(items)
    else:
        found = deck.members(block)
        expected = [int(i) for i in items]
    if found != expected:
        deck.delete(block, force=True)
        raise FieldError(f"New {SET_KINDS[kind][0]} failed verification")
    return sid, blocks
