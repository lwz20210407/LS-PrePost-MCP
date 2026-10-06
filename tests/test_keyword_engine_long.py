"""Keyword engine: long format (20-character fields), per keyword (+) and global (LONG=Y)."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck


def _f(*values: object) -> str:
    return "".join(str(v).rjust(20) for v in values) + "\n"


def _deck(tmp_path: Path, text: str) -> KeywordDeck:
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    return KeywordDeck.load(tmp_path / "main.k")


def test_plus_flag_material_named_fields(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, "*MAT_ELASTIC+\n" + _f(1, 7.85e-9, 210000.0, 0.3) + "*END\n")
    block = deck.blocks("*MAT_ELASTIC")[0]
    assert deck.get(block, "e").value == 210000.0
    deck.set(block, "e", 70000.0)
    assert block.lines[1] == _f(1, 7.85e-9, 70000.0, 0.3)


def test_global_long_nodes_and_parts(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*KEYWORD LONG=Y\n*NODE\n" + _f(1, 0.0, 0.0, 0.0) + _f(2, 10.0, 0.0, 0.0)
                 + "*PART\nplate\n" + _f(1, 2, 3) + "*END\n")
    assert deck.format == "long"
    nodes = deck.blocks("*NODE")[0]
    deck.set(nodes, "y", 2.5, row=2)
    assert nodes.lines[2] == _f(2, 10.0, 2.5, 0.0)
    part = deck.blocks("*PART")[0]
    assert deck.get(part, "mid", row=1).value == 3


def test_minus_flag_overrides_global_long(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*KEYWORD LONG=Y\n*NODE-\n"
                           "       1             0.0             0.0             0.0\n*END\n")
    block = deck.blocks("*NODE")[0]
    deck.set(block, "x", 1.5, row=1)
    assert block.lines[1] == "       1             1.5             0.0             0.0\n"


def test_long_list_set_members(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*SET_NODE_LIST+\n" + _f(7) + _f(1, 2, 3) + "*END\n")
    block = deck.blocks("*SET_NODE_LIST")[0]
    assert deck.get(block, "sid").value == 7 and deck.members(block) == [1, 2, 3]
    deck.set_members(block, [4, 5])
    assert block.lines[2] == _f(4, 5)


def test_long_element_table(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, "*ELEMENT_SHELL+\n" + _f(1, 1, 1, 2, 3, 4) + "*END\n")
    block = deck.blocks("*ELEMENT_SHELL")[0]
    deck.set(block, "pid", 9, row=1)
    assert block.lines[1] == _f(1, 9, 1, 2, 3, 4)
