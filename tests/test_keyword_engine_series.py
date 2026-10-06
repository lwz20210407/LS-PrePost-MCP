"""Keyword engine: PyDYNA series cards (e.g. layer angles of *SECTION_SHELL with ICOMP=1)."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck

pytest.importorskip("ansys.dyna.core")


def _deck(tmp_path: Path, text: str) -> KeywordDeck:
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    return KeywordDeck.load(tmp_path / "main.k")


def test_layer_angles_by_name(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*SECTION_SHELL_TITLE\n"
                           "laminate\n"
                           "         7        16  0.833333        10       1.0         0         1\n"
                           "       2.0       2.0       2.0       2.0\n"
                           "       0.0      45.0     -45.0      90.0       0.0      45.0     -45.0      90.0\n"
                           "      45.0     -45.0\n")
    block = deck.blocks("*SECTION_SHELL")[0]
    assert deck.get(block, "icomp").value == 1
    assert deck.get(block, "angle3").value == -45.0 and deck.get(block, "angle10").value == -45.0
    deck.set(block, "angle10", 30.0)
    assert block.lines[5] == "      45.0      30.0\n"
    with pytest.raises(KeyError):
        deck.get(block, "angle11")


def test_section_without_layers_has_no_angles(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*SECTION_SHELL\n         1        16\n       2.0       2.0       2.0       2.0\n")
    names = {info.name for info in deck.layout(deck.blocks("*SECTION_SHELL")[0]).fields}
    assert "t1" in names and not any(name.startswith("angle") for name in names)
