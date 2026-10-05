"""Keyword-level geometry: node selection, exterior segments of solids, set creation."""
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.domain.model.geometry import (
    check_segment_normals,
    exterior_segments,
    nodes,
    select_elements,
    select_nodes,
)
from ls_prepost_mcp.domain.model.operations import edit_deck, inspect_deck

pytest.importorskip("ansys.dyna.core")


def _node(nid: int, x: float, y: float, z: float) -> str:
    return f"{nid:>8}{x:>16}{y:>16}{z:>16}\n"


def _solid(eid: int, pid: int, *ns: int) -> str:
    return f"{eid:>8}{pid:>8}" + "".join(f"{n:>8}" for n in ns) + "\n"


def _two_hex() -> str:
    text = "*KEYWORD\n*NODE\n"
    for k in range(2):
        for j in range(2):
            for i in range(3):
                text += _node(1 + i + 3 * j + 6 * k, float(i), float(j), float(k))
    text += "*ELEMENT_SOLID\n" + _solid(1, 1, 1, 2, 5, 4, 7, 8, 11, 10) + _solid(2, 2, 2, 3, 6, 5, 8, 9, 12, 11)
    return text + "*PART\nleft\n         1         1         1\nright\n         2         1         1\n*END\n"


def _deck(tmp_path: Path, text: str) -> KeywordDeck:
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    return KeywordDeck.load(tmp_path / "main.k")


def _outward(deck: KeywordDeck, faces: np.ndarray, inside: np.ndarray) -> bool:
    ids, xyz = nodes(deck)
    where = {int(n): xyz[i] for i, n in enumerate(ids)}
    for face in faces:
        p = np.array([where[int(n)] for n in face])
        normal = np.cross(p[2] - p[0], p[3] - p[1])
        if np.dot(normal, p.mean(axis=0) - inside) <= 0:
            return False
    return True


def test_two_hexes_exterior_and_direction(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _two_hex())
    faces = exterior_segments(deck)
    assert len(faces) == 10
    assert _outward(deck, faces, np.array([1.0, 0.5, 0.5]))
    top = exterior_segments(deck, direction=[0, 0, 1])
    assert sorted(map(sorted, top.tolist())) == [[7, 8, 10, 11], [8, 9, 11, 12]]
    assert len(exterior_segments(deck, parts=[2], direction=[1, 0, 0])) == 1
    assert len(exterior_segments(deck, box=[1.9, -1, -1, 3, 2, 2])) == 1  # only the x=2 face centroid


def test_tetrahedron_and_pentahedron(tmp_path: Path) -> None:
    tet = ("*NODE\n" + _node(1, 0.0, 0.0, 0.0) + _node(2, 1.0, 0.0, 0.0) + _node(3, 0.0, 1.0, 0.0)
           + _node(4, 0.0, 0.0, 1.0) + "*ELEMENT_SOLID\n" + _solid(1, 1, 1, 2, 3, 4, 4, 4, 4, 4))
    deck = _deck(tmp_path, tet)
    faces = exterior_segments(deck)
    assert len(faces) == 4 and (faces[:, 2] == faces[:, 3]).all()
    assert _outward(deck, faces, np.array([0.25, 0.25, 0.25]))
    wedge = ("*NODE\n" + _node(1, 0.0, 0.0, 0.0) + _node(2, 1.0, 0.0, 0.0) + _node(3, 1.0, 1.0, 0.0)
             + _node(4, 0.0, 1.0, 0.0) + _node(5, 0.5, 0.0, 1.0) + _node(6, 0.5, 1.0, 1.0)
             + "*ELEMENT_SOLID\n" + _solid(1, 1, 1, 2, 3, 4, 5, 5, 6, 6))
    (tmp_path / "w").mkdir()
    deck = _deck(tmp_path / "w", wedge)
    faces = exterior_segments(deck)
    assert len(faces) == 5 and int((faces[:, 2] == faces[:, 3]).sum()) == 2
    assert _outward(deck, faces, np.array([0.5, 0.5, 0.4]))


def test_node_and_element_selection(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _two_hex())
    assert sorted(select_nodes(deck, box=[-1, -1, 0.5, 3, 2, 2]).tolist()) == [7, 8, 9, 10, 11, 12]
    assert sorted(select_nodes(deck, plane={"point": [0, 0, 1], "normal": [0, 0, 1]}).tolist()) == [7, 8, 9, 10, 11, 12]
    assert select_nodes(deck, sphere=[0, 0, 0, 0.1]).tolist() == [1]
    assert sorted(select_nodes(deck, parts=[2], box=[1.5, -1, -1, 3, 2, 2]).tolist()) == [3, 6, 9, 12]
    assert select_elements(deck, "*ELEMENT_SOLID", box=[1, -1, -1, 3, 2, 2]).tolist() == [2]


def test_create_sets_through_edit_deck(tmp_path: Path) -> None:
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "main.k").write_bytes(_two_hex().encode("ascii"))
    edits = [{"op": "create_set", "kind": "segment", "title": "top face", "select": {"direction": [0, 0, 1]}},
             {"op": "create_set", "kind": "node", "select": {"plane": {"point": [0, 0, 0], "normal": [1, 0, 0]}}},
             {"op": "create_set", "kind": "node", "ids": [1, 2]},
             {"op": "create_set", "kind": "part", "ids": [1, 2], "sid": 50}]
    result = edit_deck(str(tmp_path / "in" / "main.k"), edits, output_dir=str(tmp_path / "out"))
    assert result["status"] == "succeeded", result
    assert [c["description"] for c in result["changes"]] == [
        "created *SET_SEGMENT_TITLE sid=1 with 2 items; normals checked on 2 sampled segments: all outward, "
        "within 0.0 deg", "created *SET_NODE_LIST sid=1 with 4 items",
        "created *SET_NODE_LIST sid=2 with 2 items", "created *SET_PART_LIST sid=50 with 2 items"]
    info = inspect_deck(str(tmp_path / "out" / "main.k"), include_mesh=True)
    assert info["elements"] == {"*ELEMENT_SOLID": 2}  # P01: element count per element keyword
    assert {d["kind"] for d in info["references"]["dangling"]} <= {"section", "material"}  # base deck lacks them
    empty = edit_deck(str(tmp_path / "in" / "main.k"),
                      [{"op": "create_set", "kind": "node", "select": {"sphere": [9, 9, 9, 0.1]}}])
    assert empty["status"] == "failed" and "empty" in empty["error"]


def test_segment_normal_check_flags_inward_faces(tmp_path: Path) -> None:
    """P04: sampled segments read back; bottom face 1-2-5-4 points into element 1, 1-4-5-2 points out."""
    from ls_prepost_mcp.domain.model.sets import create_set
    deck = _deck(tmp_path, _two_hex())
    _, inward = create_set(deck, "segment", [[1, 2, 5, 4]])
    _, outward = create_set(deck, "segment", [[1, 4, 5, 2]])
    assert check_segment_normals(deck, inward[0], [0, 0, -1])["failures"] == [1]
    good = check_segment_normals(deck, outward[0], [0, 0, -1])
    assert good["failures"] == [] and good["outward"] == 1 and good["max_angle_deg"] == 0.0
