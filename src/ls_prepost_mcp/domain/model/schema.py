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

import logging
import math
import re
import threading
import warnings
from collections.abc import Mapping

from . import lists, tables, umat
from .blocks import Block
from .fields import (
    FieldError,
    FieldSlot,
    format_value,
    is_free_format,
    long_spans,
    parse_number,
    read_text,
    stray_text,
    write_text,
)
from .layouts import Column, FieldInfo, Layout, RowMap, Unsupported
from .parameters import field_expression, resolve_field
from .text import body, ending, is_blank

logger = logging.getLogger(__name__)
_REF_TOKEN = re.compile(r"<[^<>]*>|-?&[A-Za-z_][A-Za-z0-9_]*(?:[-+*/^][A-Za-z0-9_.&()]+)*")
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


class _SeriesLine:
    """One data line of a PyDYNA SeriesCard: values ``start .. start + count - 1``."""

    def __init__(self, series: object, start: int, count: int) -> None:
        self.series, self.start, self.count = series, start, count


def _series_lines(card: object) -> list[tuple[str, object]]:
    import dataclasses
    if dataclasses.is_dataclass(card._type):
        raise Unsupported("Structured series cards are not supported for named fields yet")
    total, per = len(card), int(card._fields_per_card)
    return [(card._name.lower(), _SeriesLine(card, start, min(per, total - start))) for start in range(0, total, per)]


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
        elif kind == "SeriesCard":
            if card.active:
                main.extend(_series_lines(card))
        elif getattr(card, "active", True):
            raise Unsupported(f"Active {kind} cards are not supported for named fields yet")
    ordered = [c for _, group in sorted(pre, key=lambda p: -p[0]) for c in group]
    ordered += main
    ordered += [c for _, group in sorted(post, key=lambda p: p[0]) for c in group]
    return ordered


def _ordered_cards(keyword: object) -> list[tuple[str, object]]:
    return _arrange(keyword._cards, set(getattr(keyword, "_active_options", set())))


def title_alias(name: str) -> str:
    """Keyword name as PyDYNA should read it.

    *CONTACT_..._TITLE is read by LS-DYNA like _ID (first line CID, HEADING): with CID 77 on
    that line the R11 solver reports contact interface ID 77. The manual lists only ID.
    """
    if name.startswith("*CONTACT_") and name.endswith("_TITLE") and "_ID_" not in name:
        return name[: -len("_TITLE")] + "_ID"
    return name


def pydyna_title(block: Block, long: bool) -> str:
    """Keyword line for PyDYNA: upper case, ``+`` when the block is in long format."""
    keyword = block.keyword
    text = title_alias(keyword.name) + ("+" if long else "") + ((" " + keyword.extra) if keyword.extra else "")
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
        if index == -1:
            out.append("\n")  # placeholder for an option-only card that the block does not have
            continue
        line = block.lines[index]
        if index == 0:
            out.append(pydyna_title(block, long))
            continue
        if line.startswith("$") or ("&" not in line and "<" not in line):
            out.append(line)
            continue
        if slots is None or index not in slots:
            out.append(_REF_TOKEN.sub(lambda m: " " * len(m.group(0)), line))
            continue
        new = line
        for slot in slots[index]:
            cell = read_text(new, slot)
            if field_expression(cell) is None:
                continue
            try:
                value = resolve_field(cell, lookup)
            except FieldError as error:
                raise Unsupported(f"Parameter expression {cell.strip()!r}: {error}") from error
            if not isinstance(value, (int, float)):
                raise Unsupported(f"Parameter expression {cell.strip()!r} has no numeric value")
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
    try:
        value = resolve_field(stripped, lookup) if field_expression(stripped) else parse_number(stripped)
    except (KeyError, TypeError, FieldError):
        return False
    if expected is None:
        return value == 0  # PyDYNA reads 0 in optional ID/link fields (e.g. LCID) as "not set"
    if value is None:
        return False
    return math.isclose(float(value), float(expected), rel_tol=1e-9, abs_tol=1e-30)


_TABLE_CARDS = {"TableCard", "TableCardGroup", "TextCard"}


class _ExtraLines(Unsupported):
    def __init__(self, lines: int, cards: int) -> None:
        super().__init__(f"{lines} data lines but PyDYNA expects {cards} cards")
        self.cards = cards


