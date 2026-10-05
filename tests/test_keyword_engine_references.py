"""Keyword engine: ID definitions, dangling references and guarded deletion."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck, ReferencedError

pytest.importorskip("ansys.dyna.core")

DECK = ("*KEYWORD\n"
        "*PART\n"
        "plate\n"
        "         1         1         1\n"
        "target\n"
        "         2         1         2\n"
        "*SECTION_SHELL\n"
        "         1        16\n"
        "       2.0       2.0       2.0       2.0\n"
        "*MAT_ELASTIC\n"
        "         1      7.85  210000.0       0.3\n"
        "*MAT_ELASTIC\n"
        "         2      2.70   70000.0      0.33\n"
        "*NODE\n"
        "       1             0.0             0.0             0.0\n"
        "       2            10.0             0.0             0.0\n"
        "       3            10.0            10.0             0.0\n"
        "       4             0.0            10.0             0.0\n"
        "*ELEMENT_SHELL\n"
        "       1       1       1       2       3       4\n"
        "*SET_NODE_LIST\n"
        "         7\n"
        "         1         2\n"
        "*BOUNDARY_SPC_SET\n"
        "         7         0         1         1         1\n"
        "*END\n")


def _deck(tmp_path: Path, text: str = DECK) -> KeywordDeck:
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    return KeywordDeck.load(tmp_path / "main.k")


def test_clean_deck_has_no_dangling_references(tmp_path: Path) -> None:
    report = _deck(tmp_path).references()
    assert report.dangling() == [] and report.duplicates() == []
    assert report.summary()["defined"] == {"part": 2, "section": 1, "material": 2, "node": 4, "shell": 1,
                                           "node_set": 1}
    assert report.unused()["material"] == []


def test_dangling_material_is_reported_with_location(tmp_path: Path) -> None:
    deck = _deck(tmp_path)
    (block, row), = deck.find("*PART", pid=2)
    deck.set(block, "mid", 9, row=row)
    (problem,) = deck.references().dangling()
    assert (problem["kind"], problem["id"], problem["field"], problem["row"]) == ("material", 9, "mid", 2)
    assert problem["line"] == 6


def test_delete_referenced_material_is_refused(tmp_path: Path) -> None:
    deck = _deck(tmp_path)
    (material, _), = deck.find("*MAT_ELASTIC", mid=2)
    with pytest.raises(ReferencedError, match="material 2 used by \\*PART.mid"):
        deck.delete(material)
    deck.delete(material, force=True)
    assert [d["id"] for d in deck.references().dangling()] == [2]


def test_delete_allowed_when_another_definition_remains(tmp_path: Path) -> None:
    deck = _deck(tmp_path, DECK.replace("*END\n", "*MAT_ELASTIC\n         2      2.70   70000.0      0.33\n*END\n"))
    first, _ = deck.find("*MAT_ELASTIC", mid=2)[0]
    assert len(deck.references().duplicates()) == 1
    deck.delete(first)
    assert deck.references().dangling() == []


def test_delete_referenced_node_set_and_unreferenced_block(tmp_path: Path) -> None:
    deck = _deck(tmp_path)
    with pytest.raises(ReferencedError):
        deck.delete(deck.blocks("*SET_NODE_LIST")[0])
    deck.delete(deck.blocks("*BOUNDARY_SPC_SET")[0])
    deck.delete(deck.blocks("*SET_NODE_LIST")[0])


def test_contact_surface_types_and_set_members(tmp_path: Path) -> None:
    extra = ("*CONTACT_AUTOMATIC_SURFACE_TO_SURFACE\n"
             "         1         5         3         2\n"
             "       0.1\n"
             "\n"
             "*SET_NODE_LIST\n"
             "         8\n"
             "         1        99\n")
    deck = _deck(tmp_path, DECK.replace("*END\n", extra + "*END\n"))
    found = {(d["kind"], d["id"]) for d in deck.references().dangling()}
    assert found == {("part_set", 5), ("node", 99)}


def test_mesh_can_be_skipped_for_speed(tmp_path: Path) -> None:
    report = _deck(tmp_path).references(include_mesh=False)
    assert "node" not in report.summary()["defined"] and report.summary()["defined"]["part"] == 2
