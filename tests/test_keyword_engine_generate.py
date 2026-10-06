"""Element generation (P08): linear / polar arrays, shell offsets, refusals."""
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.domain.model import FieldError, KeywordDeck
from ls_prepost_mcp.domain.model.generate import array_elements, offset_shells, shell_nodal_normals
from ls_prepost_mcp.domain.model.geometry import elements, nodes
from ls_prepost_mcp.domain.model.layouts import Unsupported
from ls_prepost_mcp.domain.model.mesh import copy_elements, reverse_elements, rotation_matrix
from ls_prepost_mcp.domain.model.operations import edit_deck

pytest.importorskip("ansys.dyna.core")

CUBE = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]


def _node(nid: int, x: float, y: float, z: float) -> str:
    return f"{nid:>8}{x:>16.10g}{y:>16.10g}{z:>16.10g}\n"


def _shell(eid: int, pid: int, *ns: int) -> str:
    return f"{eid:>8}{pid:>8}" + "".join(f"{n:>8}" for n in ns) + "\n"


def _deck(tmp_path: Path, text: str) -> KeywordDeck:
    (tmp_path / "main.k").write_bytes(("*KEYWORD\n" + text + "*END\n").encode("ascii"))
    return KeywordDeck.load(tmp_path / "main.k")


def _cube() -> str:
    text = "*NODE\n" + "".join(_node(i + 1, *map(float, p)) for i, p in enumerate(CUBE))
    return text + "*ELEMENT_SOLID\n" + _shell(1, 1, *range(1, 9))


def _plate(n: int = 2, size: float = 1.0) -> str:
    """n x n quads in z = 0, normals +z, node (i, j) = 1 + i + (n + 1) j."""
    text = "*NODE\n" + "".join(_node(1 + i + (n + 1) * j, i * size, j * size, 0.0)
                               for j in range(n + 1) for i in range(n + 1))
    text += "*ELEMENT_SHELL\n"
    for j in range(n):
        for i in range(n):
            a = 1 + i + (n + 1) * j
            text += _shell(1 + i + n * j, 1, a, a + 1, a + n + 2, a + n + 1)
    return text


def _cylinder(radius: float = 10.0, segments: int = 6, rows: int = 2) -> str:
    """Quarter-cylinder patch about z with outward normals."""
    angles = np.linspace(0.0, np.pi / 2, segments + 1)
    text = "*NODE\n"
    for j in range(rows + 1):
        for i, a in enumerate(angles):
            text += _node(1 + i + (segments + 1) * j, radius * np.cos(a), radius * np.sin(a), float(j))
    text += "*ELEMENT_SHELL\n"
    for j in range(rows):
        for i in range(segments):
            a = 1 + i + (segments + 1) * j
            text += _shell(1 + i + segments * j, 1, a, a + 1, a + segments + 2, a + segments + 1)
    return text


def _coords(deck: KeywordDeck) -> dict[int, np.ndarray]:
    ids, xyz = nodes(deck)
    return {int(i): p for i, p in zip(ids, xyz)}


def test_linear_array_places_each_copy_one_step_further(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _cube())
    result = array_elements(deck, "*ELEMENT_SOLID", [1], 3, offset=(2.0, 0.0, 0.0))
    assert result == {"copies": 3, "nodes": 24, "elements": 3, "first_node": 9, "first_element": 2,
                      "mirrored_copies": 0}
    coords = _coords(deck)
    eids, _, conn = elements(deck, "*ELEMENT_SOLID", 8)
    assert eids.tolist() == [1, 2, 3, 4]
    for k, row in enumerate(conn):
        assert np.allclose(coords[int(row[0])], (2.0 * k, 0.0, 0.0))


def test_polar_array_rotates_about_the_axis(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _plate(1))
    matrix = rotation_matrix((0, 0, 1), 90.0)
    array_elements(deck, "*ELEMENT_SHELL", [1], 3, matrix=matrix)
    coords = _coords(deck)
    _, _, conn = elements(deck, "*ELEMENT_SHELL", 4)
    corner = [coords[int(row[2])] for row in conn]  # node (1, 1) and its rotated images
    assert np.allclose(corner, [(1, 1, 0), (-1, 1, 0), (-1, -1, 0), (1, -1, 0)], atol=1e-12)


def test_array_refuses_identity_and_bad_counts(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _cube())
    with pytest.raises(FieldError, match="identity"):
        array_elements(deck, "*ELEMENT_SOLID", [1], 2)
    for count in (0, 1001, 2.0, True):
        with pytest.raises(FieldError, match="count"):
            array_elements(deck, "*ELEMENT_SOLID", [1], count, offset=(1, 0, 0))


