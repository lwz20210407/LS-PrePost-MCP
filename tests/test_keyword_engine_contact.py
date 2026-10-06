"""Keyword-level initial penetration check (P06)."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.domain.model.contact import check_penetration

pytest.importorskip("ansys.dyna.core")


def _box(first_node: int, eid: int, pid: int, low: tuple[float, ...], high: tuple[float, ...]) -> tuple[str, str]:
    (x0, y0, z0), (x1, y1, z1) = low, high
    corners = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    node_text = "".join(f"{first_node + i:>8}{x:>16}{y:>16}{z:>16}\n" for i, (x, y, z) in enumerate(corners))
    element = f"{eid:>8}{pid:>8}" + "".join(f"{first_node + i:>8}" for i in range(8)) + "\n"
    return node_text, element


def _deck(tmp_path: Path, shift: float, plate_z: float | None = None) -> KeywordDeck:
    a_nodes, a_el = _box(1, 1, 1, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    b_nodes, b_el = _box(101, 2, 2, (shift, 0.25, 0.25), (shift + 1.0, 0.75, 0.75))
    text = ("*PART\nA\n         1         1         1\n*PART\nB\n         2         1         1\n"
            "*SECTION_SOLID\n         1         1\n*MAT_ELASTIC\n         1    7.8e-9  210000.0       0.3\n"
            "*NODE\n" + a_nodes + b_nodes + "*ELEMENT_SOLID\n" + a_el + b_el)
    if plate_z is not None:
        plate = "".join(f"{201 + i:>8}{x:>16}{y:>16}{plate_z:>16}\n"
                        for i, (x, y) in enumerate([(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]))
        text += ("*PART\nplate\n         3         2         1\n*SECTION_SHELL\n         2         2\n"
                 "       1.0       1.0       1.0       1.0\n*NODE\n" + plate
                 + "*ELEMENT_SHELL\n       3       3     201     202     203     204\n")
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    return KeywordDeck.load(tmp_path / "main.k")


def test_overlapping_solids_report_depth(tmp_path: Path) -> None:
    result = check_penetration(_deck(tmp_path, 0.9), {"parts": [2]}, {"parts": [1]})
    assert result["penetrating"] == 4 and result["max_depth"] == pytest.approx(0.1)
    assert {n["node"] for n in result["nodes"]} == {101, 104, 105, 108}


def test_gap_reports_nothing(tmp_path: Path) -> None:
    result = check_penetration(_deck(tmp_path, 1.1), {"parts": [2]}, {"parts": [1]})
    assert result["penetrating"] == 0 and result["master_faces"] == 6


def test_shell_thickness_offset(tmp_path: Path) -> None:
    deck = _deck(tmp_path, 1.1, plate_z=1.2)
    result = check_penetration(deck, {"parts": [3]}, {"parts": [1]})
    assert result["penetrating"] == 4 and result["max_depth"] == pytest.approx(0.3)
    assert check_penetration(deck, {"parts": [3]}, {"parts": [1]}, tolerance=0.35)["penetrating"] == 0


def test_contact_blocks_are_checked(tmp_path: Path) -> None:
    from ls_prepost_mcp.domain.model.operations import check_contacts
    deck = _deck(tmp_path, 0.9)
    deck.insert("*CONTACT_AUTOMATIC_SURFACE_TO_SURFACE\n         2         1         3         3\n\n\n"
                "*CONTACT_AUTOMATIC_SINGLE_SURFACE\n         0         0         5\n\n\n")
    deck.save_as(tmp_path / "out")
    result = check_contacts(str(tmp_path / "out" / "main.k"))
    first, second = result["contacts"]
    assert first["checked"] and first["penetrating"] == 4 and first["max_depth"] == pytest.approx(0.1)
    assert not second["checked"] and "not supported" in second["reason"]
    assert result["penetrating_contacts"] == 1 and result["not_checked"] == 1


def test_single_surface_contact_part_set_is_a_reference(tmp_path: Path) -> None:
    """*CONTACT_AUTOMATIC_SINGLE_SURFACE names its fields SSID/SSTYP in PyDYNA."""
    from ls_prepost_mcp.domain.model.renumber import renumber
    deck = _deck(tmp_path, 1.1)
    deck.insert("*SET_PART_LIST\n         9\n         1         2\n"
                "*CONTACT_AUTOMATIC_SINGLE_SURFACE\n         9         0         2\n\n\n")
    assert deck.references().dangling_count == 0
    renumber(deck, "part_set", {9: 19})
    block = deck.blocks("*CONTACT_AUTOMATIC_SINGLE_SURFACE")[0]
    assert deck.get(block, "ssid").value == 19 and deck.references().dangling_count == 0
