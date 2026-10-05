"""Header + list keywords: ``*SET_*_LIST`` style member lists and ``*DEFINE_CURVE`` point tables.

Headers are exposed as named fields; members and curve points are read and replaced
as whole lists (the list lines are rewritten in standard format, everything else in
the block, including comments and the header line, is kept).
"""
from __future__ import annotations

from .blocks import Block
from .fields import FieldError, FieldSlot, format_value, is_free_format, long_spans, parse_number
from .text import body, ending, is_blank

# Header card (card 1) of list sets, after the optional title line.
SET_HEADERS: dict[str, tuple[tuple[str, str], ...]] = {
    "*SET_NODE_LIST": (("sid", "int"), ("da1", "float"), ("da2", "float"), ("da3", "float"), ("da4", "float"),
                       ("solver", "str"), ("its", "int")),
    "*SET_PART_LIST": (("sid", "int"), ("da1", "float"), ("da2", "float"), ("da3", "float"), ("da4", "float"),
                       ("solver", "str")),
    "*SET_SHELL_LIST": (("sid", "int"), ("da1", "float"), ("da2", "float"), ("da3", "float"), ("da4", "float")),
    "*SET_BEAM_LIST": (("sid", "int"), ("da1", "float"), ("da2", "float"), ("da3", "float"), ("da4", "float")),
    "*SET_TSHELL_LIST": (("sid", "int"), ("da1", "float"), ("da2", "float"), ("da3", "float"), ("da4", "float")),
    "*SET_DISCRETE_LIST": (("sid", "int"), ("da1", "float"), ("da2", "float"), ("da3", "float"), ("da4", "float")),
    "*SET_SOLID": (("sid", "int"), ("solver", "str")),
    "*SET_SOLID_LIST": (("sid", "int"), ("solver", "str")),
}
CURVE_HEADER = (("lcid", "int"), ("sidr", "int"), ("sfa", "float"), ("sfo", "float"), ("offa", "float"),
                ("offo", "float"), ("dattyp", "int"), ("lcint", "int"))
CURVE_KEYWORDS = ("*DEFINE_CURVE", "*DEFINE_CURVE_TITLE")


def base_name(name: str) -> tuple[str, bool]:
    """Strip a trailing ``_TITLE`` option: ``*SET_NODE_LIST_TITLE`` -> (``*SET_NODE_LIST``, True)."""
    return (name[:-6], True) if name.endswith("_TITLE") else (name, False)


def is_list_set(name: str) -> bool:
    return base_name(name)[0] in SET_HEADERS


def is_curve(name: str) -> bool:
    return name in CURVE_KEYWORDS


def split(block: Block) -> tuple[int | None, int, list[int]]:
    """Return (title line index or None, header line index, list line indices)."""
    data = [(i, line) for i, line in block.data()]
    while data and is_blank(data[-1][1]):
        data.pop()
    titled = base_name(block.name)[1]
    needed = 2 if titled else 1
    if len(data) < needed:
        raise FieldError(f"{block.name} lacks its {'title and ' if titled else ''}header card")
    title = data[0][0] if titled else None
    header = data[needed - 1][0]
    return title, header, [i for i, _ in data[needed:]]


def header_fields(block: Block, long: bool = False) -> list[tuple[str, str, FieldSlot, str]]:
    """``(name, kind, slot, card)`` for the title and header fields."""
    title, header, _ = split(block)
    spec = CURVE_HEADER if is_curve(block.name) else SET_HEADERS[base_name(block.name)[0]]
    line = block.lines[header]
    result = []
    if title is not None:
        result.append(("title", "str", FieldSlot(title, 0, 80), "title"))
    spans = long_spans([10] * len(spec)) if long else [(10 * t, 10) for t in range(len(spec))]
    for token, ((name, kind), (offset, width)) in enumerate(zip(spec, spans)):
        result.append((name, kind, FieldSlot(header, offset, width, token if is_free_format(line) else None), "card1"))
    return result


def _values(line: str, width: int, count: int) -> list[str]:
    text = body(line)
    if is_free_format(line):
        return [t for t in text.split(",")][:count]
    return [text[i:i + width] for i in range(0, width * count, width)]


def members(block: Block, long: bool = False) -> list[int]:
    """Member IDs in file order; blank and zero fields (row padding) are skipped."""
    _, _, lines = split(block)
    result = []
    for index in lines:
        for text in _values(block.lines[index], 20 if long else 10, 8):
            value = parse_number(text)
            if value in (None, 0):
                continue
            if not isinstance(value, int):
                raise FieldError(f"Non-integer member {text.strip()!r} on line {index}")
            result.append(value)
    return result


def points(block: Block) -> list[tuple[float, float]]:
    """Curve points ``(a, o)`` in file order."""
    _, _, lines = split(block)
    result = []
    for index in lines:
        line = block.lines[index]
        a, o = (_values(line, 20, 2) + ["", ""])[:2]
        a_value, o_value = parse_number(a), parse_number(o)
        if a_value is None and o_value is None:
            continue
        result.append((float(a_value or 0.0), float(o_value or 0.0)))
    return result


def _replace_list(block: Block, new_lines: list[str]) -> tuple[list[str], list[str]]:
    """Swap the list data lines for ``new_lines``; title, header and comments are kept.

    New lines go where the first old list line was (right after the header when the
    list was empty) and use the file's line ending.
    """
    _, header, old = split(block)
    newline = block.file.newline() if block.file else (ending(block.lines[header]) or "\n")
    formatted = [line + newline for line in new_lines]
    if not ending(block.lines[header]):
        block.lines[header] += newline
    removed = [block.lines[i] for i in old]
    anchor = old[0] if old else header + 1
    dropped = set(old)
    result: list[str] = []
    for index, line in enumerate(block.lines):
        if index == anchor:
            result.extend(formatted)
        if index not in dropped:
            result.append(line)
    if anchor >= len(block.lines):
        result.extend(formatted)
    block.lines[:] = result
    return removed, formatted


def write_members(block: Block, ids: list[int], per_line: int = 8, long: bool = False) -> tuple[list[str], list[str]]:
    if any(isinstance(i, bool) or int(i) != i or i <= 0 for i in ids):
        raise FieldError("Member IDs must be positive integers")
    rows = [ids[i:i + per_line] for i in range(0, len(ids), per_line)]
    width = 20 if long else 10
    lines = ["".join(format_value(int(v), width, "int")[0].rjust(width) for v in row) for row in rows]
    return _replace_list(block, lines)


def write_points(block: Block, pairs: list[tuple[float, float]]) -> tuple[list[str], list[str]]:
    lines = []
    for a, o in pairs:
        a_text, _ = format_value(float(a), 20, "float")
        o_text, _ = format_value(float(o), 20, "float")
        lines.append(a_text.rjust(20) + o_text.rjust(20))
    return _replace_list(block, lines)


__all__ = ["CURVE_KEYWORDS", "SET_HEADERS", "header_fields", "is_curve", "is_list_set", "members", "points",
           "split", "write_members", "write_points"]
