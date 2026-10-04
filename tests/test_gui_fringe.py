import math

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.field_contracts import SamplingSpec
from ls_prepost_mcp.gui_fringe import field_range, parse_field
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.stress import native_mises_matches


def test_field_table_requires_matching_ids_state_part_and_completion(tmp_path):
    path, marker = tmp_path / "native.csv", tmp_path / "complete.txt"
    marker.write_text("4 2\n")
    header = "state,time,entity_id,part_id,stress_x\n"
    path.write_text(header + "3,0.2,101,7,-4\n3,0.2,507,7,6\n")
    rows, total = parse_field(path, marker, "solid", "stress_x", 3, 0.2, [7])
    assert total == 4 and [r[2] for r in rows] == [101, 507]
    for text in [
        "3,0.2,101,7,-4\n3,0.2,101,7,6\n",
        "2,0.2,101,7,-4\n3,0.2,507,7,6\n",
        "3,0.3,101,7,-4\n3,0.2,507,7,6\n",
        "3,0.2,101,8,-4\n3,0.2,507,7,6\n",
        "3,0.2,101,7,nan\n3,0.2,507,7,6\n",
        "3,0.2,101,7,-4\n",
    ]:
        path.write_text(header + text)
        with pytest.raises(ValueError):
            parse_field(path, marker, "solid", "stress_x", 3, 0.2, [7])


def test_node_table_does_not_invent_single_part_membership(tmp_path):
    path, marker = tmp_path / "native.csv", tmp_path / "complete.txt"
    marker.write_text("8 1\n")
    path.write_text("state,time,entity_id,part_id,disp_x\n1,0,13,,2\n")
    assert parse_field(path, marker, "node", "disp_x", 1, 0, [7])[0][0][3] is None
    path.write_text("state,time,entity_id,part_id,disp_x\n1,0,13,7,2\n")
    with pytest.raises(ValueError):
        parse_field(path, marker, "node", "disp_x", 1, 0, [7])


@pytest.mark.parametrize("bounds", [[0, 0], [2, 1], [True, 2], [0, math.inf], [math.nan, 2], [0, 1e100], []])
def test_invalid_fixed_color_ranges_fail(bounds):
    with pytest.raises(ValueError):
        field_range([1, 2], bounds)


def test_constant_nonzero_field_padding_scales_with_declared_data_units():
    small = field_range([1e-9, 1e-9], None)
    large = field_range([1, 1], None)
    assert small == pytest.approx([v * 1e-9 for v in large], rel=1e-12, abs=0)
    assert field_range([0, 0], None) == [-1e-6, 1e-6]
    assert field_range([-5, 10], [0, 3]) == [0, 3]  # Explicit clipping is intentional.


@pytest.mark.parametrize(
    "args",
    [
        dict(entity_type="solid", field="unknown", state=1, units="Pa"),
        dict(entity_type="node", field="stress_x", state=1, units="Pa"),
        dict(entity_type="solid", field="stress_x", state=True, units="Pa"),
        dict(entity_type="solid", field="stress_x", state=1, units='Pa";exit'),
        dict(entity_type="solid", field="stress_x", state=1, units="Pa", part_ids=[True]),
        dict(entity_type="solid", field="stress_x", state=1, units="Pa", color_range=[0, float("inf")]),
        dict(entity_type="node", field="disp_x", state=1, units="mm", validity_policy="alive"),
        dict(entity_type="tshell", field="stress_x", state=1, units="Pa", validity_policy="alive"),
        dict(entity_type="solid", field="stress_x", state=1, units="Pa", validity_policy="guess"),
    ],
)
def test_bad_render_requests_never_contact_native_session(tmp_path, args):
    with pytest.raises(ValueError):
        Service(Settings(tmp_path)).render_gui_field("missing", **args)
    assert not list(tmp_path.iterdir())


def test_native_mises_verification_is_unit_scale_invariant_and_rejects_fabricated_zero():
    for scale in (1e-12, 1e-6, 1.0, 1e9):
        stress = [scale, 0, 0, 0, 0, 0]
        assert native_mises_matches(stress, scale, scale)
        assert not native_mises_matches(stress, scale, 0)
        assert not native_mises_matches(stress, scale, -scale)
    assert native_mises_matches([0] * 6, 0, 0)
    assert not native_mises_matches([0] * 6, 0, 1e-30)


def test_impossible_solid_point_is_not_silently_reported_as_default_result():
    with pytest.raises(ValueError, match="1..8"):
        SamplingSpec.native("solid", "99")


def test_element_scalar_is_not_mislabeled_as_a_shell_layer():
    assert SamplingSpec.native_fields("shell", "mid", ["thickness"]).kind == "native_element_scalar"
    with pytest.raises(ValueError, match="no layer"):
        SamplingSpec.native_fields("shell", "outer", ["thickness"])
    with pytest.raises(ValueError, match="no layer"):
        SamplingSpec.native_fields("shell", "outer", ["stress_x", "thickness"])
