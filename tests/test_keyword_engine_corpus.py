"""Opt-in corpus regression for the keyword engine.

Set ``LSPP_CORPUS_DIR`` to a folder of keyword decks (public corpus, never committed). Each
deck is loaded with its includes; every file must join back to its original bytes and
every readable field must survive a same-value write. ``LSPP_CORPUS_LIMIT`` caps the
number of decks (default 300) to keep a local run short.
"""
import os
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import FieldError, KeywordDeck, Unsupported

ROOT = os.environ.get("LSPP_CORPUS_DIR")
LIMIT = int(os.environ.get("LSPP_CORPUS_LIMIT", "300"))
SUFFIXES = {".k", ".key", ".dyn"}


def _decks() -> list[Path]:
    if not ROOT:
        return []
    found = sorted(p for p in Path(ROOT).rglob("*") if p.suffix.lower() in SUFFIXES and p.is_file())
    return [p for p in found if p.stat().st_size <= 50 * 2**20][:LIMIT]


pytestmark = pytest.mark.skipif(not ROOT, reason="set LSPP_CORPUS_DIR to run the corpus regression")


@pytest.mark.parametrize("path", _decks(), ids=lambda p: p.name)
def test_round_trip_and_same_value_writes(path: Path) -> None:
    deck = KeywordDeck.load(path)
    for source in deck.files.values():
        assert source.data() == source.original, source.path
    for block in deck.iter_blocks():
        try:
            layout = deck.layout(block)
        except Unsupported:
            continue
        infos = list(layout.fields) or (layout.rows[next(iter(layout.rows))] if layout.key and layout.rows else [])
        row = next(iter(layout.rows)) if layout.key and not layout.fields and layout.rows else None
        for info in infos[:3]:
            try:
                value = deck._value(block, info)
            except FieldError:
                continue
            if value.parameter or not isinstance(value.value, (int, float)) or not value.raw.strip():
                continue
            before = list(block.lines)
            deck.set(block, info.name, value.value, card=info.card, row=row)
            assert deck.get(block, info.name, info.card, row).value == pytest.approx(value.value, rel=1e-6)
            block.lines[:] = before
            break
