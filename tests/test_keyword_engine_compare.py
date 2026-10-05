"""Semantic deck comparison: formatting is ignored, entity changes are reported by ID."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model.compare import compare_decks

pytest.importorskip("ansys.dyna.core")

BASE = ("*KEYWORD\n"
        "*PART\n"
        "plate\n"
        "         1         1         1\n"
        "*SECTION_SHELL\n"
        "         1        16\n"
        "       2.0       2.0       2.0       2.0\n"
        "*MAT_ELASTIC\n"
        "         1      7.85  210000.0       0.3\n"
        "*CONTROL_TERMINATION\n"
        "     0.001\n"
        "*NODE\n"
        "       1             0.0             0.0             0.0\n"
        "       2            10.0             0.0             0.0\n"
        "*ELEMENT_SHELL\n"
        "       1       1       1       2       2       1\n"
        "*END\n")


def _write(folder: Path, name: str, text: str) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(text.encode("ascii"))
    return str(folder / name)


def test_reformatted_deck_is_identical(tmp_path: Path) -> None:
    a = _write(tmp_path / "a", "main.k", BASE)
    reformatted = (BASE.replace("         1      7.85  210000.0       0.3\n", "1,7.85,2.1e5,0.3\n")
                   .replace("     0.001\n", "1.0e-3\n").replace("*NODE\n", "$ comment\n*NODE\n"))
    b = _write(tmp_path / "b", "main.k", reformatted)
    result = compare_decks(a, b)
    assert result["identical"], result


def test_split_into_include_is_identical(tmp_path: Path) -> None:
    a = _write(tmp_path / "a", "main.k", BASE)
    material = "*MAT_ELASTIC\n         1      7.85  210000.0       0.3\n"
    _write(tmp_path / "b", "mat.k", material)
    b = _write(tmp_path / "b", "main.k", BASE.replace(material, "*INCLUDE\nmat.k\n"))
    assert compare_decks(a, b)["identical"]


def test_changes_are_reported_by_entity(tmp_path: Path) -> None:
    a = _write(tmp_path / "a", "main.k", BASE)
    changed = (BASE.replace("  210000.0       0.3", "   70000.0       0.3")
               .replace("       2            10.0", "       2            10.5")
               .replace("     0.001\n", "     0.002\n")
               .replace("*END\n", "*MAT_ELASTIC\n         2      2.70   70000.0      0.33\n*END\n"))
    b = _write(tmp_path / "b", "main.k", changed)
    result = compare_decks(a, b)
    assert not result["identical"]
    material = result["entities"]["material"]
    assert material["added"] == [2] and material["changed"][0]["fields"]["e"] == {"a": 210000.0, "b": 70000.0}
    node = result["entities"]["node"]
    assert node["changed_count"] == 1 and node["max_displacement"] == pytest.approx(0.5)
    assert result["keywords"]["*CONTROL_TERMINATION"]["changed"][0]["fields"]["endtim"]["b"] == 0.002


def test_coordinate_tolerance(tmp_path: Path) -> None:
    a = _write(tmp_path / "a", "main.k", BASE)
    b = _write(tmp_path / "b", "main.k", BASE.replace("       2            10.0", "       2      10.0000001"))
    assert not compare_decks(a, b)["identical"]
    assert compare_decks(a, b, coordinate_tol=1e-5)["identical"]
