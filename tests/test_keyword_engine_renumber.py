"""Keyword-level renumbering, duplicate-node merging and element deletion (P08)."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import FieldError, KeywordDeck
from ls_prepost_mcp.domain.model.geometry import elements, nodes
from ls_prepost_mcp.domain.model.quality import check_quality
from ls_prepost_mcp.domain.model.renumber import (
    delete_elements,
    merge_duplicate_nodes,
    renumber,
    renumber_range,
)

pytest.importorskip("ansys.dyna.core")

A = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
B = [(x + 1, y, z) for x, y, z in A]


def _model(extra: str = "") -> str:
    node_text = "".join(f"{i + 1:>8}{float(x):>16}{float(y):>16}{float(z):>16}\n" for i, (x, y, z) in enumerate(A + B))
    hexes = "".join(f"{e:>8}{1:>8}" + "".join(f"{n:>8}" for n in range(first, first + 8)) + "\n"
                    for e, first in ((1, 1), (2, 9)))
    return ("*KEYWORD\n*PART\nblock\n         1         1         1\n*SECTION_SOLID\n         1         1\n"
            "*MAT_ELASTIC\n         1    7.8e-9  210000.0       0.3\n*NODE\n" + node_text + "*ELEMENT_SOLID\n" + hexes
            + "*SET_NODE_LIST\n         1\n         1         2         9\n*SET_PART_LIST\n         2\n         1\n"
            "*BOUNDARY_SPC_NODE\n         1         0         1         1         1         0         0         0\n"
            "*DATABASE_HISTORY_NODE\n         2         9\n" + extra + "*END\n")


def _deck(tmp_path: Path, text: str) -> KeywordDeck:
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    return KeywordDeck.load(tmp_path / "main.k")


def test_renumber_nodes_everywhere(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _model())
    result = renumber(deck, "node", {1: 101, 9: 109})
    assert result["renumbered"] == 2
    assert deck.members(deck.blocks("*SET_NODE_LIST")[0]) == [101, 2, 109]
    assert deck.get(deck.blocks("*BOUNDARY_SPC_NODE")[0], "nid", row=101).value == 101
    assert deck.get(deck.blocks("*DATABASE_HISTORY_NODE")[0], "id2").value == 109
    assert elements(deck, "*ELEMENT_SOLID", 8)[2][:, 0].tolist() == [101, 109]
    assert deck.references().dangling_count == 0
    deck.save_as(tmp_path / "out")
    assert set(nodes(KeywordDeck.load(tmp_path / "out" / "main.k"))[0].tolist()) >= {101, 109}


def test_renumber_part_reaches_elements_and_sets(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _model())
    renumber(deck, "part", {1: 5})
    assert elements(deck, "*ELEMENT_SOLID", 8)[1].tolist() == [5, 5]
    assert deck.members(deck.blocks("*SET_PART_LIST")[0]) == [5]
    assert deck.references().dangling_count == 0


def test_renumber_refusals_change_nothing(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _model("*SET_NODE_LIST_GENERATE\n         3\n         3         5\n"))
    with pytest.raises(FieldError, match="already in use"):
        renumber(deck, "node", {1: 2})
    with pytest.raises(FieldError, match="not defined"):
        renumber(deck, "node", {99: 100})
    with pytest.raises(FieldError, match="range 3-5"):
        renumber(deck, "node", {4: 104})
    assert deck.changes == []
    (tmp_path / "p").mkdir()
    deck = _deck(tmp_path / "p", "*PARAMETER\nI        n         1\n" + _model().replace(
        "*BOUNDARY_SPC_NODE\n         1", "*BOUNDARY_SPC_NODE\n        &n"))
    with pytest.raises(FieldError, match="parameter expression"):
        renumber(deck, "node", {1: 101})
    assert deck.changes == []


def test_renumber_range_is_consecutive(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _model())
    assert renumber_range(deck, "node", 9, 16, 1000)["renumbered"] == 8
    assert sorted(nodes(deck)[0].tolist())[-8:] == list(range(1000, 1008))


def test_merge_duplicate_nodes(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _model())
    result = merge_duplicate_nodes(deck, 1e-6)
    assert result["merged"] == 4 and result["groups"] == 4 and result["collapsed_elements"] == 0
    assert nodes(deck)[0].size == 12
    assert elements(deck, "*ELEMENT_SOLID", 8)[2][1].tolist() == [2, 10, 11, 3, 6, 14, 15, 7]
    assert deck.members(deck.blocks("*SET_NODE_LIST")[0]) == [1, 2, 2]
    assert check_quality(deck)["ok"] and deck.references().dangling_count == 0


def test_delete_elements_and_orphans(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _model())
    assert delete_elements(deck, "*ELEMENT_SOLID", [2], delete_orphan_nodes=True) == {
        "deleted": 1, "orphan_nodes_deleted": 7}  # node 9 stays: a set and the history refer to it
    assert sorted(nodes(deck)[0].tolist()) == list(range(1, 10))
    assert deck.references().dangling_count == 0
    (tmp_path / "s").mkdir()
    deck = _deck(tmp_path / "s", _model("*SET_SOLID\n         3\n         2\n"))
    with pytest.raises(FieldError, match="references to the elements remain"):
        delete_elements(deck, "*ELEMENT_SOLID", [2])
    assert deck.changes == []


def test_line_numbers_follow_removed_lines_and_inserted_blocks(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _model())
    later = deck.blocks("*SET_NODE_LIST")[0]
    start = later.line_number
    delete_elements(deck, "*ELEMENT_SOLID", [1])
    assert later.line_number == start - 1
    deck.insert("*SET_PART_LIST\n         7\n         1\n", before=deck.blocks("*NODE")[0])
    assert later.line_number == start + 2
    text = deck.main.text().splitlines()
    assert text[later.line_number - 1] == "*SET_NODE_LIST"


def test_renumber_refuses_when_a_node_referencing_block_is_unreadable(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _model("*CONSTRAINED_JOINT_REVOLUTE_FAILURE\n         1         2         3         4\n"))
    with pytest.raises(FieldError, match="CONSTRAINED_JOINT_REVOLUTE_FAILURE x1 cannot be read"):
        renumber(deck, "node", {1: 101})
    assert deck.changes == []


def test_renumber_rewrites_plain_spotweld_nodes(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _model("*CONSTRAINED_SPOTWELD\n         1         2       0.0       0.0       0.0       0.0\n"))
    renumber(deck, "node", {1: 101})
    block = deck.blocks("*CONSTRAINED_SPOTWELD")[0]
    assert deck.get(block, "n1").value == 101 and deck.get(block, "n2").value == 2


def test_line_numbers_after_a_middle_block_grows(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _model())
    first, sets, later = deck.blocks("*PART")[0], deck.blocks("*SET_NODE_LIST")[0], deck.blocks("*SET_PART_LIST")[0]
    before = (first.line_number, sets.line_number, later.line_number)
    deck.set_members(sets, list(range(1, 17)))  # 3 members on one line -> 16 members on two lines
    assert (first.line_number, sets.line_number, later.line_number) == (before[0], before[1], before[2] + 1)
    assert deck.main.text().splitlines()[later.line_number - 1] == "*SET_PART_LIST"


def test_type_coded_initial_velocity_follows_part_renumbering(tmp_path: Path) -> None:
    """Found by the edit-then-solve regression: STYP=2 makes ID a part ID (LS-DYNA error 11085 when missed)."""
    deck = _deck(tmp_path, _model("*INITIAL_VELOCITY_GENERATION\n         1         2       0.0       0.0       0.0"
                                  "     -10.0\n       0.0       0.0       0.0       0.0       0.0       0.0\n"))
    assert deck.references().referenced["part"] == {1}
    renumber(deck, "part", {1: 5})
    block = deck.blocks("*INITIAL_VELOCITY_GENERATION")[0]
    assert deck.get(block, "id").value == 5 and deck.references().dangling_count == 0


def test_renumber_refuses_unruled_id_like_fields(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _model("*ALE_REFERENCE_SYSTEM_GROUP\n         1         1\n"))
    with pytest.raises(FieldError, match="sid=1 may be a part ID"):
        renumber(deck, "part", {1: 5})
    assert deck.changes == []


def test_lagrange_in_solid_part_references(tmp_path: Path) -> None:
    """Plain *CONSTRAINED_LAGRANGE_IN_SOLID (no COUPID card) with SSTYP/MSTYP = 1 (parts)."""
    deck = _deck(tmp_path, _model("*CONSTRAINED_LAGRANGE_IN_SOLID\n         1         1         1         1\n"))
    renumber(deck, "part", {1: 5})
    block = deck.blocks("*CONSTRAINED_LAGRANGE_IN_SOLID")[0]
    assert deck.get(block, "lstrsid").value == 5 and deck.get(block, "alesid").value == 5
    assert deck.references().dangling_count == 0


def test_load_segment_curve_and_nodes_follow_renumbering(tmp_path: Path) -> None:
    text = _model("*LOAD_SEGMENT\n         7       1.0                   1         2         3         4\n"
                  "*DEFINE_CURVE\n         7\n                 0.0                 0.0\n                 1.0                 1.0\n")
    deck = _deck(tmp_path, text)
    renumber(deck, "curve", {7: 70})
    renumber(deck, "node", {1: 101})
    block = deck.blocks("*LOAD_SEGMENT")[0]
    assert deck.get(block, "lcid", row=1).value == 70 and deck.get(block, "n1", row=1).value == 101
    assert deck.references().dangling_count == 0
