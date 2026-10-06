"""*SET_* variants with a repeated data card (GENERAL / COLUMN / GENERATE_INCREMENT) and the COLLECT option."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck, Unsupported

ROWS = (
    "*KEYWORD\n"
    "*SET_NODE_GENERAL\n"
    "         7       0.0       0.0       0.0       0.0MECH\n"
    "PART             6\n"
    "DBOX             7\n"
    "ALL\n"
    "*SET_NODE_COLUMN_TITLE\n"
    "column set\n"
    "         4       1.0       2.0       3.0       4.0\n"
    "       301       5.0       6.0       7.0       8.0\n"
    "       302\n"
    "*SET_SHELL_LIST_GENERATE_INCREMENT\n"
    "        16\n"
    "        10       200        10\n"
    "       300       400         5\n"
    "*SET_SOLID_GENERAL\n"
    "        25,MECH\n"
    "PART,6\n"
    "SET,23\n"
    "*END\n"
)
COLLECT = (
    "*KEYWORD\n"
    "*SET_NODE_LIST_COLLECT\n"
    "        20\n"
    "         1         2\n"
    "*SET_NODE_LIST_COLLECT\n"
    "        20\n"
    "         3\n"
    "*SET_NODE_LIST\n"
    "        30\n"
    "         4\n"
    "*SET_NODE_LIST\n"
    "        30\n"
    "         5\n"
    "*NODE\n"
    "       1             0.0             0.0             0.0\n"
    "       2             1.0             0.0             0.0\n"
    "       3             0.0             1.0             0.0\n"
    "       4             0.0             0.0             1.0\n"
    "       5             1.0             1.0             0.0\n"
    "*END\n"
)


def _deck(tmp_path: Path, text: str) -> KeywordDeck:
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    return KeywordDeck.load(tmp_path / "main.k")


def _changed(deck: KeywordDeck) -> list[str]:
    return [line for line in deck.diff().splitlines() if line[:1] in "+-" and line[:3] not in ("+++", "---")]


def test_general_rows_are_named_fields_and_edit_in_place(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, ROWS)
    block = deck.blocks("*SET_NODE_GENERAL")[0]
    layout = deck.layout(block)
    assert (layout.key, list(layout.rows)) == ("row", [1, 2, 3])
    assert (deck.get(block, "sid").value, deck.get(block, "solver").value) == (7, "MECH")
    assert [deck.get(block, "option", row=r).value for r in (1, 2, 3)] == ["PART", "DBOX", "ALL"]
    assert deck.get(block, "e1", row=2).value == 7
    deck.set(block, "e1", 9, row=2)
    assert _changed(deck) == ["-DBOX             7", "+DBOX             9"]


def test_column_rows_keep_blank_attributes_blank(tmp_path: Path) -> None:
    # LS-DYNA gives a blank A1-A4 the header's DA1-DA4; the engine reports the text as written.
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, ROWS)
    block = deck.blocks("*SET_NODE_COLUMN_TITLE")[0]
    assert deck.get(block, "title").value == "column set" and deck.get(block, "da4").value == 4.0
    assert [deck.get(block, "nid", row=r).value for r in (1, 2)] == [301, 302]
    assert deck.get(block, "a3", row=1).value == 7.0 and deck.get(block, "a3", row=2).raw.strip() == ""


def test_generate_increment_and_comma_rows(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, ROWS)
    block = deck.blocks("*SET_SHELL_LIST_GENERATE_INCREMENT")[0]
    assert [tuple(deck.get(block, f, row=r).value for f in ("bbeg", "bend", "incr")) for r in (1, 2)] == [
        (10, 200, 10), (300, 400, 5)]
    solid = deck.blocks("*SET_SOLID_GENERAL")[0]
    assert deck.get(solid, "sid").value == 25 and deck.get(solid, "solver").value == "MECH"
    assert [(deck.get(solid, "option", row=r).value, deck.get(solid, "e1", row=r).value) for r in (1, 2)] == [
        ("PART", 6), ("SET", 23)]
    deck.set(solid, "e1", 24, row=2)
    assert _changed(deck) == ["-SET,23", "+SET,24"]


def test_placeholder_rows_are_refused(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, "*SET_NODE_GENERAL\n         1\nPART             ?\n")
    with pytest.raises(Unsupported):
        deck.layout(deck.blocks("*SET_NODE_GENERAL")[0])


def test_collect_sets_are_lists_and_one_merged_definition(tmp_path: Path) -> None:
    deck = _deck(tmp_path, COLLECT)
    first, second = deck.blocks("*SET_NODE_LIST_COLLECT")
    assert (deck.members(first), deck.members(second)) == ([1, 2], [3])
    duplicates = deck.references().duplicates()
    assert [(d["kind"], d["id"]) for d in duplicates] == [("node_set", 30)]  # plain sets still collide


def test_references_of_row_sets(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    text = ROWS.replace("*END\n", "*BOUNDARY_SPC_SET\n         7         0         1         1         1\n*END\n")
    report = _deck(tmp_path, text).references()
    # The GENERAL SID is a definition, so the SPC set reference is neither dangling nor unverified.
    assert 7 in report.defined["node_set"] and report.unverified() == []
    # COLUMN rows name real nodes (none defined here); GENERATE_INCREMENT range ends are not references.
    assert [(d["kind"], d["id"]) for d in report.dangling()] == [("node", 301), ("node", 302)]
    # GENERAL row IDs depend on OPTION and stay unchecked rather than look clean.
    assert {"*SET_NODE_GENERAL", "*SET_SOLID_GENERAL"} <= set(report.unchecked)


def test_joint_checks_do_not_follow_a_set_spread_over_collect_blocks(tmp_path: Path) -> None:
    from ls_prepost_mcp.domain.model import joint_checks

    deck = _deck(tmp_path, COLLECT)
    unread: list[str] = []
    found = joint_checks.node_set_blocks(deck, unread)
    assert 20 not in found and any("20: defined by several blocks" in u for u in unread)


MESH = (
    "*KEYWORD\n"
    "*NODE\n"
    "       1             0.0             0.0             0.0\n"
    "       2             1.0             0.0             0.0\n"
    "       3             1.0             1.0             0.0\n"
    "       4             0.0             1.0             0.0\n"
    "*PART\n"
    "plate\n"
    "         1         1         1\n"
    "*SECTION_SHELL\n"
    "         1\n"
    "       1.0       1.0       1.0       1.0\n"
    "*MAT_ELASTIC\n"
    "         1   7.85e-9  210000.0       0.3\n"
    "*ELEMENT_SHELL\n"
    + "".join(f"{eid:>8}       1       1       2       3       4\n" for eid in (10, 20, 30, 40, 50, 75))
    + "*SET_SHELL_LIST_GENERATE_INCREMENT\n"
    "         5\n"
    "        10        70        10\n"
    "*END\n"
)


def test_renumber_refuses_ids_inside_increment_ranges(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    from ls_prepost_mcp.domain.model.fields import FieldError
    from ls_prepost_mcp.domain.model.renumber import renumber

    deck = _deck(tmp_path, MESH)  # members 10, 20, ..., 70; shells 10-50 exist, 75 is outside
    with pytest.raises(FieldError, match="range 10-70 step 10"):
        renumber(deck, "shell", {20: 1000})  # would silently leave the set
    with pytest.raises(FieldError, match="range 10-70 step 10"):
        renumber(deck, "shell", {75: 60})  # a new ID on the step would join it
    assert renumber(deck, "shell", {75: 65})["cells_changed"] >= 1  # between steps: not a member


def test_general_rows_only_block_renumbering_of_kinds_they_can_name(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    from ls_prepost_mcp.domain.model.fields import FieldError
    from ls_prepost_mcp.domain.model.renumber import renumber

    text = MESH.replace("*END\n", "*SET_NODE_GENERAL\n         7\nPART             1\n*END\n")
    deck = _deck(tmp_path, text)
    assert renumber(deck, "material", {1: 5})["cells_changed"] == 2  # *MAT_ELASTIC and *PART
    with pytest.raises(FieldError, match="OPTION-dependent"):
        renumber(deck, "part", {1: 7})


def test_contact_set_members_merge_collect_blocks(tmp_path: Path) -> None:
    from ls_prepost_mcp.domain.model.contact import _set_members
    from ls_prepost_mcp.domain.model.fields import FieldError

    deck = _deck(tmp_path, COLLECT)
    assert _set_members(deck, "*SET_NODE", 20) == [1, 2, 3]
    with pytest.raises(FieldError, match="not all _COLLECT"):
        _set_members(deck, "*SET_NODE", 30)


@pytest.mark.parametrize("text", [
    "*SET_NODE_COLUMN +\n         7\n       301       1.5\n       302       2.5\n",  # PyDYNA reads long format
    "*SET_NODE_GENERAL\n         1\nPART             6\n\nALL\n",  # blank line between rows
    # text beyond the last field (column 60) on row 26, outside the first and last 20 sampled rows
    "*SET_NODE_COLUMN\n         7\n" + "".join(f"{n:>10}       1.0\n" for n in range(1, 26))
    + "        26       1.0" + " " * 40 + "junk\n" + "".join(f"{n:>10}       1.0\n" for n in range(27, 51)),
])
def test_uncertain_row_sets_are_refused(tmp_path: Path, text: str) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, text)
    with pytest.raises(Unsupported):
        deck.layout(deck.blocks()[0])


def test_compare_merges_collect_members(tmp_path: Path) -> None:
    from ls_prepost_mcp.domain.model.compare import compare_decks

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "main.k").write_bytes(COLLECT.encode("ascii"))
    (tmp_path / "b" / "main.k").write_bytes(COLLECT.replace("         1         2\n", "         1         4\n", 1).encode("ascii"))
    result = compare_decks(str(tmp_path / "a" / "main.k"), str(tmp_path / "b" / "main.k"), include_mesh=False)
    changed = result["entities"]["node_set"]["changed"]
    assert not result["identical"] and changed == [{"id": 20, "fields": {"members": {"a": (1, 2, 3), "b": (1, 3, 4)}}}]


def test_generate_ranges_check_new_ids_but_merging_keeps_existing_nodes(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    from ls_prepost_mcp.domain.model.fields import FieldError
    from ls_prepost_mcp.domain.model.renumber import merge_duplicate_nodes, renumber

    nodes = "".join(f"{n:>8}{x:>16}{0.0:>16}{0.0:>16}\n" for n, x in ((1, 0.0), (2, 1.0), (3, 2.0), (4, 3.0),
                                                                    (7, 1.0), (80, 9.0)))
    text = "*KEYWORD\n*NODE\n" + nodes + "*SET_NODE_LIST_GENERATE\n         5\n         1        10\n*END\n"
    with pytest.raises(FieldError, match="range 1-10"):
        renumber(_deck(tmp_path, text), "node", {80: 9})  # node 9 would join the set
    assert renumber(_deck(tmp_path, text), "node", {80: 20})["cells_changed"] >= 1
    # node 7 coincides with node 2 inside the range: node 2 stays, so the members do not change
    narrow = text.replace("         1        10\n", "         1         4\n")
    result = merge_duplicate_nodes(_deck(tmp_path, narrow), 1e-6)
    assert result["merged"] == 1


def test_keyword_docs_and_joint_errors_follow_the_set_variants(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    from ls_prepost_mcp.domain.model import joints
    from ls_prepost_mcp.domain.model.fields import FieldError
    from ls_prepost_mcp.domain.model.keyword_docs import keyword_doc

    assert keyword_doc("*SET_SHELL_LIST_GENERATE_INCREMENT")["references"] == []  # range ends
    assert keyword_doc("*SET_NODE_COLUMN")["references"] == [{"field": "nid", "refers_to": "node"}]
    cnrb = "*CONSTRAINED_NODAL_RIGID_BODY\n       100         0        20\n*END\n"
    deck = _deck(tmp_path, COLLECT.replace("*END\n", cnrb))
    with pytest.raises(FieldError, match="not one readable member list"):
        joints._attach(deck, ("cnrb", 100, []), [5], None, "joint")


def test_compare_keeps_the_header_of_every_collect_block(tmp_path: Path) -> None:
    from ls_prepost_mcp.domain.model.compare import compare_decks

    second = "*SET_NODE_LIST_COLLECT\n        20\n         3\n"
    plain = COLLECT.replace("*SET_NODE_LIST_COLLECT\n        20\n         1", "*SET_NODE_LIST\n        20\n         1", 1)
    variants = {"a": COLLECT, "b": COLLECT.replace(second, second.replace("        20\n", "        20       5.0\n")),
                "c": plain}
    for name, text in variants.items():
        (tmp_path / name).mkdir()
        (tmp_path / name / "main.k").write_bytes(text.encode("ascii"))
    path = {name: str(tmp_path / name / "main.k") for name in variants}
    assert compare_decks(path["a"], path["a"], include_mesh=False)["identical"]
    assert not compare_decks(path["a"], path["b"], include_mesh=False)["identical"]  # DA1 of the second block
    assert not compare_decks(path["a"], path["c"], include_mesh=False)["identical"]  # plain + COLLECT: duplicate
