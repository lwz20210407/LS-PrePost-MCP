"""New cards from field values (PyDYNA text) with read-back verification."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import FieldError, KeywordDeck
from ls_prepost_mcp.domain.model.cards import card_text
from ls_prepost_mcp.domain.model.operations import edit_deck, inspect_deck

pytest.importorskip("ansys.dyna.core")


def _deck(tmp_path: Path) -> KeywordDeck:
    (tmp_path / "main.k").write_bytes(b"*KEYWORD\n*END\n")
    return KeywordDeck.load(tmp_path / "main.k")


def test_card_text_with_title_option() -> None:
    text = card_text("*MAT_ELASTIC_TITLE", {"title": "steel", "mid": 3, "ro": 7.85e-9, "e": 210000.0, "pr": 0.3})
    assert text.startswith("*MAT_ELASTIC_TITLE\n") and "steel\n" in text
    assert all(line == line.rstrip() for line in text.splitlines())


def test_unknown_field_and_table_keyword_are_refused() -> None:
    with pytest.raises(FieldError):
        card_text("*MAT_ELASTIC", {"youngs_modulus": 1.0})
    with pytest.raises(FieldError):
        card_text("*NODE", {"nid": 1})


def test_insert_card_before_end_and_read_back(tmp_path: Path) -> None:
    deck = _deck(tmp_path)
    deck.insert_card("*CONTACT_AUTOMATIC_SURFACE_TO_SURFACE_ID",
                     {"cid": 9, "heading": "impact", "surfa": 1, "surfb": 2, "surfatyp": 3, "surfbtyp": 3, "fs": 0.2})
    block = deck.blocks("*CONTACT_AUTOMATIC_SURFACE_TO_SURFACE")[0]
    assert deck.get(block, "fs").value == 0.2 and deck.get(block, "cid").value == 9
    assert deck.main.blocks[-1].name == "*END"


def test_edit_deck_inserts_cards_by_fields(tmp_path: Path) -> None:
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "main.k").write_bytes(b"*KEYWORD\n*END\n")
    edits = [{"op": "insert", "card": {"keyword": "*MAT_PIECEWISE_LINEAR_PLASTICITY_TITLE",
                                       "fields": {"title": "tc4", "mid": 1, "ro": 4.43e-9, "e": 110000.0,
                                                  "pr": 0.34, "sigy": 950.0}}},
             {"op": "insert", "card": {"keyword": "*CONTROL_TERMINATION", "fields": {"endtim": 5e-5}}}]
    result = edit_deck(str(tmp_path / "in" / "main.k"), edits, output_dir=str(tmp_path / "out"))
    assert result["status"] == "succeeded", result
    info = inspect_deck(str(tmp_path / "out" / "main.k"))
    assert info["materials"][0]["mid"] == 1 and info["materials"][0]["title"] == "tc4"
