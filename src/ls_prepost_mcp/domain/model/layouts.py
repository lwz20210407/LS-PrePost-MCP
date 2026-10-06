"""Layout data structures shared by the schema, table and reference modules."""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field

from .blocks import Block
from .fields import FieldSlot, is_free_format, read_text


class Unsupported(ValueError):
    """Named-field access is not available for this block; use positional editing."""


@dataclass(frozen=True)
class FieldInfo:
    name: str
    kind: str  # "int" | "float" | "str"
    slot: FieldSlot
    card: str
    default: object = None


@dataclass(frozen=True)
class Column:
    """One field of a row template: name, kind and fixed-format position."""

    name: str
    kind: str
    offset: int
    width: int
    default: object = None


class RowMap(Mapping[int, list[FieldInfo]]):
    """Rows of a table-like block: key -> field infos, built only when a row is accessed.

    Each row spans one line per template entry (e.g. ``*PART`` = heading + card).
    Large blocks (hundreds of thousands of nodes/elements) therefore cost one tuple of
    line indices per row instead of one object per field.
    """

    def __init__(self, block: Block, template: list[list[Column]], cards: list[str],
                 rows: dict[int, tuple[int, ...]]) -> None:
        self.block, self.template, self.cards, self._rows = block, template, cards, rows

    def __getitem__(self, key: int) -> list[FieldInfo]:
        result = []
        for columns, card, index in zip(self.template, self.cards, self._rows[key]):
            free = is_free_format(self.block.lines[index])
            for token, column in enumerate(columns):
                if column.name.startswith("unused"):
                    continue
                slot = FieldSlot(index, column.offset, column.width, token if free else None)
                result.append(FieldInfo(column.name, column.kind, slot, card, column.default))
        return result

    def __iter__(self) -> Iterator[int]:
        return iter(self._rows)

    def __len__(self) -> int:
        return len(self._rows)

    def __contains__(self, key: object) -> bool:
        return key in self._rows

    def line_indices(self, key: int) -> tuple[int, ...]:
        return self._rows[key]

    def lines(self) -> Iterator[tuple[int, tuple[int, ...]]]:
        """``(key, line indices)`` without building field objects."""
        return iter(self._rows.items())

    def locate(self, name: str) -> tuple[int, int, int, int] | None:
        """``(line position in row, offset, width, token)`` of the first column called ``name``."""
        for position, columns in enumerate(self.template):
            for token, column in enumerate(columns):
                if column.name == name:
                    return position, column.offset, column.width, token
        return None

    def cell(self, indices: tuple[int, ...], located: tuple[int, int, int, int]) -> str:
        position, offset, width, token = located
        if position >= len(indices):
            return ""  # optional trailing card absent in this row
        line = self.block.lines[indices[position]]
        return read_text(line, FieldSlot(0, offset, width, token if is_free_format(line) else None))


@dataclass
class Layout:
    """Field positions of one block: header ``fields`` and, for tables, ``rows`` (key -> fields)."""

    keyword: str
    fields: list[FieldInfo] = field(default_factory=list)
    rows: Mapping[int, list[FieldInfo]] = field(default_factory=dict)
    key: str | None = None
    source: str = ""
    missing_cards: list[str] = field(default_factory=list)

    def lookup(self, name: str, card: str | None = None, row: int | None = None) -> FieldInfo:
        name = name.lower()
        if row is None:
            pool = self.fields
            if self.key is not None and not any(f.name == name for f in pool):
                raise KeyError(f"{self.keyword} holds rows; give row=<{self.key}>")
        else:
            if self.key is None:
                raise KeyError(f"{self.keyword} has no rows")
            if row not in self.rows:
                raise KeyError(f"No row with {self.key}={row} in {self.keyword}")
            pool = self.rows[row]
        matches = [f for f in pool if f.name == name and (card is None or f.card == card)]
        if not matches:
            raise KeyError(f"No field {name!r} in {self.keyword}")
        if len(matches) > 1:
            raise KeyError(f"Field {name!r} occurs on cards {[m.card for m in matches]}; give card=")
        return matches[0]
