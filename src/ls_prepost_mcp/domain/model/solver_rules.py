"""Input rules LS-DYNA enforces at read time or mishandles silently (used by ``check_deck``).

* Free-format items longer than their field: R11 stops with Error 10459 "item n of line is too
  long" (comma-separated values still have to fit the fixed field width).
* Prescribed motion whose curve ends before the motion should stop: past the last point R11
  takes the prescribed value as 0. Seen on 2026-10-06 converting Peridigm twist_and_pull: the
  rigid grips snapped back to their initial position in the state written just after the last
  curve point, while the run terminated normally.
"""
from __future__ import annotations

import warnings
from functools import lru_cache
from typing import TYPE_CHECKING

from .fields import FieldError
from .layouts import RowMap, Unsupported
from .lists import is_curve
from .parameters import field_expression
from .schema import _pydyna_class
from .text import body

if TYPE_CHECKING:
    from .blocks import Block
    from .deck import KeywordDeck

MOTION = "*BOUNDARY_PRESCRIBED_MOTION"


def _site(block: Block, index: int | None = None) -> dict:
    line = block.line_number + (index or 0)
    return {"keyword": block.name, "file": str(block.file.path), "line": line}


def _flag(found: list[dict], block: Block, index: int, field: str, token: str, width: int) -> None:
    text = token.strip()
    if len(text) > width and field_expression(text) is None:
        found.append({**_site(block, index), "field": field, "text": text, "width": width})


@lru_cache(maxsize=None)
def _one_card_columns(name: str) -> tuple[tuple[str, int], ...]:
    """Columns of a keyword PyDYNA defines with a single card (one data line per row), else ()."""
    try:
        cls, _ = _pydyna_class(name)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cards = cls()._cards
    except Exception:  # noqa: BLE001 - any PyDYNA failure means "no fallback"
        return ()
    fields = getattr(cards[0], "_fields", None) if len(cards) == 1 else None
    return tuple((f.name.lower(), int(f.width)) for f in fields or ())


def long_free_items(deck: KeywordDeck, limit: int = 50) -> tuple[int, list[dict]]:
    """(count, sample) of comma-separated items wider than their field.

    Uses the engine's layout; table keywords it has no layout for (*INITIAL_VELOCITY_NODE, ...)
    are checked against PyDYNA's columns when PyDYNA defines them with a single card.
    """
    found: list[dict] = []
    for block in deck.iter_blocks():
        comma = {i for i, line in enumerate(block.lines[1:], 1) if "," in body(line)}
        if not comma:
            continue
        try:
            layout = deck.layout(block)
        except (Unsupported, FieldError, KeyError, ValueError):
            layout = None
        if layout is None or (not layout.fields and not len(layout.rows)):
            columns = _one_card_columns(block.name) if deck.format == "standard" and "TITLE" not in block.name else ()
            for index in sorted(comma):
                for token, (name, width) in zip(body(block.lines[index]).split(","), columns):
                    _flag(found, block, index, name, token, width)
            continue
        rows = layout.rows
        infos = list(layout.fields)
        if not isinstance(rows, RowMap):  # small tables come as plain {key: [FieldInfo]}
            infos += [info for row in rows.values() for info in row]
        for info in infos:
            if info.slot.token is not None and info.slot.line in comma:
                tokens = body(block.lines[info.slot.line]).split(",")
                if info.slot.token < len(tokens):
                    _flag(found, block, info.slot.line, info.name, tokens[info.slot.token], info.slot.width)
        if isinstance(rows, RowMap):
            for _, indices in rows.lines():
                for position, index in enumerate(indices):
                    if index in comma:
                        tokens = body(block.lines[index]).split(",")
                        for token, column in zip(tokens, rows.template[position]):
                            _flag(found, block, index, column.name, token, column.width)
    return len(found), found[:limit]


def _number(deck: KeywordDeck, block: Block, name: str, default: float = 0.0) -> float:
    try:
        value = deck.get(block, name).value
    except (KeyError, FieldError, Unsupported):
        return default
    return default if value in (None, "") or isinstance(value, str) else float(value)


def short_motion_curves(deck: KeywordDeck) -> list[dict]:
    """Prescribed motions active after their curve's last abscissa (SFA / OFFA applied)."""
    endtim = None
    for block in deck.blocks("*CONTROL_TERMINATION"):
        endtim = _number(deck, block, "endtim") or endtim
    curves = {}
    for block in deck.iter_blocks():
        if is_curve(block.name):
            try:
                points = deck.points(block)
            except (Unsupported, FieldError):
                continue
            if points:
                sfa = _number(deck, block, "sfa") or 1.0
                curves[int(_number(deck, block, "lcid"))] = (max(a for a, _ in points) * sfa + _number(deck, block, "offa"),
                                                            block)
    found = []
    for block in deck.iter_blocks():
        if not block.name.startswith(MOTION):
            continue
        try:
            layout = deck.layout(block)
        except (Unsupported, FieldError, KeyError, ValueError):
            continue
        groups = [layout.fields] if not isinstance(layout.rows, RowMap) or not len(layout.rows) else \
            [layout.rows[key] for key in layout.rows]
        for infos in groups:
            values = {info.name: deck._value(block, info).value for info in infos}
            lcid = values.get("lcid")
            if not isinstance(lcid, (int, float)) or int(lcid) not in curves:
                continue
            death = values.get("death")
            death = 1e28 if not isinstance(death, (int, float)) or death == 0 else float(death)
            stop = min(death, endtim) if endtim else death
            last, curve = curves[int(lcid)]
            if last < stop:
                found.append({**_site(block), "lcid": int(lcid), "curve_end": last, "active_until": stop,
                              "curve": _site(curve)})
    return found


__all__ = ["long_free_items", "short_motion_curves"]
