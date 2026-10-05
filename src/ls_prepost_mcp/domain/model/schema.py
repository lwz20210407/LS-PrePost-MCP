"""Named-field layouts for keyword blocks.

A layout maps field names to exact positions (data line + columns) inside a block.
Two sources are used:

* built-in row specs for ``*NODE`` and plain ``*PART`` (one row per node / part);
* PyDYNA card schemas for keywords made of plain cards, option cards (``_TITLE``,
  ``_ID``, ``_MPP``, ...) and single card sets.

Every PyDYNA layout is self-checked: the text found at each computed position must
equal the value PyDYNA itself parsed. Any disagreement raises :class:`Unsupported`, so
an edit is never written to a guessed position. Callers can then fall back to
positional editing.
"""
from __future__ import annotations

import math
import re
import warnings
from collections.abc import Mapping

from . import lists, tables
from .blocks import Block
from .fields import (
    FieldError,
    FieldSlot,
    format_value,
    is_free_format,
    long_spans,
    parse_number,
    read_text,
    write_text,
)
from .layouts import Column, FieldInfo, Layout, RowMap, Unsupported
from .parameters import reference
from .text import body, ending, is_blank

_REF_TOKEN = re.compile(r"-?&[A-Za-z_][A-Za-z0-9_]*")
NODE_FIELDS = (("nid", "int", 0, 8), ("x", "float", 8, 16), ("y", "float", 24, 16),
               ("z", "float", 40, 16), ("tc", "int", 56, 8), ("rc", "int", 64, 8))
PART_FIELDS = (("pid", "int"), ("secid", "int"), ("mid", "int"), ("eosid", "int"),
               ("hgid", "int"), ("grav", "int"), ("adpopt", "int"), ("tmid", "int"))


def _slot(line: str, index: int, offset: int, width: int, token: int) -> FieldSlot:
    return FieldSlot(index, offset, width, token if is_free_format(line) else None)


def _node_layout(block: Block, long: bool = False) -> Layout:
    spans = long_spans([w for _, _, _, w in NODE_FIELDS]) if long else [(o, w) for _, _, o, w in NODE_FIELDS]
    columns = [Column(n, k, o, w) for (n, k, _, _), (o, w) in zip(NODE_FIELDS, spans)]
    rows: dict[int, tuple[int, ...]] = {}
    for index, line in block.data():
        if is_blank(line):
            continue
        try:
            nid = parse_number(read_text(line, _slot(line, index, columns[0].offset, columns[0].width, 0)))
        except FieldError as error:
            raise Unsupported(f"*NODE line {index}: {error}") from error
        if not isinstance(nid, int):
            raise Unsupported(f"*NODE line {index} has no integer node ID")
        if nid in rows:
            raise Unsupported(f"Duplicate node ID {nid} in one *NODE block")
        rows[nid] = (index,)
    return Layout(block.name, rows=RowMap(block, [columns], ["node"], rows), key="nid", source="builtin")


def _part_layout(block: Block, long: bool = False) -> Layout:
    width = 20 if long else 10
    template = [[Column("heading", "str", 0, 80)],
                [Column(n, k, width * t, width) for t, (n, k) in enumerate(PART_FIELDS)]]
    data = [(i, line) for i, line in block.data()]
    while data and is_blank(data[-1][1]):
        data.pop()
    if len(data) % 2:
        raise Unsupported("*PART block does not consist of heading/card line pairs")
    rows: dict[int, tuple[int, ...]] = {}
    for (h_index, _), (c_index, line) in zip(data[0::2], data[1::2]):
        try:
            pid = parse_number(read_text(line, _slot(line, c_index, 0, width, 0)))
        except FieldError as error:
            raise Unsupported(f"*PART line {c_index}: {error}") from error
        if not isinstance(pid, int):
            raise Unsupported(f"*PART card line {c_index} has no integer PID")
        rows[pid] = (h_index, c_index)
    return Layout(block.name, rows=RowMap(block, template, ["heading", "card1"], rows), key="pid", source="builtin")


def _pydyna_class(name: str) -> tuple[type, str]:
    try:
        from ansys.dyna.core import keywords
        from ansys.dyna.core.keywords.keyword_classes.type_mapping import TypeMapping
    except ImportError as error:  # optional dependency
        raise Unsupported("PyDYNA (ansys-dyna-core) is required for named fields of this keyword") from error
    tokens = name.split("_")
    while tokens:
        type_name = TypeMapping.get("_".join(tokens))
        if type_name is not None:
            return getattr(keywords, type_name), "_".join(tokens)
        tokens = tokens[:-1]
    raise Unsupported(f"PyDYNA has no definition for {name}")


def _kind(python_type: type) -> str:
    return "int" if python_type is int else "float" if python_type is float else "str"


