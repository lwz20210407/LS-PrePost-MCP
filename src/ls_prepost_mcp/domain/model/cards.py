"""New keyword cards from field values (PyDYNA writes the text, the engine checks it)."""
from __future__ import annotations

import math
import warnings
from typing import TYPE_CHECKING

from .blocks import Block, SourceFile, make_blocks
from .fields import FieldError, write_text
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
            key = name.lower()
            if not isinstance(getattr(type(card), key, None), property):
                raise FieldError(f"{keyword} has no field {name!r}")
            setattr(card, key, value)
        text = card.write()
    return _blank_unset("\n".join(line.rstrip() for line in text.splitlines()) + "\n", fields)


def _blank_unset(text: str, fields: dict[str, object]) -> str:
    """Blank every numeric cell the caller did not set, so LS-DYNA applies its own defaults.

    PyDYNA writes its static defaults, but some LS-DYNA defaults depend on other fields: on
    *HOURGLASS, QB and QW default to QM (R17 Vol I), and PyDYNA's written 0.1 would override a
    given QM. A blank field is read as the default (R11 Vol I, General Card Format).
    """
    block = make_blocks(text, "\n")[0]
    given = {name.lower() for name in fields}
    for info in block_layout(block, {}).fields:
        if info.name not in given and info.kind != "str":
            block.lines[info.slot.line] = write_text(block.lines[info.slot.line], info.slot, "")
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