def _chunk_fields(cls: type, block: Block, lookup: Mapping[str, object],
                  chunk: list[tuple[int, str]], long: bool = False,
                  omit: int | None = None) -> tuple[list[FieldInfo], list[str]]:
    """Fields of one card instance (``chunk`` = its data lines), self-checked against PyDYNA.

    ``omit``: index of a PyDYNA card the block does not have (an option-only ID card that
    PyDYNA reads unconditionally); PyDYNA gets a blank line in its place.
    """
    data_indices = [i for i, _ in chunk]
    if omit is None:
        indices = [0] + data_indices
    else:
        indices = [0] + data_indices[:omit] + [-1] + data_indices[omit:]

    def build(keyword: object) -> tuple[list[FieldInfo], list[str], list[tuple[object, int]], list]:
        cards = _ordered_cards(keyword)
        if omit is not None:
            cards = cards[:omit] + cards[omit + 1:]
        if len(chunk) > len(cards):
            raise _ExtraLines(len(chunk), len(cards))
        infos, sources, coverage = [], [], []
        for (card_name, card), (index, line) in zip(cards, chunk):
            if isinstance(card, _SeriesLine):
                series = card.series
                width = 20 if long else int(series._element_width)
                coverage.append((card_name, index, [(j * width, width) for j in range(card.count)], True))
                kind = _kind(series._type)
                for j in range(card.count):
                    slot = _slot(line, index, j * width, width, j)
                    infos.append(FieldInfo(f"{card_name}{card.start + j + 1}", kind, slot, card_name))
                    sources.append((series, card.start + j))
                continue
            schemas = card._schema.fields
            spans = long_spans([s.width for s in schemas]) if long else [(s.offset, s.width) for s in schemas]
            # A card holding one text field (title/heading) is never comma separated: commas are text.
            title_card = len(schemas) == 1 and _kind(schemas[0].type) == "str"
            if not title_card:  # one text field: commas and any column are part of the text
                coverage.append((card_name, index, list(spans), None))
            seen: dict[str, int] = {}
            for token, (schema, (offset, width)) in enumerate(zip(schemas, spans)):
                name = schema.name.lower()
                if name.startswith("unused"):
                    continue  # ignored by LS-DYNA; PyDYNA does not keep its text
                seen[name] = seen.get(name, 0) + 1
                if seen[name] > 1:
                    name = f"{name}_{seen[name]}"  # PyDYNA repeats some names (x/y/z curve IDs)
                slot = FieldSlot(index, offset, width) if title_card else _slot(line, index, offset, width, token)
                infos.append(FieldInfo(name, _kind(schema.type), slot, card_name, schema.default))
                sources.append((card, token))
        return infos, [name for name, _ in cards[len(chunk):]], sources, coverage

    first, _, _, _ = build(_load(cls, _substituted_text(block, indices, lookup, None, long)))
    slots: dict[int, list[FieldSlot]] = {}
    for info in first:
        slots.setdefault(info.slot.line, []).append(info.slot)
    infos, missing, sources, coverage = build(_load(cls, _substituted_text(block, indices, lookup, slots, long)))
    for card_name, index, spans, tolerant in coverage:
        stray = stray_text(block.lines[index], spans, long, tolerant)
        if stray:
            raise Unsupported(f"Text outside the fields of {card_name} on line {index} ({stray[:40]!r}): "
                              "the PyDYNA cards do not match this block")
    for info, (card, position) in zip(infos, sources):
        if type(card).__name__ == "SeriesCard":
            expected = card[position] if position < len(card) else None
        else:
            expected = card._values[position] if position < len(card._values) else None
        text = read_text(block.lines[info.slot.line], info.slot)
        if _comma_title(card, text, expected):
            continue  # PyDYNA cuts a title at its first comma; the engine keeps the whole title line
        if not _same(text, expected, info.kind, info.default, lookup):
            raise Unsupported(f"Layout self-check failed for {info.name!r} on line {info.slot.line} "
                              f"({text!r} vs PyDYNA {expected!r})")
    return infos, missing


def _comma_title(card: object, text: str, expected: object) -> bool:
    """A one-text-field (title) card whose PyDYNA value is the text before the first comma."""
    fields = getattr(getattr(card, "_schema", None), "fields", None)
    if not fields or len(fields) != 1 or _kind(fields[0].type) != "str" or "," not in text:
        return False
    return str(expected or "").strip() == text.split(",", 1)[0].strip()


