import copy

import pytest

from ls_prepost_mcp.boundary_cards import inspect_boundary_cards, verify_boundary_delta
from ls_prepost_mcp.boundary_geometry import segment_normals, validate_boundary
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


def deck(path, body):
    path.write_text("*KEYWORD\n" + body + "\n*END\n")
    return path


def plane(path, form=13):
    return deck(path, "*NODE\n1,0,0,0\n2,1,0,0\n3,1,1,0\n4,0,1,0\n*ELEMENT_SHELL\n1,1,1,2,3,4\n"
                f"*PART\nContinuum\n1,1,1\n*SECTION_SHELL\n1,{form}\n1,1,1,1")


def test_pressure_curve_and_named_load_readback_preserve_all_rows(tmp_path):
    before = inspect_boundary_cards(deck(tmp_path / "before.k", "*TITLE\nModel"))
    after = inspect_boundary_cards(deck(tmp_path / "after.k", "*TITLE\nModel\n*DEFINE_CURVE_TITLE\nPressure\n500,0,1,1,0,0,0,0\n0,0\n1,2.5\n2,0\n"
                                        "*LOAD_SEGMENT_SET_ID\n600,Top pressure\n100,500,1.0,0.0"))
    expected_curve = dict(after["curves"][500])
    expected_load = dict(after["loads"][0])
    assert verify_boundary_delta(before, after, curve=expected_curve, load=expected_load)["native_card_references_verified"]
    broken = copy.deepcopy(after)
    broken["curves"][500]["points"][1][1] = 25.0
    with pytest.raises(ValueError, match="samples"):
        verify_boundary_delta(before, broken, curve=expected_curve, load=expected_load)
    broken = copy.deepcopy(after)
    broken["loads"][0]["scale"] = -1.0
    with pytest.raises(ValueError, match="loads"):
        verify_boundary_delta(before, broken, curve=expected_curve, load=expected_load)


def test_curve_namespace_includes_tables_and_functions(tmp_path):
    data = inspect_boundary_cards(deck(tmp_path / "namespace.k", "*DEFINE_TABLE\n500\n1,3\n*DEFINE_FUNCTION\n600\nf(t)=t;"))
    assert data["namespace_ids"] == {500, 600}
    with pytest.raises(ValueError, match="namespace ID"):
        inspect_boundary_cards(deck(tmp_path / "collision.k", "*DEFINE_TABLE\n500\n1,3\n*DEFINE_CURVE\n500\n0,0\n1,1"))


def test_native_curve_precision_may_not_collapse_distinct_times(tmp_path):
    before = inspect_boundary_cards(deck(tmp_path / "before.k", "*TITLE\nModel"))
    after = inspect_boundary_cards(deck(tmp_path / "after.k", "*TITLE\nModel\n*DEFINE_CURVE\n500\n0,0\n1,1\n1,2"))
    expected = copy.deepcopy(after["curves"][500])
    expected["points"][-1][0] = 1.00000001
    with pytest.raises(ValueError, match="samples"):
        verify_boundary_delta(before, after, curve=expected)


def test_legacy_boundary_verification_checks_order_not_only_set_membership(tmp_path):
    before = inspect_boundary_cards(deck(tmp_path / "before.k", "*TITLE\nModel"), True)
    after = inspect_boundary_cards(deck(tmp_path / "after.k", "*TITLE\nModel\n*SET_NODE_LIST_TITLE\nedge\n1000\n4,1\n*BOUNDARY_NON_REFLECTING_2D\n1000,0,0"), True)
    expected_set = dict(entity_type="node", set_id=1000, title="edge", member_ids=[1,4], order=[4,1],
                        attributes=[0.]*4, solver="MECH", its="1")
    boundary = dict(dimension=2, target_id=1000, ad=0., as_=0.)
    assert verify_boundary_delta(before, after, nonreflecting=[boundary], new_node_sets=[expected_set])["native_card_references_verified"]
    after["ordered_node_sets"][1000]["order"] = [1,4]
    with pytest.raises(ValueError, match="order changed"):
        verify_boundary_delta(before, after, nonreflecting=[boundary], new_node_sets=[expected_set])


def test_unscoped_ale_boundary_is_not_treated_as_no_boundary(tmp_path):
    data = inspect_boundary_cards(deck(tmp_path / "ale.k", "*BOUNDARY_NON_REFLECTING_2D"))
    assert data["unresolved"] and not data["nonreflecting"]


