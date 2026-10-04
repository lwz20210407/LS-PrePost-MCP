from types import SimpleNamespace

import pytest

from ls_prepost_mcp.field_contracts import SamplingSpec
from ls_prepost_mcp.result_availability import header_field_contract


def header(**kw):
    values = dict(
        n_nodes=8,
        n_solids=1,
        n_shells=1,
        n_thick_shells=0,
        n_beams=0,
        n_solid_layers=1,
        n_shell_tshell_layers=3,
        has_solid_stress=True,
        has_shell_tshell_stress=True,
        has_node_displacement=True,
        has_node_velocity=True,
        has_node_acceleration=False,
        has_element_strain=False,
        has_solid_internal_energy_density=False,
        has_shell_extra_variables=True,
    )
    return SimpleNamespace(**(values | kw))


def test_missing_recorded_data_is_not_accepted_as_native_zero():
    for domain, field in [("node", "accel_x"), ("solid", "strain_x"), ("solid", "internal_energy_density")]:
        sample = SamplingSpec.native_fields(domain, "mid", [field])
        with pytest.raises(ValueError, match="absent"):
            header_field_contract(header(), dict(nodes=8, elements=2), domain, field, sample)


def test_numbered_points_require_actual_recorded_layers():
    with pytest.raises(ValueError, match="recorded output count"):
        header_field_contract(
            header(), dict(nodes=8, elements=2), "shell", "stress_x", SamplingSpec.native("shell", "4")
        )
    with pytest.raises(ValueError, match="recorded output count"):
        header_field_contract(
            header(), dict(nodes=8, elements=2), "solid", "stress_x",
            SamplingSpec("native_integration_point", 2, "2")
        )
    result = header_field_contract(
        header(), dict(nodes=8, elements=2), "shell", "stress_x", SamplingSpec.native("shell", "outer")
    )
    assert result["recorded_layer_count"] == 3 and result["data_backend"] == "lsprepost"


def test_header_does_not_certify_another_live_model():
    with pytest.raises(ValueError, match="counts differ"):
        header_field_contract(
            header(), dict(nodes=9, elements=2), "solid", "stress_x", SamplingSpec.native("solid", "mid")
        )


def test_native_geometry_and_thickness_require_relevant_prerequisites():
    sample = SamplingSpec.native_fields("shell", "mid", ["thickness"])
    assert header_field_contract(header(), dict(nodes=8, elements=2), "shell", "thickness", sample)[
        "prerequisite_flags"
    ] == {"has_shell_extra_variables": True}
    with pytest.raises(ValueError, match="unsupported"):
        header_field_contract(
            header(),
            dict(nodes=8, elements=2),
            "solid",
            "area",
            SamplingSpec.native_fields("solid", "mid", ["area"]),
        )
