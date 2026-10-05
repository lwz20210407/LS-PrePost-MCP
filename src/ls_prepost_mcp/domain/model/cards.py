"""New keyword cards from field values (PyDYNA writes the text, the engine checks it)."""
from __future__ import annotations

import math
import warnings
from typing import TYPE_CHECKING

from .blocks import Block, SourceFile
from .fields import FieldError
from .layouts import Unsupported
from .schema import _pydyna_class

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
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


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
