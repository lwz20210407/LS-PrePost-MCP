"""Keyword engine: row layouts for table keywords (elements, nodal BCs, segment sets)."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck, Unsupported

pytest.importorskip("ansys.dyna.core")


def _deck(tmp_path: Path, text: str) -> KeywordDeck:
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    return KeywordDeck.load(tmp_path / "main.k")


def test_element_shell_rows_by_eid(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*ELEMENT_SHELL\n"
                           "$#   eid     pid      n1      n2      n3      n4\n"
                           "      11       1       1       2       3       4\n"
                           "      12       1       2       5       6       3\n")
    block = deck.blocks("*ELEMENT_SHELL")[0]
    layout = deck.layout(block)
    assert layout.key == "eid" and sorted(layout.rows) == [11, 12]
    deck.set(block, "pid", 7, row=12)
    assert block.lines[3] == "      12       7       2       5       6       3\n"
    assert [row for _, row in deck.find("*ELEMENT_SHELL", pid=7)] == [12]


def test_element_solid_one_line_format(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*ELEMENT_SOLID\n"
                           "       1       2       1       2       3       4       5       6       7       8\n")
    block = deck.blocks("*ELEMENT_SOLID")[0]
    assert deck.get(block, "n8", row=1).value == 8
    deck.set(block, "pid", 3, row=1)
    assert block.lines[1] == "       1       3       1       2       3       4       5       6       7       8\n"


def test_element_solid_two_line_format(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*ELEMENT_SOLID\n"
                           "       1       2\n"
                           "       1       2       3       4       5       6       7       8       0       0\n"
                           "       2       2\n"
                           "       5       6       7       8       9      10      11      12       0       0\n")
    block = deck.blocks("*ELEMENT_SOLID")[0]
    assert sorted(deck.layout(block).rows) == [1, 2]
    assert deck.get(block, "n1", row=2).value == 5


def test_spc_node_with_id_option(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*BOUNDARY_SPC_NODE_ID\n"
                           "         5fixed base\n"
                           "       101         0         1         1         1         0         0         0\n"
                           "       102         0         1         1         1         0         0         0\n")
    block = deck.blocks("*BOUNDARY_SPC_NODE")[0]
    assert deck.get(block, "id").value == 5
    deck.set(block, "dofrx", 1, row=102)
    assert block.lines[3] == "       102         0         1         1         1         1         0         0\n"


def test_segment_set_header_and_rows(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*SET_SEGMENT\n"
                           "         3\n"
                           "         1         2         3         4\n"
                           "         1         2         3         4\n")
    block = deck.blocks("*SET_SEGMENT")[0]
    layout = deck.layout(block)
    assert layout.key == "row"  # duplicate n1 values -> numbered rows
    assert deck.get(block, "sid").value == 3
    deck.set(block, "n4", 9, row=2)
    assert block.lines[3] == "         1         2         3         9\n"
    assert [r for _, r in deck.find("*SET_SEGMENT", sid=3)] == [None]


def test_irregular_table_is_refused(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*ELEMENT_SOLID\n"
                           "       1       2\n"
                           "       1       2       3       4       5       6       7       8       0       0\n"
                           "       2       2\n")
    with pytest.raises(Unsupported):
        deck.layout(deck.blocks("*ELEMENT_SOLID")[0])
