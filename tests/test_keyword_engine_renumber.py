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


def test_contact_title_form_and_coded_groups(tmp_path: Path) -> None:
    text = _model("*CONTACT_AUTOMATIC_SURFACE_TO_SURFACE_TITLE\n        77impact\n"
                  "         1         1         3         3\n\n\n"
                  "*ALE_MULTI-MATERIAL_GROUP\n         1         1\n         2         0\n"
                  "*DATABASE_CROSS_SECTION_SET\n         1         0         0         0         0         0         1\n")
    deck = _deck(tmp_path, text)
    contact = deck.blocks("*CONTACT_AUTOMATIC_SURFACE_TO_SURFACE_TITLE")[0]
    assert deck.get(contact, "cid").value == 77 and deck.get(contact, "surfa").value == 1
    assert deck.references().dangling_count == 0
    renumber(deck, "part", {1: 5})
    group = deck.blocks("*ALE_MULTI-MATERIAL_GROUP")[0]
    section = deck.blocks("*DATABASE_CROSS_SECTION_SET")[0]
    assert deck.get(contact, "surfa").value == 5 and deck.get(contact, "cid").value == 77
    assert deck.get(group, "sid", row=1).value == 5 and deck.get(group, "sid", row=2).value == 2
    assert deck.get(section, "id").value == 5


# --- found by the 538-deck edit-then-solve regression (LS-DYNA R11 reported undefined IDs) ---

def test_history_node_set_ids_are_node_sets(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _model("*DATABASE_HISTORY_NODE_SET\n         1\n"))
    renumber(deck, "node", {1: 101})
    assert deck.get(deck.blocks("*DATABASE_HISTORY_NODE_SET")[0], "id1").value == 1
    assert deck.references().dangling_count == 0


@pytest.mark.parametrize("extra", [
    "*CONSTRAINED_LINEAR\n         2\n         1         1\n         9         1\n",  # legacy *_LINEAR_GLOBAL
    "*BOUNDARY_PRESCRIBED_MOTION_NODES\n         1         1         0         1       1.0\n",  # legacy plural
])
def test_unknown_keywords_block_renumbering(tmp_path: Path, extra: str) -> None:
    curve = "*DEFINE_CURVE\n         1\n                 0.0                 0.0\n                 1.0                 1.0\n"
    deck = _deck(tmp_path, _model(extra + curve))
    name = extra.split("\n", 1)[0]
    assert deck.references().unchecked[name] == 1
    for kind in ("node", "curve"):  # the R11 failure was curve renumbering (LCID of the plural form)
        with pytest.raises(FieldError, match="cannot be read"):
            renumber(deck, kind, {1: 101})
    assert deck.changes == []


def test_unreadable_block_with_unruled_curve_field_blocks_curve_renumbering(tmp_path: Path) -> None:
    # a third value on the two-field SSID/PSEROD card makes the block unreadable (stray text)
    flux = ("*BOUNDARY_FLUX_SET\n         5         0         3\n"
            "         7       1.0       1.0       1.0       1.0         0         0\n")
    curve = "*DEFINE_CURVE\n         7\n                 0.0                 0.0\n                 1.0                 1.0\n"
    deck = _deck(tmp_path, _model(flux + curve))
    with pytest.raises(FieldError, match="BOUNDARY_FLUX_SET x1 cannot be read"):
        renumber(deck, "curve", {7: 70})
    renumber(deck, "part", {1: 5})  # LCID cannot be a part ID: unaffected


def test_thick_shell_history_is_not_a_shell_reference(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _model("*DATABASE_HISTORY_TSHELL_ID\n         1tshell one\n"
                                  "*DATABASE_HISTORY_SHELL_SET\n         4\n"))
    report = deck.references()
    assert report.referenced["tshell"] == {1} and report.referenced["shell_set"] == {4}


def test_joint_failure_and_local_after_parm_card(tmp_path: Path) -> None:
    """R11 Vol I 10-54..10-58: [ID], card 1, PARM card (GEARS), LOCAL, FAILURE x2 (last one blank)."""
    joint = ("*CONSTRAINED_JOINT_GEARS_ID_LOCAL_FAILURE\n        77gear pair\n"
             "         1         2         3         4         5         6       1.0\n"
             "       2.5         7         0       0.0       0.0\n"
             "         1         0\n"
             "         0       0.5       0.0\n"
             "\n")
    deck = _deck(tmp_path, _model(joint))
    block = deck.blocks("*CONSTRAINED_JOINT_GEARS_ID_LOCAL_FAILURE")[0]
    values = {name: deck.get(block, name).value for name in ("jid", "n6", "parm", "raid", "lst", "tfail", "mzz")}
    assert values == {"jid": 77, "n6": 6, "parm": 2.5, "raid": 1, "lst": 0, "tfail": 0.5, "mzz": None}
    renumber(deck, "part", {1: 5})  # RAID with LST=0 is a rigid body part
    assert deck.get(block, "raid").value == 5 and deck.get(block, "n1").value == 1


