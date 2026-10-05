"""Reading and writing single fields while keeping the rest of a line intact."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .text import body, ending

_EXP = re.compile(r"e([+-])0*(\d)")
_FORTRAN_D = re.compile(r"(?<=[0-9.])[dD](?=[+-]?\d)")
_IMPLICIT_EXP = re.compile(r"^([+-]?(?:\d+\.\d*|\.\d+|\d+))([+-]\d+)$")


class FieldError(ValueError):
    """A value cannot be read from or written into a field."""


@dataclass(frozen=True)
class FieldSlot:
    """Where a field lives: data line index in its block plus column range or token index."""

    line: int
    offset: int
    width: int
    token: int | None = None  # set when the line is comma separated


def is_free_format(line: str) -> bool:
    """LS-DYNA treats a data line containing a comma as free (comma separated) format."""
    return "," in body(line)


def read_text(line: str, slot: FieldSlot) -> str:
    """Return the raw (unstripped) text of a field."""
    text = body(line)
    if slot.token is not None:
        tokens = text.split(",")
        return tokens[slot.token] if slot.token < len(tokens) else ""
    return text[slot.offset:slot.offset + slot.width]


def _styled_cell(old: str, value: str, width: int, align: str) -> str:
    """New cell text that follows the alignment of the old cell (blank cells use ``align``)."""
    padded = old.ljust(width)
    if not padded.strip():
        return value.rjust(width) if align == "right" else value.ljust(width)
    lead = len(padded) - len(padded.lstrip(" "))
    if padded[-1] != " ":
        return value.rjust(width)  # right-anchored, the usual LS-PrePost style
    if lead and lead + len(value) <= width:
        return (" " * lead + value).ljust(width)  # keep the original indentation
    return value.ljust(width)


def write_text(line: str, slot: FieldSlot, value: str, align: str = "right") -> str:
    """Replace one field, leaving every other character and the line ending unchanged.

    The new value follows the alignment of the old one, so only the value itself changes.
    """
    text, end = body(line), ending(line)
    if slot.token is not None:
        tokens = text.split(",")
        while len(tokens) <= slot.token:
            tokens.append("")
        old = tokens[slot.token]
        lead, trail = old[:len(old) - len(old.lstrip())], old[len(old.rstrip()):] if old.strip() else ""
        tokens[slot.token] = lead + value + trail
        return ",".join(tokens) + end
    if len(value) > slot.width:
        raise FieldError(f"{value!r} does not fit in a {slot.width}-character field")
    if len(text) < slot.offset:
        text += " " * (slot.offset - len(text))
    right = text[slot.offset + slot.width:]
    ended_inside = len(body(line)) < slot.offset + slot.width
    cell = _styled_cell(text[slot.offset:slot.offset + slot.width], value, slot.width, align)
    new = text[:slot.offset] + cell + right
    if ended_inside and not right:
        new = new.rstrip(" ")  # the old line ended inside this field: add no trailing padding
    return new + end


def parse_number(text: str) -> float | int | None:
    """Parse an LS-DYNA numeric field; blank returns None.

    Accepts Fortran forms: ``1.0d-3`` and exponents without a letter (``1.13000-4``,
    ``2.1000+11``), which LS-DYNA reads as ``1.13e-4`` and ``2.1e11``.
    """
    stripped = text.strip()
    if not stripped:
        return None
    normalized = _FORTRAN_D.sub("e", stripped)
    try:
        return int(normalized)
    except ValueError:
        pass
    implicit = _IMPLICIT_EXP.match(normalized)
    if implicit:
        normalized = implicit.group(1) + "e" + implicit.group(2)
    try:
        return float(normalized)
    except ValueError as error:
        raise FieldError(f"Not a number: {stripped!r}") from error


def _compact(text: str) -> str:
    """Shorten exponents: ``7.85e-09`` -> ``7.85e-9``, ``1e+21`` -> ``1e21``."""
    return _EXP.sub(lambda m: "e" + ("-" if m.group(1) == "-" else "") + m.group(2), text)


def format_value(value: object, width: int, kind: str = "auto") -> tuple[str, bool]:
    """Format ``value`` for a field of ``width`` characters.

    Returns the text and whether it reads back exactly. Strings (titles, ``&param``
    references) are written as given. ``kind`` is ``int``, ``float``, ``str`` or ``auto``.
    """
    if isinstance(value, str):
        if len(value) > width:
            raise FieldError(f"{value!r} does not fit in a {width}-character field")
        return value, True
    if isinstance(value, bool):
        raise FieldError("Boolean values are not LS-DYNA field values")
    if kind == "int" or (kind == "auto" and isinstance(value, int)):
        if isinstance(value, float):
            if not value.is_integer():
                raise FieldError(f"{value} is not an integer")
            value = int(value)
        text = str(int(value))
        if len(text) > width:
            raise FieldError(f"{text} does not fit in a {width}-character field")
        return text, True
    number = float(value)
    if not math.isfinite(number):
        raise FieldError("Non-finite values cannot be written")
    shortest = repr(number)
    for candidate in (shortest, _compact(shortest)):
        if len(candidate) <= width:
            return candidate, True
    for precision in range(width, 0, -1):
        candidate = _compact(f"{number:.{precision}g}")
        if "." not in candidate and "e" not in candidate and len(candidate) < width:
            candidate += "."
        if len(candidate) <= width:
            return candidate, float(candidate) == number
    raise FieldError(f"{number} cannot be represented in {width} characters")
