"""Keyword-level mesh editing (P08): transforms, mirroring with re-orientation, shell normals."""
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.domain.model import FieldError, KeywordDeck
from ls_prepost_mcp.domain.model.geometry import elements, nodes
from ls_prepost_mcp.domain.model.mesh import (
    flipped,
    reflect_nodes,
    reverse_elements,
    rotate_nodes,
    translate_nodes,
    unify_shell_normals,
)
from ls_prepost_mcp.domain.model.quality import check_quality

pytest.importorskip("ansys.dyna.core")

CUBE = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]


def _node(nid: int, x: float, y: float, z: float) -> str:
    return f"{nid:>8}{x:>16}{y:>16}{z:>16}\n"


def _deck(tmp_path: Path, text: str) -> KeywordDeck:
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    return KeywordDeck.load(tmp_path / "main.k")


def _cube_text() -> str:
    text = "*NODE\n" + "".join(_node(i + 1, *map(float, p)) for i, p in enumerate(CUBE))
    return text + "*ELEMENT_SOLID\n" + f"{1:>8}{1:>8}" + "".join(f"{n:>8}" for n in range(1, 9)) + "\n"


def _coords(deck: KeywordDeck) -> dict[int, tuple[float, ...]]:
    ids, xyz = nodes(deck)
    return {int(i): tuple(p) for i, p in zip(ids, xyz)}


def test_translate_changes_only_selected_rows(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _cube_text())
    before = list(deck.blocks("*NODE")[0].lines)
    result = translate_nodes(deck, [1, 2], (10.0, 0.0, -2.5))
    assert result == {"nodes": 2, "max_rounding": 0.0}
    after = deck.blocks("*NODE")[0].lines
    assert [i for i, (a, b) in enumerate(zip(before, after)) if a != b] == [1, 2]
    assert _coords(deck)[2] == (11.0, 0.0, -2.5) and _coords(deck)[3] == (1.0, 1.0, 0.0)


def test_rotate_about_center_and_rounding_report(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _cube_text())
    rotate_nodes(deck, [2], axis=(0, 0, 1), angle_deg=90.0, center=(0.5, 0.5, 0.0))
    assert np.allclose(_coords(deck)[2], (1.0, 1.0, 0.0), atol=1e-12)
    result = translate_nodes(deck, [3], (1 / 3, 0.0, 0.0))
    assert 0 < result["max_rounding"] < 1e-10


def test_reflect_reorders_fully_mirrored_solids(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _cube_text())
    result = reflect_nodes(deck, range(1, 9), normal=(1, 0, 0), point=(0, 0, 0))
    assert result["reoriented"]["*ELEMENT_SOLID"] == 1 and result["partially_mirrored_elements"] == 0
    assert _coords(deck)[2] == (-1.0, 0.0, 0.0)
    report = check_quality(deck)
    assert report["ok"] and report["solids"]["hexahedra"]["min_scaled_jacobian"]["min"] == pytest.approx(1.0)
    (tmp_path / "raw").mkdir()
    raw = _deck(tmp_path / "raw", _cube_text())
    reflect_nodes(raw, range(1, 9), normal=(1, 0, 0), fix_orientation=False)
    assert not check_quality(raw)["ok"]


def test_refusals_leave_the_deck_unchanged(tmp_path: Path) -> None:
    text = "*PARAMETER\nR        a       2.0\n" + _cube_text().replace(_node(1, 0.0, 0.0, 0.0), f"{1:>8}{'&a':>16}{0.0:>16}{0.0:>16}\n")
    deck = _deck(tmp_path, text)
    with pytest.raises(FieldError, match="parameter"):
        translate_nodes(deck, [1, 2], (1.0, 0.0, 0.0))
    with pytest.raises(FieldError, match="not found"):
        translate_nodes(deck, [2, 99], (1.0, 0.0, 0.0))
    assert deck.changes == [] and _coords(deck)[2] == (1.0, 0.0, 0.0)


def test_flip_rules_keep_degenerate_patterns() -> None:
    solid = np.array([[1, 2, 3, 4, 5, 6, 7, 8], [1, 2, 3, 4, 4, 4, 4, 4], [1, 2, 3, 4, 5, 5, 6, 6]])
    assert flipped(solid, True).tolist() == [[2, 1, 4, 3, 6, 5, 8, 7], [2, 1, 3, 4, 4, 4, 4, 4], [2, 1, 4, 3, 5, 5, 6, 6]]
    shell = np.array([[1, 2, 3, 4], [1, 2, 3, 3], [1, 2, 3, 0]])
    assert flipped(shell, False).tolist() == [[2, 1, 4, 3], [2, 1, 3, 3], [2, 1, 3, 0]]


def _strip(second: tuple[int, ...]) -> str:
    nodes_text = "".join(_node(i + 1, float(i % 3), float(i // 3), 0.0) for i in range(6))
    return ("*NODE\n" + nodes_text + "*ELEMENT_SHELL\n" + f"{1:>8}{1:>8}{1:>8}{2:>8}{5:>8}{4:>8}\n"
            + f"{2:>8}{1:>8}" + "".join(f"{n:>8}" for n in second) + "\n")


def test_reverse_and_unify_shell_normals(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _strip((2, 3, 6, 5)))
    assert reverse_elements(deck, "*ELEMENT_SHELL", [2]) == {"elements": 1}
    assert elements(deck, "*ELEMENT_SHELL", 4)[2].tolist()[1] == [3, 2, 5, 6]
    result = unify_shell_normals(deck)
    assert result["reversed"] == 1 and result["patches"] == 1 and result["orientation_conflicts"] == 0
    assert elements(deck, "*ELEMENT_SHELL", 4)[2].tolist()[1] == [2, 3, 6, 5]
    result = unify_shell_normals(deck, direction=(0, 0, -1))
    assert result["reversed"] == 2
    assert check_quality(deck)["ok"]


def test_mesh_edits_survive_save_and_reload(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _cube_text())
    reflect_nodes(deck, range(1, 9), normal=(0, 0, 1), point=(0, 0, 2))
    deck.save_as(tmp_path / "out")
    again = KeywordDeck.load(tmp_path / "out" / "main.k")
    assert _coords(again)[5] == (0.0, 0.0, 3.0) and check_quality(again)["ok"]
