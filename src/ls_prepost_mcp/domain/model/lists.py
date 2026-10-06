"""Header + list keywords: ``*SET_*_LIST`` style member lists and ``*DEFINE_CURVE`` point tables.

Headers are exposed as named fields; members and curve points are read and replaced
as whole lists (the list lines are rewritten in standard format, everything else in
the block, including comments and the header line, is kept).
"""
from __future__ import annotations

from .blocks import Block
from .fields import FieldError, FieldSlot, format_value, is_free_format, long_spans, parse_number, stray_text
from .layouts import Column, FieldInfo, Layout, RowMap, Unsupported
from .parameters import field_expression, resolve_field
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
_GENERIC = (("sid", "int"), ("da1", "float"), ("da2", "float"), ("da3", "float"), ("da4", "float"))
# *_ADD lists hold other set IDs; *_GENERATE lists hold ID ranges (header access only).
for _family, _head in (("NODE", SET_HEADERS["*SET_NODE_LIST"]), ("PART", SET_HEADERS["*SET_PART_LIST"]),
                       ("SHELL", _GENERIC), ("SOLID", _GENERIC), ("BEAM", _GENERIC), ("SEGMENT", _GENERIC)):
    SET_HEADERS[f"*SET_{_family}_ADD"] = _head
for _name, _head in (("*SET_NODE_LIST_GENERATE", SET_HEADERS["*SET_NODE_LIST"]),
                     ("*SET_PART_LIST_GENERATE", SET_HEADERS["*SET_PART_LIST"]),
                     ("*SET_SHELL_LIST_GENERATE", _GENERIC), ("*SET_SOLID_GENERATE", _GENERIC),
                     ("*SET_BEAM_GENERATE", _GENERIC)):
    SET_HEADERS[_name] = _head
# Legacy spellings without _LIST read as list sets.
for _alias, _target in (("*SET_NODE", "*SET_NODE_LIST"), ("*SET_PART", "*SET_PART_LIST"),
                        ("*SET_SHELL", "*SET_SHELL_LIST"), ("*SET_BEAM", "*SET_BEAM_LIST")):
    SET_HEADERS[_alias] = SET_HEADERS[_target]
RANGE_SETS = {name for name in SET_HEADERS if name.endswith("_GENERATE")}
CURVE_HEADER = (("lcid", "int"), ("sidr", "int"), ("sfa", "float"), ("sfo", "float"), ("offa", "float"),
                ("offo", "float"), ("dattyp", "int"), ("lcint", "int"))
CURVE_KEYWORDS = ("*DEFINE_CURVE", "*DEFINE_CURVE_TITLE")


def base_name(name: str) -> tuple[str, bool]:
    """Strip a trailing ``_TITLE`` option: ``*SET_NODE_LIST_TITLE`` -> (``*SET_NODE_LIST``, True).

    The ``_COLLECT`` option of ``*SET_*`` keywords (merge blocks with the same SID) does not change
    the cards, so it is stripped too: ``*SET_SHELL_GENERAL_COLLECT`` -> ``*SET_SHELL_GENERAL``.
    """
    titled = name.endswith("_TITLE")
    base = name[:-6] if titled else name
    if base.startswith("*SET_"):
        base = "_".join(token for token in base.split("_") if token != "COLLECT")
    return base, titled


def collected(name: str) -> bool:
    """``*SET_..._COLLECT``: blocks with the same SID form one merged set."""
    return name.startswith("*SET_") and "COLLECT" in name.split("_")


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
    """Member IDs in file order; blank and zero fields (row padding) are skipped.

    For ``*_ADD`` sets the members are set IDs. ``*_GENERATE`` sets hold ranges, not members.
    """
    if base_name(block.name)[0] in RANGE_SETS:
        raise FieldError(f"{block.name} holds ID ranges, not a member list; use positional editing")
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


RANGE_KINDS = {"*SET_NODE_LIST_GENERATE": "node", "*SET_PART_LIST_GENERATE": "part",
               "*SET_SHELL_LIST_GENERATE": "shell", "*SET_SOLID_GENERATE": "solid", "*SET_BEAM_GENERATE": "beam"}


def ranges(block: Block, long: bool = False) -> list[tuple[int, int]]:
    """``(first, last)`` ID ranges of a ``*SET_*_GENERATE`` block (zero pairs are padding)."""
    _, _, lines = split(block)
    values = []
    for index in lines:
        for text in _values(block.lines[index], 20 if long else 10, 8):
            value = parse_number(text)
            values.append(0 if value is None else value)
    pairs = []
    for first, last in zip(values[0::2], values[1::2]):
        if first == 0 and last == 0:
            continue
        if not (isinstance(first, int) and isinstance(last, int)):
            raise FieldError(f"Non-integer range in {block.name}")
        pairs.append((first, last))
    return pairs


