"""``*SET_*`` variants whose data card repeats: ``_GENERAL``, ``_COLUMN``, ``_GENERATE_INCREMENT``.

PyDYNA 0.12.1 has the right field names and columns for these keywords but defines the data
card once, so a set with several data lines cannot be read through it. Here the header card and
the row template come from the PyDYNA class and the data card repeats for every remaining line
(``row`` = 1, 2, ... in file order). Sampled rows are self-checked by letting PyDYNA parse the
header plus that single row; any disagreement refuses the layout.
"""
from __future__ import annotations

import warnings

from .blocks import Block
from .fields import FieldSlot, is_free_format, read_text, stray_text
from .layouts import Column, FieldInfo, Layout, RowMap, Unsupported
from .tables import SAMPLE, _columns, _fixed, _same
from .text import ending, is_blank

ROW_OPTIONS = ("_GENERAL", "_COLUMN", "_GENERATE_INCREMENT")


def is_row_set(base: str) -> bool:
    """``base`` is a keyword name without ``_TITLE`` / ``_COLLECT`` (see :func:`lists.base_name`)."""
    return base.startswith("*SET_") and base.endswith(ROW_OPTIONS)


def increment_kind(base: str) -> str | None:
    """ID kind of the ``BBEG``-``BEND`` ranges of a ``*SET_*_GENERATE_INCREMENT`` (else None)."""
    if not (base.startswith("*SET_") and base.endswith("_GENERATE_INCREMENT")):
        return None
    return base.split("_")[1].lower()  # NODE, SHELL, SOLID, BEAM, PART, TSHELL, DISCRETE


def is_general(base: str) -> bool:
    return base.startswith("*SET_") and base.endswith("_GENERAL")


# What a *SET_*_GENERAL row can name, depending on OPTION: nodes, elements, parts, boxes and sets.
GENERAL_KINDS = frozenset({"node", "part", "shell", "solid", "beam", "tshell", "discrete", "box", "node_set",
                           "part_set", "shell_set", "solid_set", "beam_set", "tshell_set", "discrete_set",
                           "segment_set"})


def row_set_layout(block: Block, keyword_class: type, base: str, titled: bool, long: bool = False) -> Layout:
    cards = [card for card in keyword_class()._cards if type(card).__name__ == "Card"]
    if len(cards) != 2:
        raise Unsupported(f"{block.name}: PyDYNA defines {len(cards)} plain cards, expected header + data card")
    head, data_card = (_columns(card._schema, long) for card in cards)
    data = list(block.data())
    while data and is_blank(data[-1][1]):
        data.pop()
    skip = 1 if titled else 0
    if len(data) <= skip:
        raise Unsupported(f"{block.name}: missing {'title and ' if titled else ''}header card")
    fields = [FieldInfo("title", "str", FieldSlot(data[0][0], 0, 80), "title")] if titled else []
    header = data[skip][0]
    fields += _infos(block, header, head, "header")
    if any(is_blank(line) for _, line in data[skip + 1:]):
        # PyDYNA reads a blank data card as defaults (OPTION "ALL"); what LS-DYNA does is not verified
        raise Unsupported(f"{block.name}: blank line between the data rows")
    rows = RowMap(block, [data_card], ["row"], {n: (index,) for n, (index, _) in enumerate(data[skip + 1:], 1)})
    _self_check(block, keyword_class, base, long, header, head, rows)
    return Layout(block.name, fields=fields, rows=rows, key="row", source="builtin-row-set")


def _infos(block: Block, index: int, columns: list[Column], card: str) -> list[FieldInfo]:
    free = is_free_format(block.lines[index])
    return [FieldInfo(c.name, c.kind, FieldSlot(index, c.offset, c.width, token if free else None), card, c.default)
            for token, c in enumerate(columns) if not c.name.startswith("unused")]


def _pydyna_line(block: Block, index: int, columns: list[Column]) -> str:
    line = block.lines[index]
    spans = {token: (c.offset, c.width) for token, c in enumerate(columns)}
    return _fixed(line, spans) if is_free_format(line) else line


def _self_check(block: Block, keyword_class: type, base: str, long: bool, header: int,
                head: list[Column], rows: RowMap) -> None:
    keys = list(rows)
    picks = keys[:SAMPLE] + keys[max(len(keys) - SAMPLE, SAMPLE):]
    extra = block.keyword.extra if block.keyword else ""  # e.g. " +": PyDYNA then reads long format
    title = base + ("+" if long else "") + ((" " + extra) if extra else "") + ending(block.lines[0])
    for index, columns in [(header, head)] + [(rows.line_indices(k)[0], rows.template[0]) for k in keys]:
        stray = stray_text(block.lines[index], [(c.offset, c.width) for c in columns], long)
        if stray:
            raise Unsupported(f"{block.name}: text outside the fields on line {index} ({stray[:40]!r})")
    header_text = _pydyna_line(block, header, head)
    for key in picks or [None]:
        lines = [header_text]
        if key is not None:
            lines.append(_pydyna_line(block, rows.line_indices(key)[0], rows.template[0]))
        keyword = keyword_class()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                keyword.loads(title + "".join(line if line.endswith("\n") else line + "\n" for line in lines))
            except Exception as error:  # PyDYNA raises many exception types on malformed input
                raise Unsupported(f"PyDYNA could not parse {block.name} row {key}: {error}") from error
        infos = _infos(block, header, head, "header") + (rows[key] if key is not None else [])
        for info in infos:
            if not hasattr(type(keyword), info.name):
                continue
            text = read_text(block.lines[info.slot.line], info.slot)
            expected = getattr(keyword, info.name)
            if not _same(text, expected, info.kind, info.default):
                raise Unsupported(f"{block.name}: self-check failed for {info.name!r} on line {info.slot.line} "
                                  f"({text!r} vs PyDYNA {expected!r})")


__all__ = ["GENERAL_KINDS", "ROW_OPTIONS", "increment_kind", "is_general", "is_row_set", "row_set_layout"]