def test_free_format_table_rows(tmp_path: Path) -> None:
    """Comma rows of a table keyword (tube.k of the Reid class examples) read, renumber and stay commas."""
    spc = "".join(f"{n:>10},  0,1,1,1, 1, 1, 1\n" for n in (1, 2, 9))
    deck = _deck(tmp_path, _model("*BOUNDARY_SPC_NODE\n" + spc))
    block = deck.blocks("*BOUNDARY_SPC_NODE")[1]
    assert deck.get(block, "dofx", row=9).value == 1
    renumber(deck, "node", {9: 109})
    assert deck.get(block, "nid", row=109).value == 109
    assert block.lines[3].rstrip() == "       109,  0,1,1,1, 1, 1, 1"


def test_counts_and_own_ids_do_not_block_renumbering(tmp_path: Path) -> None:
    extra = ("*CONTROL_SOLUTION\n         0         0         0         7\n"
             "*DEFINE_CURVE\n         7\n                 0.0                 0.0\n                 1.0                 1.0\n")
    deck = _deck(tmp_path, _model(extra))
    renumber(deck, "curve", {7: 70})  # LCINT=7 is a point count, not curve 7
    assert deck.get(deck.blocks("*CONTROL_SOLUTION")[0], "lcint").value == 7


def test_integration_shell_points(tmp_path: Path) -> None:
    rule = ("*INTEGRATION_SHELL\n         1         3         0         0\n"
            "     -0.05       0.5         1\n       0.0       0.3         0\n      0.05       0.2         1\n")
    deck = _deck(tmp_path, _model(rule))
    block = deck.blocks("*INTEGRATION_SHELL")[0]
    assert deck.get(block, "nip").value == 3 and deck.get(block, "wf", row=2).value == 0.3
    renumber(deck, "part", {1: 5})
    assert [deck.get(block, "pid", row=r).value for r in (1, 2, 3)] == [5, 0, 5]
    assert deck.references().dangling_count == 0
    (tmp_path / "x").mkdir()
    two_rules = rule + "         2         1         0         0\n       0.0       1.0         0\n"
    deck = _deck(tmp_path / "x", _model(two_rules))
    with pytest.raises(FieldError, match="cannot be read"):
        renumber(deck, "part", {1: 5})


def test_flux_segments_and_instance_rows(tmp_path: Path) -> None:
    """Refusals of the regression rerun: flux segments, *CONSTRAINED_NODE_SET, *LOAD_SHELL_ELEMENT."""
    flux = ("*BOUNDARY_FLUX_SEGMENT\n         1         2         3         4\n"
            "         7       1.0       1.0       1.0       1.0         0         2\n       5.0       6.0\n"
            "         5         6         7         8\n         7      -1.0      -1.0      -1.0      -1.0\n")
    curve = "*DEFINE_CURVE\n         7\n                 0.0                 0.0\n                 1.0                 1.0\n"
    more = "*CONSTRAINED_NODE_SET\n         1         1\n*SET_NODE_LIST\n         5\n         1         2\n"
    deck = _deck(tmp_path, _model(flux + curve + more))
    block = deck.blocks("*BOUNDARY_FLUX_SEGMENT")[0]
    assert deck.get(block, "hisv2", row=1).value == 6.0 and deck.get(block, "n4", row=2).value == 8
    renumber(deck, "curve", {7: 70})
    renumber(deck, "node", {1: 101})
    assert [deck.get(block, "lcid", row=r).value for r in (1, 2)] == [70, 70]
    assert deck.get(block, "n1", row=1).value == 101
    node_set = deck.blocks("*CONSTRAINED_NODE_SET")[0]
    assert deck.get(node_set, "nsid").value == 1 and deck.references().dangling_count == 0


def test_comma_line_with_parameter_reference(tmp_path: Path) -> None:
    text = ("*PARAMETER\nR tshell       1.5\n" + _model().replace(
        "*SECTION_SOLID\n         1         1\n",
        "*SECTION_SOLID\n         1         1\n*SECTION_SHELL\n2,2,0.000E+00,0.000E+00,0.000E+00,0.000E+00,0\n"
        "&tshell,&tshell,&tshell,&tshell,0.000E+00\n"))
    deck = _deck(tmp_path, text)
    shell = deck.blocks("*SECTION_SHELL")[0]
    assert deck.get(shell, "t1").value == 1.5 and deck.get(shell, "t1").parameter == "tshell"