TABLE_KEYWORDS = ("*DEFINE_TABLE", "*DEFINE_TABLE_TITLE")
TABLE_HEADER = (("tbid", "int", None), ("sfa", "float", 1.0), ("offa", "float", 0.0))
TABLE_ROW = [Column("value", "float", 0, 20, 0.0), Column("lcid", "int", 20, 20)]


def is_define_table(name: str) -> bool:
    return name in TABLE_KEYWORDS


def define_table_layout(block: Block, long: bool = False) -> Layout:
    """``*DEFINE_TABLE``: header (TBID, SFA, OFFA) and rows of VALUE (columns 1-20) and LCID (21-40).

    PyDYNA models only the values; LS-DYNA also accepts the curve ID on each row (when it is
    blank the curves follow the table in order). Rows are keyed by their position (1, 2, ...).
    """
    try:
        title, header, row_lines = split(block)
    except FieldError as error:
        raise Unsupported(str(error)) from error
    fields = [] if title is None else [FieldInfo("title", "str", FieldSlot(title, 0, 80), "title")]
    line = block.lines[header]
    spans = long_spans([10, 10, 10]) if long else [(0, 10), (10, 10), (20, 10)]
    for token, ((name, kind, default), (offset, width)) in enumerate(zip(TABLE_HEADER, spans)):
        slot = FieldSlot(header, offset, width, token if is_free_format(line) else None)
        fields.append(FieldInfo(name, kind, slot, "card1", default))
    rows: dict[int, tuple[int, ...]] = {}
    for index in row_lines:
        if is_blank(block.lines[index]):
            continue
        stray = stray_text(block.lines[index], [(0, 20), (20, 20)], long, tolerant=False)
        if stray:
            raise Unsupported(f"{block.name}: text outside VALUE/LCID on line {index} ({stray[:40]!r})")
        rows[len(rows) + 1] = (index,)
    return Layout(block.name, fields=fields, rows=RowMap(block, [TABLE_ROW], ["row"], rows), key="row",
                  source="builtin-table")


INTEGRATION_HEADER = (("irid", "int", None), ("nip", "int", 0), ("esop", "int", 0), ("failopt", "int", 0))
INTEGRATION_POINT = [Column("s", "float", 0, 10), Column("wf", "float", 10, 10), Column("pid", "int", 20, 10)]


def integration_shell_layout(block: Block, long: bool = False) -> Layout:
    """``*INTEGRATION_SHELL`` (R17 Vol I 29-16): card 1 IRID NIP ESOP FAILOPT, then NIP point
    cards S WF PID when ESOP = 0; points are rows keyed 1..NIP. One rule per block."""
    if long:
        raise Unsupported("Long-format *INTEGRATION_SHELL is not supported for named fields")
    lines = [(index, line) for index, line in block.data()]
    while lines and is_blank(lines[-1][1]):
        lines.pop()
    if not lines:
        raise Unsupported("*INTEGRATION_SHELL has no card 1")
    header, line = lines[0]
    free = is_free_format(line)
    fields = [FieldInfo(name, kind, FieldSlot(header, 10 * i, 10, i if free else None), "card1", default)
              for i, (name, kind, default) in enumerate(INTEGRATION_HEADER)]
    values = (_values(line, 10, 4) + ["", "", "", ""])[:4]
    try:
        nip, esop = parse_number(values[1]) or 0, parse_number(values[2]) or 0
    except FieldError as error:
        raise Unsupported(f"*INTEGRATION_SHELL: NIP/ESOP must be numbers ({error})") from error
    points = lines[1:]
    expected = nip if esop == 0 else 0
    if not isinstance(nip, int) or len(points) != expected:
        raise Unsupported(f"*INTEGRATION_SHELL: {len(points)} point lines for NIP={nip}, ESOP={esop} "
                          "(several rules in one block are not supported)")
    for index, text in points:
        stray = stray_text(text, [(c.offset, c.width) for c in INTEGRATION_POINT], tolerant=False)
        if stray:
            raise Unsupported(f"*INTEGRATION_SHELL: text outside S/WF/PID on line {index} ({stray[:40]!r})")
    rows = {number: (index,) for number, (index, _) in enumerate(points, 1)}
    return Layout(block.name, fields=fields, rows=RowMap(block, [INTEGRATION_POINT], ["point"], rows), key="row",
                  source="builtin-integration")


FLUX_NODES = [Column(f"n{i}", "int", 10 * (i - 1), 10) for i in range(1, 5)]
FLUX_DATA = [Column("lcid", "int", 0, 10)] + [Column(f"mlc{i}", "float", 10 * i, 10) for i in range(1, 5)] + [
    Column("loc", "int", 50, 10), Column("nhisv", "int", 60, 10)]


