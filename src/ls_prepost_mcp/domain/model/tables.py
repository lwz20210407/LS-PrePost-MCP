"""Row layouts for table keywords (``*ELEMENT_*``, ``*BOUNDARY_SPC_NODE``, ``*SET_SEGMENT``, ...).

Field widths come from the PyDYNA table schema, so large blocks are mapped without
parsing them; rows are kept as line indices (:class:`RowMap`). A sample of rows (first
and last ``SAMPLE``) plus all header lines is parsed by PyDYNA and compared field by
field; any disagreement refuses the layout.
"""
from __future__ import annotations

import math
import warnings

from .blocks import Block
from .fields import FieldError, FieldSlot, is_free_format, long_spans, parse_number, read_text
from .layouts import Column, FieldInfo, Layout, RowMap, Unsupported
from .text import is_blank

SAMPLE = 20


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


def _same(text: str, expected: object, kind: str, default: object) -> bool:
    stripped = text.strip()
    if "&" in stripped or stripped.startswith("<"):
        return True  # parameter expressions are checked by the scalar layouts
    if not stripped:
        return _is_missing(expected) or expected == default
    if kind == "str":
        return not _is_missing(expected) and str(expected).strip() == stripped
    try:
        value = parse_number(stripped)
    except FieldError:
        return False
    if _is_missing(expected):
        return value == 0  # PyDYNA reads 0 in optional ID/link columns as "not set"
    if value is None:
        return False
    return math.isclose(float(value), float(expected), rel_tol=1e-9, abs_tol=1e-30)


def _shape(block: Block, keyword_class: type, base: str) -> tuple[int, object, list[object]]:
    """Index of the table card, the table card and the header cards (pre-options + cards)."""
    top = keyword_class()._cards
    kinds = [type(card).__name__ for card in top]
    tables = [i for i, kind in enumerate(kinds) if kind in ("TableCard", "TableCardGroup")]
    if len(tables) != 1 or {"CardSet", "SeriesCard"} & set(kinds):
        raise Unsupported(f"{block.name}: table shape {kinds} is not supported")
    position = tables[0]
    if any(kind == "Card" for kind in kinds[position + 1:]):
        raise Unsupported(f"{block.name}: cards after the table are not supported")
    suffix = set(block.name[len(base) + 1:].split("_")) if len(block.name) > len(base) else set()
    options = [card for card in top if type(card).__name__ == "OptionCardSet"]
    if suffix - {card._option_spec.name for card in options} - {""}:
        raise Unsupported(f"{block.name}: unknown option suffix {sorted(suffix)}")
    pre: list[tuple[int, list[object]]] = []
    for card in options:
        if card._option_spec.name not in suffix:
            continue
        if str(card._option_spec.position.placement.value) != "pre":
            raise Unsupported(f"{block.name}: post option {card._option_spec.name} with a table")
        pre.append((card._option_spec.position.index, list(card._cards)))
    head = [c for _, cards in sorted(pre, key=lambda p: -p[0]) for c in cards]
    head += [card for card in top[:position] if type(card).__name__ == "Card"]
    return position, top[position], head


def table_layout(block: Block, keyword_class: type, base: str, long: bool = False,
                 title: str | None = None) -> Layout:
    """Header fields plus a :class:`RowMap` of rows, or :class:`Unsupported`."""
    position, table, head_cards = _shape(block, keyword_class, base)
    data = [(i, line) for i, line in block.data()]
    while data and is_blank(data[-1][1]):
        data.pop()
    if len(data) < len(head_cards):
        raise Unsupported(f"{block.name}: missing header cards")
    fields = []
    for card, (index, line) in zip(head_cards, data):
        free = is_free_format(line)
        for token, column in enumerate(_columns(card._schema, long)):
            if not column.name.startswith("unused"):
                slot = FieldSlot(index, column.offset, column.width, token if free else None)
                fields.append(FieldInfo(column.name, column.kind, slot, "header", column.default))
    row_lines = [i for i, _ in data[len(head_cards):]]

    beyond_pid = FieldSlot(0, 40, 160) if long else FieldSlot(0, 16, 64)
    if type(table).__name__ == "TableCard":
        group = [_columns(table._schema, long)]
    elif block.name == "*ELEMENT_SOLID" and row_lines and read_text(block.lines[row_lines[0]], beyond_pid).strip():
        group = [_widen(_SOLID_ONE_LINE) if long else _SOLID_ONE_LINE]  # LS-PrePost one-line solid format
    else:
        if any(getattr(sub, "_active_func", None) is not None for sub in table._cards):
            raise Unsupported(f"{block.name}: conditional row cards are not supported")
        group = [_columns(sub._schema, long) for sub in table._cards]
    per = len(group)
    if len(row_lines) % per:
        raise Unsupported(f"{block.name}: {len(row_lines)} row lines do not form groups of {per}")
    rows = [tuple(row_lines[start:start + per]) for start in range(0, len(row_lines), per)]

    probe = RowMap(block, group, ["row"] * per, dict(enumerate(rows)))
    first = probe.locate(group[0][0].name)
    try:
        keys = [parse_number(probe.cell(indices, first)) for indices in rows]
    except FieldError:
        keys = []
    if keys and all(isinstance(k, int) for k in keys) and len(set(keys)) == len(keys):
        key, mapping = group[0][0].name, dict(zip(keys, rows))
    else:
        key, mapping = "row", dict(enumerate(rows, 1))
    rowmap = RowMap(block, group, ["row"] * per, mapping)
    _self_check(block, keyword_class, position, data[:len(head_cards)], list(mapping), rowmap, fields,
                title or block.lines[0].upper())
    return Layout(block.name, fields=fields, rows=rowmap, key=key, source="pydyna-table")


def _self_check(block: Block, keyword_class: type, position: int, head: list, keys: list, rows: RowMap,
                fields: list[FieldInfo], title: str) -> None:
    picks = keys[:SAMPLE] + [k for k in keys[max(len(keys) - SAMPLE, SAMPLE):]]
    lines = [i for i, _ in head]
    for key in picks:
        lines.extend(rows.line_indices(key))
    keyword = keyword_class()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            keyword.loads(title + "".join(block.lines[i] for i in lines))
        except Exception as error:  # PyDYNA raises many exception types on malformed input
            raise Unsupported(f"PyDYNA could not parse a sample of {block.name}: {error}") from error
    frame = keyword._cards[position].table
    if len(frame) != len(picks):
        raise Unsupported(f"{block.name}: sample has {len(picks)} rows but PyDYNA read {len(frame)}")
    for sample_row, key in enumerate(picks):
        for info in rows[key]:
            if info.name not in frame.columns:
                continue
            text = read_text(block.lines[info.slot.line], info.slot)
            expected = frame.iloc[sample_row][info.name]
            if not _same(text, expected, info.kind, info.default):
                raise Unsupported(f"Table self-check failed for {info.name!r} on line {info.slot.line} "
                                  f"({text!r} vs PyDYNA {expected!r})")
    for info in fields:
        expected = getattr(keyword, info.name, None) if hasattr(type(keyword), info.name) else None
        text = read_text(block.lines[info.slot.line], info.slot)
        if expected is not None and not _same(text, expected, info.kind, info.default):
            raise Unsupported(f"Table header self-check failed for {info.name!r} ({text!r} vs {expected!r})")


__all__ = ["SAMPLE", "table_layout"]