# Keywords whose ID/TITLE card exists only with the _ID/_TITLE option (LS-DYNA manual) while PyDYNA
# reads it unconditionally (ansys/pydyna#1347). Plain blocks are read without that card.
OPTION_ONLY_ID = (
    "*AIRBAG_PARTICLE", "*ALE_COUPLING_NODAL_DRAG", "*ALE_COUPLING_NODAL_PENALTY", "*ALE_FAIL_SWITCH_MMG",
    "*ALE_FSI_SWITCH_MMG", "*ALE_STRUCTURED_FSI", "*CONSTRAINED_BEAM_IN_SOLID", "*CONSTRAINED_GENERALIZED_WELD",
    "*CONSTRAINED_LAGRANGE_IN_SOLID", "*CONSTRAINED_LOCAL", "*CONSTRAINED_SHELL_IN_SOLID",
    "*CONSTRAINED_SOLID_IN_SOLID", "*CONSTRAINED_SPOTWELD", "*CONTACT_GUIDED_CABLE",
    "*DEFINE_ADAPTIVE_SOLID_TO_DES", "*DEFINE_ADAPTIVE_SOLID_TO_SPH", "*DEFINE_SPH_DE_COUPLING",
    "*INTERFACE_COMPONENT", "*LOAD_ALE_CONVECTION", "*LOAD_NURBS_SHELL", "*LOAD_SEGMENT_NONUNIFORM",
    "*LOAD_SEGMENT_SET_NONUNIFORM", "*LOAD_SHELL",
)


def _id_card(keyword: object) -> tuple[int, bool] | None:
    """``(index, has_title)`` of the first card holding only an ID (optionally with a title/heading)."""
    for index, (_, card) in enumerate(_ordered_cards(keyword)):
        if isinstance(card, _SeriesLine):
            continue
        names = [s.name.lower() for s in card._schema.fields if not s.name.lower().startswith("unused")]
        if names and names[0].endswith("id") and len(names) <= 2 and names[1:] in ([], ["title"], ["heading"]):
            return index, len(names) == 2
    return None


def _leading_id_card(keyword: object) -> bool:
    found = _id_card(keyword)
    return found is not None and found[0] == 0


# Option cards that LS-DYNA defines and PyDYNA lacks, placed around the PyDYNA cards.
# (keyword prefix, option) -> (position, fields); positions: "first" or "after_card1".
SYNTHETIC_OPTIONS = {
    ("*CONSTRAINED_JOINT_", "ID"): ("first", (("jid", "int", 0, 10), ("heading", "str", 10, 70))),  # R11 p. 10-55
    ("*CONSTRAINED_JOINT_", "LOCAL"): ("after_card1", (("raid", "int", 0, 10), ("lst", "int", 10, 10))),  # p. 10-58
}


def _synthetic(block: Block, base: str) -> dict[str, tuple]:
    tokens = [token for token in block.name[len(base):].split("_") if token]
    return {token: spec for (prefix, option), spec in SYNTHETIC_OPTIONS.items()
            for token in tokens if token == option and base.startswith(prefix)}


def _split_synthetic(block: Block, data: list[tuple[int, str]], synthetic: dict[str, tuple],
                     long: bool) -> tuple[list[tuple[int, str]], list[FieldInfo]]:
    """Remove the synthesised option lines from ``data`` and describe their fields."""
    if long:
        raise Unsupported(f"{block.name}: long format with synthesised option cards is not supported")
    lines, infos = list(data), []
    for wanted in ("first", "after_card1"):
        for option, (position, fields) in synthetic.items():
            if position != wanted:
                continue
            at = 0 if position == "first" else 1
            if len(lines) <= at:
                raise Unsupported(f"{block.name}: the {option} card is missing")
            index, line = lines.pop(at)
            stray = stray_text(line, [(offset, width) for _, _, offset, width in fields], tolerant=False)
            if stray and not any(kind == "str" for _, kind, _, _ in fields):
                raise Unsupported(f"{block.name}: text outside the {option} card on line {index} ({stray[:40]!r})")
            free = is_free_format(line)
            for token, (name, kind, offset, width) in enumerate(fields):
                infos.append(FieldInfo(name, kind, FieldSlot(index, offset, width, token if free else None),
                                       option.lower()))
    return lines, infos


def _omitted_id_card(block: Block, cls: type, base: str, long: bool) -> int | None:
    """Index of the PyDYNA ID card to skip for a plain block of an OPTION_ONLY_ID keyword."""
    if not base.startswith(OPTION_ONLY_ID):
        return None
    tokens = {token for token in block.name[len(base):].split("_") if token}
    if tokens & {"ID", "TITLE"}:
        return None
    found = _id_card(_load(cls, pydyna_title(block, long)))
    return None if found is None else found[0]


