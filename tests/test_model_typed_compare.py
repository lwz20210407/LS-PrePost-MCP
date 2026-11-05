"""Semantic comparison retains declared integer versus continuous field types."""
import json

import pytest

from ls_prepost_mcp.domain.model.compare import compare_decks


def pair(tmp_path, a, b):
    paths = []
    for name, text in (("a", a), ("b", b)):
        root = tmp_path / name
        root.mkdir()
        path = root / "main.k"
        path.write_text("*KEYWORD_LONG\n" + text + "*END\n", encoding="ascii")
        paths.append(str(path))
    return paths


def compare_pair(tmp_path, a, b, **kwargs):
    result = compare_decks(*pair(tmp_path, a, b), **kwargs)
    assert result["unchecked"] == {"a": {}, "b": {}}, "This fixture must be fully supported, not an unchecked format"
    return result


def properties():
    pytest.importorskip("ansys.dyna.core")
    return "*MAT_ELASTIC\n1,1,1000000000,0.3\n*SECTION_SOLID\n1,1\n"


def test_part_reference_to_a_nearby_material_id_changes_the_model(tmp_path):
    pytest.importorskip("ansys.dyna.core")
    shared = "*MAT_ELASTIC\n1000000000,1,100,0.3\n*MAT_ELASTIC\n1000000001,1,100,0.3\n*SECTION_SOLID\n1,1\n"
    a = shared + "*PART\naudit\n1,1,1000000000\n"
    b = shared + "*PART\naudit\n1,1,1000000001\n"
    result = compare_pair(tmp_path, a, b, include_mesh=False)
    assert not result["identical"]
    assert result["entities"]["part"]["changed"][0]["fields"]["mid"] == {"a": 1000000000, "b": 1000000001}
    assert "kinds" not in json.loads(json.dumps(result))


def test_element_part_reference_is_discrete_even_with_a_large_float_tolerance(tmp_path):
    nodes = "*NODE\n" + "".join(f"{i},{i},0,0\n" for i in range(1, 9))
    shared = nodes + properties() + "*PART\na\n10000000,1,1\n*PART\nb\n10000001,1,1\n"
    a = shared + "*ELEMENT_SOLID\n17,10000000,1,2,3,4,5,6,7,8\n"
    b = shared + "*ELEMENT_SOLID\n17,10000001,1,2,3,4,5,6,7,8\n"
    assert not compare_pair(tmp_path, a, b, rel_tol=1e-6)["identical"]


def test_part_set_member_ids_are_not_physical_floats(tmp_path):
    shared = properties() + "*PART\na\n1000000000,1,1\n*PART\nb\n1000000001,1,1\n"
    a = shared + "*SET_PART_LIST_COLLECT\n20\n1000000000\n*SET_PART_LIST_COLLECT\n20\n1000000000\n"
    b = shared + "*SET_PART_LIST_COLLECT\n20\n1000000001\n*SET_PART_LIST_COLLECT\n20\n1000000000\n"
    assert not compare_pair(tmp_path, a, b, include_mesh=False)["identical"]


def test_merged_collect_headers_keep_float_attribute_tolerance(tmp_path):
    shared = properties() + "*PART\na\n1,1,1\n"
    a = shared + "*SET_PART_LIST_COLLECT\n20,1000000000\n1\n*SET_PART_LIST_COLLECT\n20\n1\n"
    b = shared + "*SET_PART_LIST_COLLECT\n20,1000000001\n1\n*SET_PART_LIST_COLLECT\n20\n1\n"
    assert compare_pair(tmp_path, a, b, include_mesh=False)["identical"]


def test_integer_parameter_change_is_not_hidden_by_float_tolerance(tmp_path):
    assert not compare_pair(tmp_path, "*PARAMETER\nIvalue,1000000000\n", "*PARAMETER\nIvalue,1000000001\n")["identical"]


def test_real_parameter_and_equivalent_float_text_keep_existing_policy(tmp_path):
    assert compare_pair(tmp_path, "*PARAMETER\nRvalue,1000000000\n", "*PARAMETER\nRvalue,1000000001\n")["identical"]


def test_equivalent_continuous_values_have_the_same_meaning_across_text_styles(tmp_path):
    pytest.importorskip("ansys.dyna.core")
    a = "*MAT_ELASTIC\n1,1,1000000000,0.3\n"
    b = "*MAT_ELASTIC\n1,1,1.0e9,3.0e-1\n"
    assert compare_pair(tmp_path, a, b, include_mesh=False)["identical"]


def test_curve_ordinates_keep_the_callers_float_tolerance(tmp_path):
    a = "*DEFINE_CURVE\n10\n0,1000000000\n1,1000000000\n"
    b = "*DEFINE_CURVE\n10\n0,1000000001\n1,1000000000\n"
    assert compare_pair(tmp_path, a, b, include_mesh=False)["identical"]


def test_compare_strings_remain_case_sensitive(tmp_path):
    a = properties() + "*PART\nAbC\n1,1,1\n"
    b = properties() + "*PART\nabc\n1,1,1\n"
    assert not compare_pair(tmp_path, a, b, include_mesh=False)["identical"]


def test_coordinate_displacement_threshold_remains_separate_from_field_rel_tol(tmp_path):
    a = "*NODE\n1,0,0,0\n"
    b = "*NODE\n1,1e-14,0,0\n"
    assert not compare_pair(tmp_path, a, b, rel_tol=1)["identical"]


def test_mesh_parameter_cells_reuse_the_existing_ast_decoder(tmp_path):
    nodes = "*NODE\n" + "".join(f"{i},{i},0,0\n" for i in range(1, 9))
    shared = nodes + "*PARAMETER\nIowner,10\n" + properties() + "*PART\na\n10,1,1\n"
    a = shared + "*ELEMENT_SOLID\n17,&owner,1,2,3,4,5,6,7,8\n"
    b = shared + "*ELEMENT_SOLID\n17,10,1,2,3,4,5,6,7,8\n"
    assert compare_pair(tmp_path, a, b)["identical"]