def _arrange(cards: list[object], active_options: set[str]) -> list[tuple[str, object]]:
    """Active plain cards in file order: pre-options (outermost first), main, post-options."""
    pre: list[tuple[int, list[tuple[str, object]]]] = []
    post: list[tuple[int, list[tuple[str, object]]]] = []
    main: list[tuple[str, object]] = []
    for number, card in enumerate(cards, 1):
        kind = type(card).__name__
        if kind == "Card":
            if card.active:
                main.append((f"card{number}", card))
        elif kind == "OptionCardSet":
            spec = card._option_spec
            if spec.name not in active_options:
                continue
            inner = []
            for sub in card._cards:
                if type(sub).__name__ != "Card":
                    raise Unsupported(f"Option {spec.name} contains {type(sub).__name__} cards")
                if sub.active:
                    inner.append((spec.name.lower(), sub))
            placement = str(spec.position.placement.value)
            (pre if placement == "pre" else post).append((spec.position.index, inner))
        elif kind == "CardSet":
            items = card._base_items
            if len(items) != 1:
                raise Unsupported(f"{len(items)} repeated card sets in one block")
            main.extend(_arrange(items[0]._cards, active_options))
        elif getattr(card, "active", True):
            raise Unsupported(f"Active {kind} cards are not supported for named fields yet")
    ordered = [c for _, group in sorted(pre, key=lambda p: -p[0]) for c in group]
    ordered += main
    ordered += [c for _, group in sorted(post, key=lambda p: p[0]) for c in group]
    return ordered


def _ordered_cards(keyword: object) -> list[tuple[str, object]]:
    return _arrange(keyword._cards, set(getattr(keyword, "_active_options", set())))


def pydyna_title(block: Block, long: bool) -> str:
    """Keyword line for PyDYNA: upper case, ``+`` when the block is in long format."""
    keyword = block.keyword
    text = keyword.name + ("+" if long else "") + ((" " + keyword.extra) if keyword.extra else "")
    return text + ending(block.lines[0])


def _substituted_text(block: Block, indices: list[int], lookup: Mapping[str, object],
                      slots: dict[int, list[FieldSlot]] | None, long: bool = False) -> str:
    """Text of the selected block lines for PyDYNA.

    The keyword line is upper-cased (PyDYNA matches titles case-sensitively) and
    ``&name`` references are blanked (first pass) or replaced by their values. The
    result is only parsed, never written back.
    """
    out = []
    for index in indices:
        line = block.lines[index]
        if index == 0:
            out.append(pydyna_title(block, long))
            continue
        if line.startswith("$") or "&" not in line:
            out.append(line)
            continue
        if slots is None or index not in slots:
            out.append(_REF_TOKEN.sub(lambda m: " " * len(m.group(0)), line))
            continue
        new = line
        for slot in slots[index]:
            ref = reference(read_text(new, slot))
            if ref is None:
                continue
            negated, name = ref
            value = lookup.get(name.lower())
            if not isinstance(value, (int, float)):
                raise Unsupported(f"Parameter {name!r} has no numeric value")
            value = -value if negated else value
            text, _ = format_value(value, slot.width if slot.token is None else 40)
            new = write_text(new, slot, text)
        out.append(new)
    return "".join(out)


def _load(cls: type, text: str) -> object:
    keyword = cls()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            keyword.loads(text)
        except Exception as error:  # PyDYNA raises many exception types on malformed input
            raise Unsupported(f"PyDYNA could not parse the block: {error}") from error
    return keyword


def _same(text: str, expected: object, kind: str, default: object, lookup: Mapping[str, object]) -> bool:
    stripped = text.strip()
    if not stripped:
        return expected is None or expected == default or (isinstance(expected, float) and math.isnan(expected))
    if kind == "str":
        return str(expected or "").strip() == stripped
    ref = reference(stripped)
    try:
        value = (-1 if ref[0] else 1) * float(lookup[ref[1].lower()]) if ref else parse_number(stripped)
    except (KeyError, TypeError, FieldError):
        return False
    if expected is None or value is None:
        return False
    return math.isclose(float(value), float(expected), rel_tol=1e-9, abs_tol=1e-30)


_TABLE_CARDS = {"TableCard", "TableCardGroup", "TextCard"}


class _ExtraLines(Unsupported):
    def __init__(self, lines: int, cards: int) -> None:
        super().__init__(f"{lines} data lines but PyDYNA expects {cards} cards")
        self.cards = cards


