"""G04 keyword Tri3 identities use handwritten coordinates and explicit padded connectivity."""
from copy import deepcopy

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model import KeywordDeck, geometry
from ls_prepost_mcp.service import Service


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("Keyword Identify must not dispatch Native")

    monkeypatch.setattr(Service, "_native", forbidden)
    yield
    assert calls == []


@pytest.fixture
def keyword_sdk():
    pytest.importorskip("ansys.dyna.core")


def _model(tmp_path, n4=33, included=False, missing=None, quad=False):
    root = tmp_path / "source"
    root.mkdir()
    points = [(11, 0, 0, 0), (22, 3, 0, 0), (33, 0, 3, 0)]
    if quad:
        points.append((44, 3, 3, 0))
    mesh = "*NODE\n" + "".join(f"{nid:8d}{x:16.8f}{y:16.8f}{z:16.8f}\n"
                                 for nid, x, y, z in points if nid != missing)
    conn = (11, 22, 44, 33) if quad else (11, 22, 33, n4)
    mesh += "*ELEMENT_SHELL\n" + "".join(" " * 8 if v is None else f"{v:8d}" for v in (41, 7, *conn)) + "\n"
    parts = ("*PART\nowned plate\n         7         2         3\n"
             "*SECTION_SHELL\n         2         2\n       0.1       0.1       0.1       0.1\n"
             "*MAT_ELASTIC\n         3    7.8e-9  210000.0       0.3\n")
    main = root / "main.k"
    if included:
        (root / "mesh.k").write_bytes(mesh.encode("ascii"))
        (root / "parts.k").write_bytes(parts.encode("ascii"))
        main.write_bytes(b"*KEYWORD\n*INCLUDE\nmesh.k\nparts.k\n*END\n")
    else:
        main.write_bytes(("*KEYWORD\n" + mesh + parts + "*END\n").encode("ascii"))
    return main


def _tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() if p.is_file() else None for p in root.rglob("*")}


def _selection(kind, ids):
    return dict(entity_type=kind, predicate=dict(kind="ids", ids=ids))


def _query(tmp_path, main, selection):
    original = deepcopy(selection)
    before = _tree(main.parent)
    service = Service(Settings(tmp_path / "work", allowed_roots=(main.parent,)))
    result = service.query_entities(str(main), selection)
    assert selection == original
    assert _tree(main.parent) == before
    return result


@pytest.mark.parametrize("n4", [33, 0, None], ids=["repeat", "zero", "blank"])
@pytest.mark.parametrize("included", [False, True], ids=["standalone", "include"])
@pytest.mark.parametrize("kind,ids", [("shell", [41]), ("part", [7]), ("node", [11, 22, 33])])
def test_keyword_triangle_handwritten_identities(tmp_path, keyword_sdk, n4, included, kind, ids):
    main = _model(tmp_path, n4, included)
    result = _query(tmp_path, main, _selection(kind, ids))
    assert result["status"] == "succeeded", result.get("error")
    assert result["data"]["read_only"] and result["data"]["configuration"] == "reference"
    rows = result["data"]["entities"]
    assert [r["entity_id"] for r in rows] == ids
    if kind == "shell":
        row = rows[0]
        assert row["node_ids"] == [11, 22, 33, 33]
        assert row["node_coordinates"] == [[0, 0, 0], [3, 0, 0], [0, 3, 0], [0, 3, 0]]
        assert (row["part_id"], row["section_id"], row["material_id"]) == (7, 2, 3)
    elif kind == "part":
        row = rows[0]
        assert row["node_count"] == 3 and row["bounds"] == [[0, 0, 0], [3, 3, 0]]
        assert row["element_counts"] == {"shell": 1, "solid": 0}
        assert (row["section_id"], row["material_id"]) == (2, 3)
    else:
        assert [r["coordinates"] for r in rows] == [[0, 0, 0], [3, 0, 0], [0, 3, 0]]
        assert all(r["part_ids"] == [7] and r["material_ids"] == [3] for r in rows)


@pytest.mark.parametrize("n4", [33, 0, None], ids=["repeat", "zero", "blank"])
def test_keyword_connectivity_representation_metadata_is_explicit(tmp_path, keyword_sdk, n4):
    main = _model(tmp_path, n4, included=True)
    raw_before = geometry.elements(KeywordDeck.load(main), "*ELEMENT_SHELL", 4)[2].tolist()
    result = _query(tmp_path, main, _selection("shell", [41]))
    assert result["status"] == "succeeded", result.get("error")
    assert result["data"]["entities"][0]["connectivity_representation"] == {
        "topology": "tri3", "stored_slots": 4, "padding": "repeat_third_node",
        "normalized": True, "raw_keyword_connectivity": False,
    }
    assert geometry.elements(KeywordDeck.load(main), "*ELEMENT_SHELL", 4)[2].tolist() == raw_before


@pytest.mark.parametrize("kind,ids", [("shell", [41]), ("part", [7])])
@pytest.mark.parametrize("missing,n4", [(11, 0), (22, 0), (33, 0), (None, 99)])
def test_missing_real_corner_or_nonzero_fourth_node_still_fails(tmp_path, keyword_sdk, kind, ids, missing, n4):
    main = _model(tmp_path, n4, included=True, missing=missing)
    result = _query(tmp_path, main, _selection(kind, ids))
    assert result["status"] == "failed" and result["data"] == {} and result["error"]


def test_keyword_quad_output_is_unchanged(tmp_path, keyword_sdk):
    main = _model(tmp_path, quad=True)
    result = _query(tmp_path, main, _selection("shell", [41]))
    assert result["status"] == "succeeded", result.get("error")
    assert result["data"]["entities"] == [{
        "entity_id": 41, "entity_type": "shell", "part_id": 7, "material_id": 3, "section_id": 2,
        "node_ids": [11, 22, 44, 33], "node_coordinates": [[0, 0, 0], [3, 0, 0], [3, 3, 0], [0, 3, 0]],
    }]


def test_without_keyword_sdk_returns_honest_failed_job(tmp_path):
    try:
        __import__("ansys.dyna.core")
    except ImportError:
        pass
    else:
        pytest.skip("This control executes only when the optional keyword SDK is absent")
    main = _model(tmp_path, 0, included=True)
    result = _query(tmp_path, main, _selection("shell", [41]))
    assert result["status"] == "failed" and result["data"] == {} and result["error"]["message"]