def test_2d_nr_requires_counterclockwise_edges_and_continuum_form(tmp_path):
    records = [dict(node_ids=[1,2], attributes=[0.0]*4)]
    path = plane(tmp_path / "plane.k")
    dimension, normals = segment_normals(path, records)
    assert dimension == 2 and normals[0]["positive_pressure_direction"] == [0.,1.,0.]
    assert validate_boundary(path, records, 2)["two_dimensional_order_verified"]
    reversed_records = [dict(node_ids=[2,1], attributes=[0.0]*4)]
    with pytest.raises(ValueError, match="counterclockwise"):
        validate_boundary(path, reversed_records, 2)
    assert validate_boundary(path, reversed_records, 2, require_ccw=False)["reversed_segments"] == 1
    plane(path, form=2)
    with pytest.raises(ValueError, match="formulations"):
        validate_boundary(path, records, 2)


@pytest.mark.parametrize("points", [[[0.,0.],[0.,1.]], [[1.,0.],[0.,1.]], [[0.,0.],[1.,float('nan')]]])
def test_bad_pressure_curve_rejected_before_native_work(tmp_path, points):
    service = Service(Settings(tmp_path))
    with pytest.raises(ValueError, match="finite pairs"):
        service.create_gui_segment_pressure("unused", 1, 2, "Pressure", points, "ms", "MPa", "mm")


def test_wrong_dimensions_and_old_solver_2d_segment_route_rejected(tmp_path):
    service = Service(Settings(tmp_path))
    with pytest.raises(ValueError, match="physical dimension"):
        service.create_gui_segment_pressure("unused", 1, 2, "Pressure", [[0.,0.],[1.,1.]], "mm", "MPa", "mm")
    with pytest.raises(ValueError, match="R14"):
        service.create_gui_nonreflecting_boundary("unused", 1, 2, 11, "mm")
    with pytest.raises(ValueError, match="Wave family"):
        service.create_gui_nonreflecting_boundary("unused", 1, 3, 11, "mm", False, "off")
    with pytest.raises(ValueError, match="documented default"):
        service.create_gui_nonreflecting_boundary("unused", 1, 2, 11, "mm", False, True, node_set_start_id=1000)


def test_secondary_legacy_node_set_collision_rejects_before_any_import(tmp_path, monkeypatch):
    pytest.importorskip("ansys.dyna.core")
    service = Service(Settings(tmp_path))
    path = plane(tmp_path / "plane.k")
    body = path.read_text().replace("*END", "*SET_SEGMENT\n10\n1,2,0,0\n2,3,0,0\n3,4,0,0\n4,1,0,0\n*SET_NODE_LIST\n1002\n1\n*END")
    path.write_text(body)
    def transaction(sid, action, parameters, commands, verify, **kwargs):
        kwargs["preflight"](path)
        pytest.fail("ID collision must reject before native commands")
    monkeypatch.setattr(service, "_gui_mesh_edit", transaction)
    with pytest.raises(ValueError, match="already exists"):
        service.create_gui_nonreflecting_boundary("unused", 10, 2, 11, "mm", node_set_start_id=1000)


def test_invalid_existing_3d_target_is_not_silently_coerced_to_positive(tmp_path, monkeypatch):
    pytest.importorskip("ansys.dyna.core")
    service = Service(Settings(tmp_path))
    path = deck(tmp_path / "tet.k", "*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n"
                "*ELEMENT_SOLID\n1,1,1,2,3,4,4,4,4,4\n*SET_SEGMENT\n10\n1,3,2,2\n"
                "*BOUNDARY_NON_REFLECTING\n-10,0,0")
    def transaction(sid, action, parameters, commands, verify, **kwargs):
        kwargs["preflight"](path)
        pytest.fail("Unsupported existing target must reject")
    monkeypatch.setattr(service, "_gui_mesh_edit", transaction)
    with pytest.raises(ValueError, match="Unsupported existing"):
        service.create_gui_nonreflecting_boundary("unused", 10, 3, 11, "mm")


def test_documented_disabled_wave_baseline_emits_both_flags_without_inversion(tmp_path, monkeypatch):
    pytest.importorskip("ansys.dyna.core")
    service = Service(Settings(tmp_path))
    path = deck(tmp_path / "tet.k", "*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n"
                "*ELEMENT_SOLID\n1,1,1,2,3,4,4,4,4,4\n*SET_SEGMENT\n10\n1,3,2,2")
    def transaction(sid, action, parameters, commands, verify, **kwargs):
        kwargs["preflight"](path)
        commands({}, tmp_path)
        assert inspect_boundary_cards(tmp_path / "nonreflecting.k")["nonreflecting"] == [
            dict(dimension=3, target_id=10, ad=1., as_=1.)]
    monkeypatch.setattr(service, "_gui_mesh_edit", transaction)
    service.create_gui_nonreflecting_boundary("unused", 10, 3, 11, "mm", False, False)
