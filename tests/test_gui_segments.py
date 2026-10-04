import numpy as np
import pytest

from ls_prepost_mcp.entity_cards import inspect_cards
from ls_prepost_mcp.segment_geometry import build_segments, canonical_cycle


def two_hex(path):
    coords = [(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1),
              (2,0,0),(2,1,0),(2,0,1),(2,1,1)]
    path.write_text("*KEYWORD\n*NODE\n" + "\n".join(
        ",".join(map(str, (i, *xyz))) for i, xyz in enumerate(coords, 1)) +
        "\n*ELEMENT_SOLID\n1,1,1,2,3,4,5,6,7,8\n2,2,2,9,10,3,6,11,12,7\n*END\n")
    return path


def test_solid_exterior_removes_interface_against_unselected_cells(tmp_path):
    path = two_hex(tmp_path / "two.k")
    records, audit = build_segments(path, "solid_exterior", [1])
    assert len(records) == 5 and sum(r["measure"] for r in audit) == pytest.approx(5)
    assert not any(set(r["node_ids"]) == {2, 3, 6, 7} for r in records)
    records, audit = build_segments(path, "solid_exterior", [1, 2])
    assert len(records) == 10 and sum(r["measure"] for r in audit) == pytest.approx(10)
    assert all(np.linalg.norm(r["normal"]) == pytest.approx(1) for r in audit)


def test_normal_filter_precedes_explicit_reverse_and_preserves_face_identity(tmp_path):
    path = two_hex(tmp_path / "two.k")
    records, audit = build_segments(path, "solid_exterior", [1, 2], [0, 0, 1])
    flipped, reverse = build_segments(path, "solid_exterior", [1, 2], [0, 0, 1], reverse=True)
    assert len(records) == 2
    assert [set(r["node_ids"]) for r in records] == [set(r["node_ids"]) for r in flipped]
    assert all(r["normal"] == [0., 0., 1.] for r in audit)
    assert all(r["normal"] == [0., 0., -1.] for r in reverse)
    for a, b in zip(records, flipped):
        assert canonical_cycle(tuple(reversed(a["node_ids"]))) == tuple(b["node_ids"])


def test_tet_triangles_have_outward_normals(tmp_path):
    p = tmp_path / "tet.k"
    p.write_text("*KEYWORD\n*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n*ELEMENT_SOLID\n1,1,1,2,3,4,4,4,4,4\n*END\n")
    records, audit = build_segments(p, "solid_exterior", [1])
    assert len(records) == 4 and all(len(r["node_ids"]) == 3 for r in records)
    assert sum(r["measure"] for r in audit) == pytest.approx(1.5 + np.sqrt(3)/2)


def test_2d_boundary_has_no_internal_edge_and_rejects_off_plane(tmp_path):
    p = tmp_path / "plate.k"
    p.write_text("*KEYWORD\n*NODE\n1,0,0,0\n2,1,0,0\n3,2,0,0\n4,0,1,0\n5,1,1,0\n6,2,1,0\n*ELEMENT_SHELL\n1,1,1,2,5,4\n2,1,2,3,6,5\n*END\n")
    records, audit = build_segments(p, "shell_boundary_2d", [1, 2])
    assert len(records) == 6 and sum(r["measure"] for r in audit) == pytest.approx(6)
    assert not any(set(r["node_ids"]) == {2, 5} for r in records)
    p.write_text(p.read_text().replace("0,0\n", "0,1\n").replace("1,0\n", "1,1\n"))
    with pytest.raises(ValueError, match="XY plane"):
        build_segments(p, "shell_boundary_2d", [1, 2])


def test_segment_native_reader_preserves_direction_and_triangle_padding(tmp_path):
    pytest.importorskip("ansys.dyna.core")
    p = tmp_path / "set.k"
    p.write_text("*KEYWORD\n*SET_SEGMENT_TITLE\nFaces\n10\n1,2,3,3\n4,5,0,0\n*END\n")
    records = inspect_cards(p)["sets"][("segment", 10)]["segments"]
    assert records[0]["node_ids"] == [1, 2, 3] and records[1]["node_ids"] == [4, 5]
    p.write_text(p.read_text().replace("4,5,0,0", "5,4,0,0"))
    assert inspect_cards(p)["sets"][("segment", 10)]["segments"][1]["node_ids"] == [5, 4]
