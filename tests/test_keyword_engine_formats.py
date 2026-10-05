"""Keyword engine: number formats, keyword spelling and block shapes found in real decks."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck, Unsupported
from ls_prepost_mcp.domain.model.fields import parse_number


@pytest.mark.parametrize(("text", "value"), [
    (" 1.13000-4", 1.13e-4), (" 2.1000+11", 2.1e11), ("1.0d-3", 1e-3), ("10-3", 1e-2),
    ("-5", -5), ("  ", None), (".5", 0.5), ("7.85e-9", 7.85e-9)])
def test_fortran_number_forms(text: str, value: float | None) -> None:
    assert parse_number(text) == (pytest.approx(value) if value is not None else None)


def _deck(tmp_path: Path, text: str) -> KeywordDeck:
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    return KeywordDeck.load(tmp_path / "main.k")


def test_lower_case_keyword_and_implicit_exponent(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, "*mat_elastic\n         1 7.85000-9 2.1000+05       0.3\n*end\n")
    block = deck.blocks("*MAT_ELASTIC")[0]
    assert deck.get(block, "ro").value == pytest.approx(7.85e-9)
    deck.set(block, "e", 70000.0)
    assert block.lines[1] == "         1 7.85000-9   70000.0       0.3\n"
    assert block.lines[0] == "*mat_elastic\n"


def test_repeated_card_instances_under_one_keyword(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, "*DEFINE_VECTOR\n"
                           "         1       0.0       0.0       0.0       1.0       0.0       0.0\n"
                           "         2       0.0       0.0       0.0       0.0       1.0       0.0\n")
    block = deck.blocks("*DEFINE_VECTOR")[0]
    layout = deck.layout(block)
    assert layout.key == "instance" and sorted(layout.rows) == [1, 2]
    assert deck.get(block, "vid", row=2).value == 2
    deck.set(block, "zt", 1.0, row=2)
    assert block.lines[2] == "         2       0.0       0.0       1.0       0.0       1.0       0.0\n"


def test_title_keyword_builtin(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*KEYWORD\n*TITLE\nold title\n*END\n")
    block = deck.blocks("*TITLE")[0]
    deck.set(block, "title", "new title")
    assert block.lines[1] == "new title\n"


def test_encrypted_block_is_refused(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*NODE\n-----BEGIN PGP MESSAGE-----\nabc\n-----END PGP MESSAGE-----\n")
    with pytest.raises(Unsupported):
        deck.layout(deck.blocks("*NODE")[0])


def test_unused_fields_are_not_editable(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, "*CONTROL_THERMAL_SOLVER\n"
                           "         1         0         0 1.0000E-4\n"
                           "         0       500\n")
    names = {info.name for info in deck.layout(deck.blocks("*CONTROL_THERMAL_SOLVER")[0]).fields}
    assert names and not any(name.startswith("unused") for name in names)
