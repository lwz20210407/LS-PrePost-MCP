"""Row layouts for table keywords (``*ELEMENT_*``, ``*BOUNDARY_SPC_NODE``, ``*SET_SEGMENT``, ...).

Field widths come from the PyDYNA table schema, so large blocks are mapped without
parsing them. A sample of rows (first and last ``SAMPLE``) plus all header lines is then
parsed by PyDYNA and compared field by field; any disagreement refuses the layout.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

from .blocks import Block
from .fields import FieldError, FieldSlot, is_free_format, long_spans, parse_number, read_text
from .text import is_blank

SAMPLE = 20


@dataclass(frozen=True)
class Column:
    name: str
    kind: str
    offset: int
    width: int
    default: object = None


def _kind(python_type: type) -> str:
    return "int" if python_type is int else "float" if python_type is float else "str"


def _columns(schema: object, long: bool = False) -> list[Column]:
    fields = list(schema.fields)
    spans = long_spans([f.width for f in fields]) if long else [(f.offset, f.width) for f in fields]
    return [Column(f.name.lower(), _kind(f.type), o, w, f.default) for f, (o, w) in zip(fields, spans)]


def _widen(columns: list[Column]) -> list[Column]:
    spans = long_spans([c.width for c in columns])
    return [Column(c.name, c.kind, o, w, c.default) for c, (o, w) in zip(columns, spans)]


_SOLID_ONE_LINE = [Column("eid", "int", 0, 8), Column("pid", "int", 8, 8)] + [
    Column(f"n{i}", "int", 8 * (i + 1), 8) for i in range(1, 9)]


def _is_missing(value: object) -> bool:
    try:
        import pandas as pd
        return value is None or bool(pd.isna(value))
    except (TypeError, ValueError, ImportError):
        return value is None


def _same(text: str, expected: object, column: Column) -> bool:
    stripped = text.strip()
    if "&" in stripped:
        return True  # parameter references are checked by the scalar layouts
    if not stripped:
        return _is_missing(expected) or expected == column.default
    if column.kind == "str":
        return not _is_missing(expected) and str(expected).strip() == stripped
    try:
        value = parse_number(stripped)
    except FieldError:
        return False
    if value is None or _is_missing(expected):
        return False
    return math.isclose(float(value), float(expected), rel_tol=1e-9, abs_tol=1e-30)


def _slot(line: str, index: int, column: Column, token: int) -> FieldSlot:
    return FieldSlot(index, column.offset, column.width, token if is_free_format(line) else None)


def table_layout(block: Block, keyword_class: type, base: str, unsupported: type[Exception],
                 long: bool = False, title: str | None = None) -> dict:
    """Return ``{"fields": [...], "rows": {key: [...]}, "key": name}`` as plain tuples.

    ``fields``/``rows`` hold ``(name, kind, slot, card, default)`` tuples so that the
    caller can build its own field objects. Raises ``unsupported`` when the block does
    not fit a single-table shape or the sampled self-check fails.
    """
    instance = keyword_class()
    top = instance._cards
    kinds = [type(card).__name__ for card in top]
    tables = [i for i, kind in enumerate(kinds) if kind in ("TableCard", "TableCardGroup")]
    if len(tables) != 1 or {"CardSet", "SeriesCard"} & set(kinds):
        raise unsupported(f"{block.name}: table shape {kinds} is not supported")
    position = tables[0]
    table = top[position]
    if any(kind == "Card" for kind in kinds[position + 1:]):
        raise unsupported(f"{block.name}: cards after the table are not supported")
    suffix = set(block.name[len(base) + 1:].split("_")) if len(block.name) > len(base) else set()
    pre: list[tuple[int, list[object]]] = []
    for card in top:
        if type(card).__name__ != "OptionCardSet" or card._option_spec.name not in suffix:
            continue
        if str(card._option_spec.position.placement.value) != "pre":
            raise unsupported(f"{block.name}: post option {card._option_spec.name} with a table")
        pre.append((card._option_spec.position.index, list(card._cards)))
    if suffix - {card._option_spec.name for card in top if type(card).__name__ == "OptionCardSet"} - {""}:
        raise unsupported(f"{block.name}: unknown option suffix {sorted(suffix)}")
    head_cards = [c for _, cards in sorted(pre, key=lambda p: -p[0]) for c in cards]
    head_cards += [card for card in top[:position] if type(card).__name__ == "Card"]

    data = [(i, line) for i, line in block.data()]
    while data and is_blank(data[-1][1]):
        data.pop()
    if len(data) < len(head_cards):
        raise unsupported(f"{block.name}: missing header cards")
    fields = []
    for card, (index, line) in zip(head_cards, data):
        for token, column in enumerate(_columns(card._schema, long)):
            if not column.name.startswith("unused"):
                fields.append((column.name, column.kind, _slot(line, index, column, token), "header", column.default))
    rows_data = data[len(head_cards):]

    beyond_pid = FieldSlot(0, 40, 160) if long else FieldSlot(0, 16, 64)
    if type(table).__name__ == "TableCard":
        group = [_columns(table._schema, long)]
    elif block.name == "*ELEMENT_SOLID" and rows_data and read_text(rows_data[0][1], beyond_pid).strip():
        group = [_widen(_SOLID_ONE_LINE) if long else _SOLID_ONE_LINE]  # LS-PrePost one-line solid format
    else:
        subcards = table._cards
        if any(getattr(sub, "_active_func", None) is not None for sub in subcards):
            raise unsupported(f"{block.name}: conditional row cards are not supported")
        group = [_columns(sub._schema, long) for sub in subcards]
    per = len(group)
    if len(rows_data) % per:
        raise unsupported(f"{block.name}: {len(rows_data)} row lines do not form groups of {per}")

    rows: list[list[tuple]] = []
    for start in range(0, len(rows_data), per):
        record = []
        for columns, (index, line) in zip(group, rows_data[start:start + per]):
            for token, column in enumerate(columns):
                if not column.name.startswith("unused"):
                    record.append((column.name, column.kind, _slot(line, index, column, token), "row", column.default))
        rows.append(record)

    key = group[0][0].name
    try:
        keys = [parse_number(read_text(block.lines[r[0][2].line], r[0][2])) for r in rows]
    except FieldError:
        keys = []
    if keys and all(isinstance(k, int) for k in keys) and len(set(keys)) == len(keys):
        keyed = dict(zip(keys, rows))
    else:
        key, keyed = "row", {n: r for n, r in enumerate(rows, 1)}

    _self_check(block, keyword_class, position, head_cards, data, rows, per, fields, unsupported,
                title or block.lines[0].upper())
    return {"fields": fields, "rows": keyed, "key": key}


def _self_check(block: Block, keyword_class: type, position: int, head_cards: list, data: list,
                rows: list, per: int, fields: list, unsupported: type[Exception], title: str) -> None:
    picks = list(range(min(SAMPLE, len(rows))))
    picks += [i for i in range(max(len(rows) - SAMPLE, 0), len(rows)) if i not in picks]
    head_lines = [i for i, _ in data[:len(head_cards)]]
    row_lines = [rows[i][0][2].line for i in picks]
    indices = [0] + head_lines
    for line in row_lines:
        start = [i for i, _ in data].index(line)
        indices += [i for i, _ in data[start:start + per]]
    text = title + "".join(block.lines[i] for i in indices[1:])
    keyword = keyword_class()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            keyword.loads(text)
        except Exception as error:  # PyDYNA raises many exception types on malformed input
            raise unsupported(f"PyDYNA could not parse a sample of {block.name}: {error}") from error
    frame = keyword._cards[position].table
    if len(frame) != len(picks):
        raise unsupported(f"{block.name}: sample has {len(picks)} rows but PyDYNA read {len(frame)}")
    for sample_row, row_index in enumerate(picks):
        for name, kind, slot, _, default in rows[row_index]:
            if name not in frame.columns:
                continue
            text_value = read_text(block.lines[slot.line], slot)
            if not _same(text_value, frame.iloc[sample_row][name], Column(name, kind, 0, 0, default)):
                raise unsupported(f"Table self-check failed for {name!r} on line {slot.line} "
                                  f"({text_value!r} vs PyDYNA {frame.iloc[sample_row][name]!r})")
    for name, kind, slot, _, default in fields:
        expected = getattr(keyword, name, None) if hasattr(type(keyword), name) else None
        text_value = read_text(block.lines[slot.line], slot)
        if expected is not None and not _same(text_value, expected, Column(name, kind, 0, 0, default)):
            raise unsupported(f"Table header self-check failed for {name!r} ({text_value!r} vs {expected!r})")


__all__ = ["SAMPLE", "table_layout"]