def flux_segment_layout(block: Block, long: bool = False) -> Layout:
    """``*BOUNDARY_FLUX_SEGMENT`` (R17 Vol I 5-46): per segment N1-N4, then LCID MLC1-MLC4 LOC NHISV,
    then ceil(NHISV/8) history-variable cards; segments are rows keyed 1, 2, ..."""
    if long:
        raise Unsupported("Long-format *BOUNDARY_FLUX_SEGMENT is not supported for named fields")
    lines = [index for index, line in block.data() if not is_blank(line)]
    rows: dict[int, tuple[int, ...]] = {}
    position, deepest = 0, 0
    while position < len(lines):
        if position + 2 > len(lines):
            raise Unsupported("*BOUNDARY_FLUX_SEGMENT: the LCID card of the last segment is missing")
        for index, columns in zip(lines[position:position + 2], (FLUX_NODES, FLUX_DATA)):
            stray = stray_text(block.lines[index], [(c.offset, c.width) for c in columns], tolerant=False)
            if stray:
                raise Unsupported(f"*BOUNDARY_FLUX_SEGMENT: text outside the fields on line {index} ({stray[:40]!r})")
        nhisv = (_values(block.lines[lines[position + 1]], 10, 7) + [""] * 7)[6]
        try:
            count = int(parse_number(nhisv) or 0)
        except (FieldError, ValueError) as error:
            raise Unsupported(f"*BOUNDARY_FLUX_SEGMENT: NHISV must be a number ({error})") from error
        extra = -(-count // 8)
        if position + 2 + extra > len(lines):
            raise Unsupported("*BOUNDARY_FLUX_SEGMENT: history-variable cards are missing")
        rows[len(rows) + 1] = tuple(lines[position:position + 2 + extra])
        deepest = max(deepest, extra)
        position += 2 + extra
    history = [[Column(f"hisv{8 * card + i}", "float", 10 * (i - 1), 10) for i in range(1, 9)]
               for card in range(deepest)]
    return Layout(block.name, rows=RowMap(block, [FLUX_NODES, FLUX_DATA] + history,
                                          ["segment", "flux"] + ["history"] * deepest, rows), key="row",
                  source="builtin-flux-segments")


SEGMENT_ROW = [Column("lcid", "int", 0, 10), Column("sf", "float", 10, 10, 1.0), Column("at", "float", 20, 10, 0.0)] + [
    Column(f"n{i}", "int", 20 + 10 * i, 10) for i in range(1, 6)]
SEGMENT_MID = [Column(f"n{i}", "int", 10 * (i - 6), 10) for i in range(6, 9)]


def load_segment_layout(block: Block, long: bool = False) -> Layout:
    """``*LOAD_SEGMENT``: one segment per row (LCID SF AT N1-N5), followed by an N6-N8 line only
    when that segment's N5 is non-zero (LS-DYNA R11 manual p. 28-64). PyDYNA reads the N6-N8
    card unconditionally and keeps one segment, so this layout is builtin."""
    if long:
        raise Unsupported("Long-format *LOAD_SEGMENT is not supported for named fields")
    lines = [index for index, line in block.data() if not is_blank(line)]
    rows: dict[int, tuple[int, ...]] = {}
    position = 0
    while position < len(lines):
        first = block.lines[lines[position]]
        stray = stray_text(first, [(c.offset, c.width) for c in SEGMENT_ROW], tolerant=False)
        if stray:
            raise Unsupported(f"*LOAD_SEGMENT: text outside the segment fields on line {lines[position]} ({stray[:40]!r})")
        n5 = _values(first, 10, 8)[7].strip() if len(_values(first, 10, 8)) > 7 else ""
        try:
            has_mid = parse_number(n5) not in (None, 0)
        except FieldError:
            has_mid = True  # parameter reference: a node is given
        count = 2 if has_mid else 1
        if position + count > len(lines):
            raise Unsupported("*LOAD_SEGMENT: the N6-N8 line of the last segment is missing")
        rows[len(rows) + 1] = tuple(lines[position:position + count])
        position += count
    template = [SEGMENT_ROW, SEGMENT_MID]
    return Layout(block.name, rows=RowMap(block, template, ["segment", "midside"], rows), key="row",
                  source="builtin-segments")


def _point_value(text: str, lookup: dict | None) -> float | int | None:
    if field_expression(text) is not None:
        value = resolve_field(text, lookup or {})
        if not isinstance(value, (int, float)):
            raise FieldError(f"Curve point {text.strip()!r} is not numeric")
        return value
    return parse_number(text)


def points(block: Block, lookup: dict | None = None) -> list[tuple[float, float]]:
    """Curve points ``(a, o)`` in file order; ``&name`` values are resolved with ``lookup``."""
    _, _, lines = split(block)
    result = []
    for index in lines:
        line = block.lines[index]
        a, o = (_values(line, 20, 2) + ["", ""])[:2]
        a_value, o_value = _point_value(a, lookup), _point_value(o, lookup)
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
