"""New keyword cards from field values (PyDYNA writes the text, the engine checks it)."""
from __future__ import annotations

import math
import warnings
from typing import TYPE_CHECKING

from .blocks import Block, SourceFile, make_blocks
from .fields import FieldError, format_value, parse_number, read_text, single_line, write_text
from .layouts import Unsupported
from .schema import _pydyna_class
from .schema import layout as block_layout

if TYPE_CHECKING:
    from .deck import KeywordDeck


def card_text(keyword: str, fields: dict[str, object], options: list[str] | None = None) -> str:
    """Standard-format text of one keyword with the given field values.

    Option suffixes in ``keyword`` (``*MAT_ELASTIC_TITLE``) or ``options`` are activated.
    Unknown field names raise :class:`FieldError`; table keywords (nodes, elements) are refused.
    """
    cls, base = _pydyna_class(keyword.upper())
    card = cls()
    if any(type(c).__name__ in ("TableCard", "TableCardGroup", "SeriesCard") for c in card._cards):
        raise FieldError(f"{keyword} is a table/list keyword; insert its text or use set/members operations")
    wanted = [t for t in keyword.upper()[len(base) + 1:].split("_") if t] + [o.upper() for o in options or []]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for option in wanted:
            try:
                card.activate_option(option)
            except Exception as error:  # PyDYNA raises different types for unknown options
                raise FieldError(f"{keyword}: unknown option {option!r}") from error
        for name, value in fields.items():
            if isinstance(value, str):
                single_line(value, f"{keyword} {name}")
            key = name.lower()
            if not isinstance(getattr(type(card), key, None), property):
                raise FieldError(f"{keyword} has no field {name!r}")
            setattr(card, key, value)
        text = card.write()
    return _settle_fields("\n".join(line.rstrip() for line in text.splitlines()) + "\n", base, fields)


# Fields whose LS-DYNA default is another field's value. They stay blank so the solver derives
# them; PyDYNA's written static default would override the derived one. *HOURGLASS QB, QW = QM
# (R17 Vol I); the others from the PyDYNA help texts ("default = SFS1", ...).
DERIVED_DEFAULTS = {
    "*HOURGLASS": {"qb", "qb_vdc", "qw"},
    "*MAT_029": {"sfs2", "sft2"}, "*MAT_FORCE_LIMITED": {"sfs2", "sft2"},
    "*MAT_139": {"yms2", "ymt2"}, "*MAT_MODIFIED_FORCE_LIMITED": {"yms2", "ymt2"},
    "*SENSOR_SWITCH_SHELL_TO_VENT": {"c23v"},
}


def _is_zero(text: str) -> bool:
    try:
        return parse_number(text) in (None, 0)
    except FieldError:
        return False


def _settle_fields(text: str, base: str, fields: dict[str, object]) -> str:
    """Rewrite PyDYNA's card text field by field.

    * Given numbers are written with the engine's formatter, with as many digits as the field
      holds (PyDYNA keeps five in a 10-column field, so 1.79998e12 came out as 1.8e12).
    * Numeric fields the caller did not set keep PyDYNA's default when it is nonzero, written
      out: a blank is read as 0, and R11 does not always replace 0 by the manual default (a
      blank *MAT_ELASTIC_PERI GT breaks every bond at the first step).
    * Zero defaults and :data:`DERIVED_DEFAULTS` are left blank.
    """
    block = make_blocks(text, "\n")[0]
    given = {name.lower(): value for name, value in fields.items()}
    derived = DERIVED_DEFAULTS.get(base, set())
    for info in block_layout(block, {}).fields:
        if info.kind == "str":
            continue
        line = block.lines[info.slot.line]
        if info.name in given:
            value = given[info.name]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                block.lines[info.slot.line] = write_text(line, info.slot,
                                                         format_value(value, info.slot.width, info.kind)[0])
        elif info.name in derived or _is_zero(read_text(line, info.slot).strip()):
            block.lines[info.slot.line] = write_text(line, info.slot, "")
    return "".join(line.rstrip() + "\n" for line in block.lines)


def _same(read: object, wanted: object) -> bool:
    if isinstance(wanted, str):
        return str(read or "").strip() == wanted.strip()
    if read is None or isinstance(read, str):
        return False
    return math.isclose(float(read), float(wanted), rel_tol=1e-6, abs_tol=1e-30)


def insert_card(deck: KeywordDeck, keyword: str, fields: dict[str, object], *, options: list[str] | None = None,
                file: SourceFile | None = None, before: Block | None = None, after: Block | None = None) -> list[Block]:
    """Insert a generated card and verify every given field by reading it back."""
    blocks = deck.insert(card_text(keyword, fields, options), file=file, before=before, after=after)
    block = blocks[0]
    try:
        for name, value in fields.items():
            read = deck.get(block, name).value
            if not _same(read, value):
                raise FieldError(f"{keyword}.{name}: wrote {value!r} but read back {read!r}")
    except (FieldError, Unsupported, KeyError) as error:
        deck.delete(block, force=True)
        raise FieldError(f"Generated {keyword} failed verification: {error}") from error
    return blocks