def _chunk_fields(cls: type, block: Block, lookup: Mapping[str, object],
                  chunk: list[tuple[int, str]], long: bool = False) -> tuple[list[FieldInfo], list[str]]:
    """Fields of one card instance (``chunk`` = its data lines), self-checked against PyDYNA."""
    indices = [0] + [i for i, _ in chunk]

    def build(keyword: object) -> tuple[list[FieldInfo], list[str], dict[str, object]]:
        cards = _ordered_cards(keyword)
        if len(chunk) > len(cards):
            raise _ExtraLines(len(chunk), len(cards))
        infos = []
        for (card_name, card), (index, line) in zip(cards, chunk):
            schemas = card._schema.fields
            spans = long_spans([s.width for s in schemas]) if long else [(s.offset, s.width) for s in schemas]
            for token, (schema, (offset, width)) in enumerate(zip(schemas, spans)):
                if schema.name.lower().startswith("unused"):
                    continue  # ignored by LS-DYNA; PyDYNA does not keep its text
                infos.append(FieldInfo(schema.name.lower(), _kind(schema.type),
                                       _slot(line, index, offset, width, token), card_name, schema.default))
        return infos, [name for name, _ in cards[len(chunk):]], dict(cards)

    first, _, _ = build(_load(cls, _substituted_text(block, indices, lookup, None, long)))
    slots: dict[int, list[FieldSlot]] = {}
    for info in first:
        slots.setdefault(info.slot.line, []).append(info.slot)
    infos, missing, cards = build(_load(cls, _substituted_text(block, indices, lookup, slots, long)))
    for info in infos:
        card = cards[info.card]
        index = card._schema.name_to_index.get(info.name)
        expected = card._values[index] if index is not None else None
        text = read_text(block.lines[info.slot.line], info.slot)
        if not _same(text, expected, info.kind, info.default, lookup):
            raise Unsupported(f"Layout self-check failed for {info.name!r} on line {info.slot.line} "
                              f"({text!r} vs PyDYNA {expected!r})")
    return infos, missing


def _pydyna_layout(block: Block, lookup: Mapping[str, object], long: bool = False) -> Layout:
    cls, base = _pydyna_class(block.name)
    if _TABLE_CARDS & {type(card).__name__ for card in cls()._cards}:
        return tables.table_layout(block, cls, base, long=long, title=pydyna_title(block, long))
    data = [(i, line) for i, line in block.data()]
    while data and is_blank(data[-1][1]):
        data.pop()
    try:
        infos, missing = _chunk_fields(cls, block, lookup, data, long)
        return Layout(block.name, fields=infos, source="pydyna", missing_cards=missing)
    except _ExtraLines as extra:
        size = extra.cards
        if size == 0 or len(data) % size:
            raise
    # Several instances of the keyword cards follow one keyword line (e.g. many vectors).
    result = Layout(block.name, key="instance", source="pydyna")
    for number, begin in enumerate(range(0, len(data), size), 1):
        infos, missing = _chunk_fields(cls, block, lookup, data[begin:begin + size], long)
        if missing:
            raise Unsupported(f"Instance {number} of {block.name} has a different card count")
        result.rows[number] = infos
    return result


def _title_layout(block: Block) -> Layout:
    data = [(i, line) for i, line in block.data() if not is_blank(line)]
    if len(data) != 1:
        raise Unsupported("*TITLE must have exactly one title line")
    title = FieldInfo("title", "str", FieldSlot(data[0][0], 0, 80), "title")
    return Layout(block.name, fields=[title], source="builtin")


def layout(block: Block, lookup: Mapping[str, object], deck_format: str = "standard") -> Layout:
    """Return the named-field layout of ``block`` or raise :class:`Unsupported`."""
    if block.kind != "keyword" or block.keyword is None:
        raise Unsupported("Not a keyword block")
    if any("BEGIN PGP MESSAGE" in line for line in block.lines):
        raise Unsupported("Encrypted block: content cannot be read or edited")
    fmt = block_format(block, deck_format)
    if fmt == "i10":
        raise Unsupported("i10 format blocks support positional editing only")
    long = fmt == "long"
    if block.name == "*NODE":
        return _node_layout(block, long)
    if block.name == "*PART":
        return _part_layout(block, long)
    if block.name == "*TITLE":
        return _title_layout(block)
    if lists.is_list_set(block.name) or lists.is_curve(block.name):
        try:
            headers = lists.header_fields(block, long)
        except FieldError as error:
            raise Unsupported(str(error)) from error
        return Layout(block.name, fields=[FieldInfo(n, k, slot, card) for n, k, slot, card in headers],
                      source="builtin-list")
    if any(body(line).startswith("&") for _, line in block.data()) and block.name.startswith("*CONTACT"):
        raise Unsupported("MPP continuation cards starting with '&' need positional editing")
    return _pydyna_layout(block, lookup, long)


def block_format(block: Block, deck_format: str = "standard") -> str:
    """``standard``, ``long`` or ``i10`` for one block (its ``+``/``-``/``%`` flag overrides the deck)."""
    flag = block.keyword.flag if block.keyword else ""
    return {"-": "standard", "+": "long", "%": "i10"}.get(flag, deck_format)


__all__ = ["FieldInfo", "Layout", "Unsupported", "block_format", "layout", "pydyna_title"]
