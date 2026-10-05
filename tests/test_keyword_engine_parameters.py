"""Keyword engine: editing *PARAMETER values for parametric studies."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import FieldError, KeywordDeck

MAIN = ("*KEYWORD\n"
        "*PARAMETER\n"
        "R thick          2.0I nipp             3\n"
        "*PARAMETER_EXPRESSION\n"
        "R thick2   thick*2\n"
        "*parameter\n"
        "rvel, 800.0, imode, 1\n"
        "*INCLUDE\n"
        "sub.k\n"
        "*END\n")
SUB = ("*PARAMETER_LOCAL\n"
       "R thick          5.0\n")


@pytest.fixture
def deck(tmp_path: Path) -> KeywordDeck:
    (tmp_path / "main.k").write_bytes(MAIN.encode("ascii"))
    (tmp_path / "sub.k").write_bytes(SUB.encode("ascii"))
    return KeywordDeck.load(tmp_path / "main.k")


def _value(deck: KeywordDeck, name: str, local: bool = False) -> object:
    return [r.definition.value for r in deck.parameters
            if r.definition.name.lower() == name.lower() and r.definition.local == local][0]


def test_fixed_value_edit_updates_dependent_expression(deck: KeywordDeck) -> None:
    deck.set_parameter("thick2", "thick*3")  # expression text
    deck.set_parameter("thick", 2.5, file=str(deck.main.path))
    assert _value(deck, "thick") == 2.5
    assert _value(deck, "thick2") == 7.5
    assert deck.main.blocks[1].lines[1] == "R thick          2.5I nipp             3\n"
    assert deck.main.blocks[2].lines[1] == "R thick2   thick*3\n"


def test_same_name_in_two_files_needs_file(deck: KeywordDeck) -> None:
    with pytest.raises(FieldError):
        deck.set_parameter("thick", 1.0)
    sub = [f for f in deck.files.values() if f.path.name == "sub.k"][0]
    deck.set_parameter("thick", 6.0, file=str(sub.path))
    assert _value(deck, "thick", local=True) == 6.0
    assert _value(deck, "thick") == 2.0


def test_integer_parameter_rejects_fraction(deck: KeywordDeck) -> None:
    with pytest.raises(FieldError):
        deck.set_parameter("nipp", 2.5)
    deck.set_parameter("nipp", 5)
    assert _value(deck, "nipp") == 5


def test_comma_format_parameter(deck: KeywordDeck) -> None:
    deck.set_parameter("vel", 950.0)
    assert deck.main.blocks[3].lines[1] == "rvel, 950.0, imode, 1\n"
    assert _value(deck, "vel") == 950.0


def test_invalid_expression_is_reverted(deck: KeywordDeck) -> None:
    before = deck.main.text()
    with pytest.raises(FieldError):
        deck.set_parameter("thick2", "undefined_name*2")
    assert deck.main.text() == before
    assert _value(deck, "thick2") == 4.0


def test_unknown_parameter(deck: KeywordDeck) -> None:
    with pytest.raises(KeyError):
        deck.set_parameter("nothing", 1.0)
