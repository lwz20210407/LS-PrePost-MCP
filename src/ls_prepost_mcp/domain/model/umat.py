"""Builtin layout for ``*MAT_USER_DEFINED_MATERIAL_MODELS`` (UMAT/VUMAT parameter cards).

Card structure (LS-DYNA keyword manual): optional title; card 1 ``MID RO MT LMC NHV IORTHO
IBULK IG``; card 2 ``IVECT IFAIL ITHERM IHYPER IEOS LMCA EXT EPSHV``; when ``IORTHO`` is
non-zero two orthotropy cards; then ``LMC`` material constants ``P1..Pn`` (8 per line);
then ``LMCA`` additional constants ``PA1..`` (8 per line). The number of data lines must
match exactly, otherwise the block is refused.
"""
from __future__ import annotations

from collections.abc import Mapping

from .blocks import Block
from .fields import FieldError, FieldSlot, is_free_format, long_spans, parse_number, read_text
from .layouts import FieldInfo, Layout, Unsupported
from .parameters import field_expression, resolve_field
from .text import is_blank

KEYWORDS = ("*MAT_USER_DEFINED_MATERIAL_MODELS", "*MAT_USER_DEFINED_MATERIAL_MODELS_TITLE")
CARD1 = (("mid", "int"), ("ro", "float"), ("mt", "int"), ("lmc", "int"), ("nhv", "int"), ("iortho", "int"),
         ("ibulk", "int"), ("ig", "int"))
CARD2 = (("ivect", "int"), ("ifail", "int"), ("itherm", "int"), ("ihyper", "int"), ("ieos", "int"),
         ("lmca", "int"), ("ext", "int"), ("epshv", "int"))
ORTHO1 = (("aopt", "float"), ("macf", "int"), ("xp", "float"), ("yp", "float"), ("zp", "float"),
          ("a1", "float"), ("a2", "float"), ("a3", "float"))
ORTHO2 = (("v1", "float"), ("v2", "float"), ("v3", "float"), ("d1", "float"), ("d2", "float"),
          ("d3", "float"), ("beta", "float"), ("ievts", "int"))


def is_umat(name: str) -> bool:
    return name in KEYWORDS


def _card(index: int, line: str, spec: tuple, card: str, long: bool) -> list[FieldInfo]:
    spans = long_spans([10] * len(spec)) if long else [(10 * t, 10) for t in range(len(spec))]
    free = is_free_format(line)
    return [FieldInfo(name, kind, FieldSlot(index, offset, width, token if free else None), card)
            for token, ((name, kind), (offset, width)) in enumerate(zip(spec, spans))]


def _count(infos: list[FieldInfo], name: str, block: Block, lookup: Mapping[str, object]) -> int:
    info = next(i for i in infos if i.name == name)
    text = read_text(block.lines[info.slot.line], info.slot).strip()
    ref = field_expression(text) is not None
    value = None
    if ref:
        try:
            value = resolve_field(text, lookup)
        except FieldError as error:
            raise Unsupported(f"{block.name}: {name.upper()} {error}") from error
    else:
        try:
            value = parse_number(text)
        except FieldError as error:
            raise Unsupported(f"{block.name}: {name.upper()} is not a number") from error
    if value is None:
        return 0
    if not float(value).is_integer() or value < 0:
        raise Unsupported(f"{block.name}: {name.upper()}={value} is not a non-negative integer")
    return int(value)


def umat_layout(block: Block, lookup: Mapping[str, object], long: bool = False) -> Layout:
    data = [(i, line) for i, line in block.data()]
    while data and is_blank(data[-1][1]):
        data.pop()
    titled = block.name.endswith("_TITLE")
    head = 1 if titled else 0
    if len(data) < head + 2:
        raise Unsupported(f"{block.name}: missing cards 1/2")
    fields: list[FieldInfo] = []
    if titled:
        fields.append(FieldInfo("title", "str", FieldSlot(data[0][0], 0, 80), "title"))
    fields += _card(*data[head], CARD1, "card1", long)
    fields += _card(*data[head + 1], CARD2, "card2", long)
    lmc, iortho, lmca = (_count(fields, n, block, lookup) for n in ("lmc", "iortho", "lmca"))
    position = head + 2
    if iortho:
        if len(data) < position + 2:
            raise Unsupported(f"{block.name}: IORTHO set but orthotropy cards are missing")
        fields += _card(*data[position], ORTHO1, "ortho1", long)
        fields += _card(*data[position + 1], ORTHO2, "ortho2", long)
        position += 2
    rows_lmc, rows_lmca = -(-lmc // 8), -(-lmca // 8)
    if len(data) != position + rows_lmc + rows_lmca:
        raise Unsupported(f"{block.name}: expected {position + rows_lmc + rows_lmca} data lines "
                          f"(LMC={lmc}, IORTHO={iortho}, LMCA={lmca}) but found {len(data)}")
    for prefix, count, start in (("p", lmc, position), ("pa", lmca, position + rows_lmc)):
        for number in range(count):
            index, line = data[start + number // 8]
            token = number % 8
            offset, width = long_spans([10] * 8)[token] if long else (10 * token, 10)
            slot = FieldSlot(index, offset, width, token if is_free_format(line) else None)
            fields.append(FieldInfo(f"{prefix}{number + 1}", "float", slot, "constants"))
    return Layout(block.name, fields=fields, source="builtin-umat")
