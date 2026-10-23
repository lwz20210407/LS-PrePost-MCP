"""G04 read-only entity identification; no ad-hoc keyword parsing or companion guessing."""

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


def selection(kind, ids):
    return {"entity_type": kind, "predicate": {"kind": "ids", "ids": ids}}


@pytest.fixture
def keyword_model(tmp_path):
    pytest.importorskip("ansys.dyna.core")
    root = tmp_path / "source"
    root.mkdir()
    (root / "mesh.k").write_text(
        "*NODE\n1,,2,3\n2,1,2,3\n3,1,3,3\n4,0,3,3\n*ELEMENT_SHELL_THICKNESS\n10,7,1,2,3,4\n0.1,0.1,0.1,0.1\n"
    )
    (root / "parts.k").write_text(
        "*PART\nskin\n7,2,3\n*SECTION_SHELL\n2,2\n0.1,0.1,0.1,0.1\n*MAT_ELASTIC\n3,1,100,0.3\n"
    )
    main = root / "main.k"
    main.write_text("*KEYWORD\n*INCLUDE\nmesh.k\nparts.k\n*END\n")
    return main


@pytest.mark.parametrize("kind,ids", [("node", [1, 2]), ("shell", [10]), ("part", [7])])
def test_keyword_identity_uses_include_engine_and_preserves_every_byte(keyword_model, tmp_path, kind, ids):
    service = Service(Settings(tmp_path / "work", allowed_roots=(keyword_model.parent,)))
    before = {p.name: p.read_bytes() for p in keyword_model.parent.iterdir()}
    result = service.query_entities(str(keyword_model), selection(kind, ids))
    assert result["status"] == "succeeded", result.get("error")
    rows = result["data"]["entities"]
    assert [r["entity_id"] for r in rows] == ids
    if kind == "node":
        assert rows[0]["coordinates"] == [0.0, 2.0, 3.0]  # Empty fixed field is not a shifted token.
        assert rows[0]["part_ids"] == [7] and rows[0]["material_ids"] == [3]
    elif kind == "shell":
        assert rows[0]["node_ids"] == [1, 2, 3, 4] and rows[0]["part_id"] == 7 and rows[0]["material_id"] == 3
    else:
        assert rows[0]["material_id"] == 3 and rows[0]["section_id"] == 2
        assert rows[0]["node_count"] == 4
    assert before == {p.name: p.read_bytes() for p in keyword_model.parent.iterdir()}


def test_result_identity_does_not_open_or_guess_a_sibling_keyword(tmp_path, monkeypatch):
    from pathlib import Path

    from tests.test_field_metrics import write_synthetic

    pytest.importorskip("lasso.dyna")
    root = tmp_path / "source"
    root.mkdir()
    source = write_synthetic(root / "d3plot")
    sibling = root / "unrelated.k"
    sibling.write_text("*PART\nunrelated\n7,8,999\n")
    original = Path.open

    def guarded(path, *a, **k):
        if path == sibling:
            pytest.fail("Result identity opened an undeclared companion")
        return original(path, *a, **k)

    monkeypatch.setattr(Path, "open", guarded)
    service = Service(Settings(tmp_path / "work", allowed_roots=(root,)))
    result = service.query_entities(
        str(source), selection("solid", [10]), source_kind="d3plot", state=3, quantity="sxx", units="MPa"
    )
    assert result["status"] == "partial" and result["warnings"]
    row = result["data"]["entities"][0]
    assert row["part_id"] == 7 and row["material_id"] is None
    assert row["result"]["value"] == 200 and row["result"]["state"] == 3
    field = service.extract_field(
        str(source), "solid", "sxx", state=3, mask="all", units="MPa", output_format="none", part_ids=[7]
    )
    assert row["result"]["value"] == field["data"]["values"][0]


def test_missing_entity_never_becomes_a_successful_empty_selection(keyword_model, tmp_path):
    service = Service(Settings(tmp_path / "work", allowed_roots=(keyword_model.parent,)))
    result = service.query_entities(str(keyword_model), selection("node", [999]))
    assert result["status"] == "failed" and result["error"]


def test_deformed_result_positions_do_not_erase_reference_displacement(tmp_path):
    pytest.importorskip("lasso.dyna")
    import numpy as np
    from lasso.dyna import ArrayType, D3plot

    from tests.test_field_metrics import write_synthetic

    root = tmp_path / "source"
    root.mkdir()
    seed = write_synthetic(root / "d3plot")
    plot = D3plot(str(seed))
    plot.arrays[ArrayType.node_coordinates] = np.ones((24, 3))
    plot.arrays[ArrayType.node_displacement] = np.broadcast_to(
        np.array([1.0, 2.0, 4.0])[:, None, None], (3, 24, 3)
    ).copy()
    output = tmp_path / "state"
    output.mkdir()
    plot.write_d3plot(str(output / "d3plot"))
    service = Service(Settings(tmp_path / "work", allowed_roots=(output,)))
    selector = {**selection("node", [2]), "configuration": "deformed", "state": 3}
    result = service.query_entities(
        str(output / "d3plot"), selector, source_kind="d3plot", quantity="displacement_z", units="mm"
    )
    assert result["status"] == "partial", result.get("error")
    row = result["data"]["entities"][0]
    assert row["coordinates"] == [4.0, 4.0, 4.0] and row["result"]["value"] == 3.0
    assert row["result"]["state"] == 3 and result["data"]["configuration"] == "deformed"


def test_result_validity_filters_returned_ids_and_is_reported(tmp_path):
    pytest.importorskip("lasso.dyna")
    from tests.test_field_metrics import write_synthetic

    root = tmp_path / "source"
    root.mkdir()
    source = write_synthetic(root / "d3plot")
    service = Service(Settings(tmp_path / "work", allowed_roots=(root,)))
    selector = {**selection("solid", [10, 20]), "validity": "deleted"}
    result = service.query_entities(
        str(source), selector, source_kind="d3plot", state=3, quantity="sxy", units="MPa"
    )
    assert result["status"] == "partial", result.get("error")
    assert result["data"]["validity"] == "deleted"
    assert [r["entity_id"] for r in result["data"]["entities"]] == [20]
    assert result["data"]["entities"][0]["result"]["value"] == 60.0


def test_set_with_an_undefined_node_does_not_index_an_unrelated_coordinate(keyword_model, tmp_path):
    keyword_model.write_text(keyword_model.read_text().replace("*END", "*SET_NODE_LIST\n11\n9\n*END"))
    service = Service(Settings(tmp_path / "work", allowed_roots=(keyword_model.parent,)))
    selector = {"entity_type": "node", "predicate": {"kind": "sets", "set_type": "node", "ids": [11]}}
    result = service.query_entities(str(keyword_model), selector)
    assert result["status"] == "failed" and result["data"] == {}


def test_reference_result_geometry_does_not_require_a_state(tmp_path):
    pytest.importorskip("lasso.dyna")
    from tests.test_field_metrics import write_synthetic

    source = write_synthetic(tmp_path / "d3plot")
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    result = service.query_entities(str(source), selection("solid", [10]), source_kind="d3plot")
    assert result["status"] == "partial", result.get("error")
    assert result["data"]["entities"][0]["part_id"] == 7
    assert result["data"]["state"] is None