def test_offset_copy_of_a_flat_plate(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _plate(2))
    result = offset_shells(deck, [1, 2, 3, 4], 0.5)
    assert result["copied"] and result["shells"] == 4 and result["nodes"] == 9
    assert result["max_normal_spread_deg"] == pytest.approx(0.0, abs=1e-9)
    assert (result["first_node"], result["first_element"]) == (10, 5)
    coords = _coords(deck)
    eids, pids, conn = elements(deck, "*ELEMENT_SHELL", 4)
    assert eids.tolist() == [1, 2, 3, 4, 5, 6, 7, 8] and set(pids.tolist()) == {1}
    for old, new in zip(conn[:4], conn[4:]):
        for a, b in zip(old, new):
            assert np.allclose(coords[int(b)], coords[int(a)] + (0.0, 0.0, 0.5))


def test_offset_on_a_cylinder_keeps_interior_nodes_on_radius_plus_distance(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _cylinder(10.0))
    result = offset_shells(deck, range(1, 13), 1.5)
    assert 0 < result["max_normal_spread_deg"] < 15.1  # half of one 15 deg segment at the patch edge
    coords = _coords(deck)
    first = result["first_node"]
    interior = [first + 1 + i + 7 * j for j in range(3) for i in range(5)]  # angles strictly inside
    radii = [np.hypot(*coords[n][:2]) for n in interior]
    assert np.allclose(radii, 11.5, rtol=1e-8)  # input rounded to 10 digits


def test_offset_in_place_and_shared_node_refusal(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _plate(2))
    with pytest.raises(FieldError, match="shared with unselected"):
        offset_shells(deck, [1], 0.25, copy=False)
    result = offset_shells(deck, [1, 2, 3, 4], -0.25, copy=False)
    assert not result["copied"] and result["max_rounding"] == 0.0
    assert all(p[2] == -0.25 for p in _coords(deck).values())


def test_offset_refuses_inconsistent_normals_and_eight_node_shells(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _plate(2))
    reverse_elements(deck, "*ELEMENT_SHELL", [2])
    with pytest.raises(FieldError, match="unify_shell_normals"):
        offset_shells(deck, [1, 2, 3, 4], 0.5)
    eight = "*NODE\n" + "".join(_node(i, float(i), 0.0, 0.0) for i in range(1, 9))
    deck = _deck(tmp_path, eight + "*ELEMENT_SHELL\n" + _shell(1, 1, *range(1, 9)))
    with pytest.raises(Unsupported, match="8-node"):
        copy_elements(deck, "*ELEMENT_SHELL", [1], offset=(0, 0, 1))


def test_triangles_count_each_node_once(tmp_path: Path) -> None:
    text = "*NODE\n" + _node(1, 0.0, 0.0, 0.0) + _node(2, 1.0, 0.0, 0.0) + _node(3, 0.0, 1.0, 0.0)
    deck = _deck(tmp_path, text + "*ELEMENT_SHELL\n" + _shell(1, 1, 1, 2, 3, 3))
    used, unit, _ = shell_nodal_normals(deck, elements(deck, "*ELEMENT_SHELL", 4)[2])
    assert used.tolist() == [1, 2, 3] and np.allclose(unit, (0.0, 0.0, 1.0))


def test_edit_deck_ops_are_saved_and_reload(tmp_path: Path) -> None:
    (tmp_path / "main.k").write_bytes(("*KEYWORD\n" + _plate(2) + "*PART\nplate\n       1       1       1\n"
                                       "*END\n").encode("ascii"))
    out = tmp_path / "out"
    result = edit_deck(str(tmp_path / "main.k"), [
        {"op": "offset_shells", "ids": [1, 2, 3, 4], "distance": 0.1},
        {"op": "array_elements", "keyword": "*ELEMENT_SHELL", "ids": [1, 2, 3, 4], "count": 2,
         "translate": [0.0, 0.0, 1.0]},
    ], output_dir=str(out))
    assert result["status"] == "succeeded", result
    deck = KeywordDeck.load(out / "main.k")
    eids, _, _ = elements(deck, "*ELEMENT_SHELL", 4)
    assert eids.size == 16 and nodes(deck)[0].size == 36
    assert {s["op"] for s in result["summaries"]} == {"offset_shells", "array_elements"}