def _check_options(block: Block, cls: type, base: str, long: bool, synthetic: set[str] = frozenset()) -> None:
    """Every keyword-name token after the PyDYNA class name must be an option PyDYNA knows."""
    suffix = [token for token in title_alias(block.name)[len(base):].split("_") if token and token not in synthetic]
    if not suffix:
        return
    probe = _load(cls, pydyna_title(block, long))
    known = {token for option in getattr(probe, "_active_options", set()) for token in str(option).split("_")}
    unknown = [token for token in suffix if token not in known]
    found = _id_card(probe)
    if found is not None and (unknown == ["ID"] or (unknown == ["TITLE"] and found[1])):
        unknown = []  # PyDYNA keeps the option-only ID/TITLE card unconditionally (ansys/pydyna#1347)
    if unknown:
        raise Unsupported(f"PyDYNA {base} has no option {'_'.join(unknown)}; its cards would be misplaced")


def _pydyna_layout(block: Block, lookup: Mapping[str, object], long: bool = False) -> Layout:
    cls, base = _pydyna_class(block.name)
    if _TABLE_CARDS & {type(card).__name__ for card in cls()._cards}:
        return tables.table_layout(block, cls, base, long=long, title=pydyna_title(block, long))
    synthetic = _synthetic(block, base)
    _check_options(block, cls, base, long, set(synthetic))
    data = [(i, line) for i, line in block.data()]
    while data and is_blank(data[-1][1]):
        data.pop()
    extra_infos: list[FieldInfo] = []
    if synthetic:
        data, extra_infos = _split_synthetic(block, data, synthetic, long)
    omit = _omitted_id_card(block, cls, base, long)
    if omit is not None:
        infos, missing = _chunk_fields(cls, block, lookup, data, long, omit=omit)
        return Layout(block.name, fields=extra_infos + infos, source="pydyna", missing_cards=missing)
    try:
        infos, missing = _chunk_fields(cls, block, lookup, data, long)
        return Layout(block.name, fields=extra_infos + infos, source="pydyna", missing_cards=missing)
    except _ExtraLines as extra:
        size = extra.cards
        if size == 0 or len(data) % size or synthetic:
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
    if not data:
        raise Unsupported("*TITLE has no title line")
    title = FieldInfo("title", "str", FieldSlot(data[0][0], 0, 80), "title")
    return Layout(block.name, fields=[title], source="builtin")


def _include_layout(block: Block) -> Layout:
    """File-name fields of ``*INCLUDE`` (one per line) and ``*INCLUDE_TRANSFORM`` / ``_AUTO_OFFSET`` (card 1)."""
    data = [(i, line) for i, line in block.data() if not is_blank(line)]
    if any(body(line).rstrip().endswith(" +") for _, line in data):
        raise Unsupported("Include names continued with ' +' need positional editing")
    if block.name != "*INCLUDE":
        data = data[:1]
    infos = [FieldInfo("filename", "str", FieldSlot(index, 0, 80), "filename") for index, _ in data]
    if len(infos) == 1:
        return Layout(block.name, fields=infos, source="builtin-include")
    return Layout(block.name, rows={n: [info] for n, info in enumerate(infos, 1)}, key="row", source="builtin-include")


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
    if block.name in ("*INCLUDE", "*INCLUDE_TRANSFORM", "*INCLUDE_AUTO_OFFSET"):
        return _include_layout(block)
    if umat.is_umat(block.name):
        return umat.umat_layout(block, lookup, long)
    if lists.is_define_table(block.name):
        return lists.define_table_layout(block, long)
    if block.name == "*LOAD_SEGMENT":
        return lists.load_segment_layout(block, long)
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


__all__ = ["FieldInfo", "Layout", "Unsupported", "block_format", "layout", "pydyna_title", "warm_up"]


def warm_up(background: bool = True) -> threading.Thread | None:
    """Import PyDYNA keyword classes before the first named-field request.

    The first import takes roughly 15-20 s (thousands of keyword modules). Call this when
    a server starts; a later import on another thread waits for it instead of repeating it.
    """
    def load() -> None:
        try:
            import ansys.dyna.core.keywords  # noqa: F401
            from ansys.dyna.core.keywords.keyword_classes.type_mapping import TypeMapping  # noqa: F401
        except ImportError:
            logger.info("PyDYNA not installed; named fields fall back to builtin layouts only")

    if not background:
        load()
        return None
    thread = threading.Thread(target=load, name="pydyna-warm-up", daemon=True)
    thread.start()
    return thread
