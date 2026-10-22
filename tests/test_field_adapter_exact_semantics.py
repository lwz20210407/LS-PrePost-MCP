"""I02 equivalence must compare semantic values, not substrings in descriptions."""
from dataclasses import replace

import pytest

from ls_prepost_mcp.core import contracts
from ls_prepost_mcp.field_contract_adapter import (
    assert_field_spec_equivalence,
    core_to_legacy_field_spec,
    is_field_spec_equivalent,
    legacy_to_core_field_spec,
)
from tests.test_field_contract_adapter import core_shell_stress_spec


def test_local_coordinate_system_id_is_not_a_substring_match():
    core = core_shell_stress_spec().model_copy(update={"frame": "local", "coordinate_system_id": 1})
    legacy = core_to_legacy_field_spec(core)
    assert is_field_spec_equivalent(core, legacy)
    wrong = replace(legacy, frame="local: coordinate_system_id=10")
    assert not is_field_spec_equivalent(core, wrong)
    with pytest.raises(AssertionError, match="coordinate system"):
        assert_field_spec_equivalence(core, wrong)


@pytest.mark.parametrize("averaging", ["nodal", "minmax", "unrecognized averaging"])
def test_no_averaging_is_not_equivalent_to_averaging_or_unknown_text(averaging):
    core = core_shell_stress_spec()
    wrong = replace(core_to_legacy_field_spec(core), averaging=averaging)
    assert not is_field_spec_equivalent(core, wrong)


@pytest.mark.parametrize("frame", ["not_global", "nonlocal", "global and material"])
def test_ambiguous_frames_cannot_be_inferred_or_equated(frame):
    core = core_shell_stress_spec()
    legacy = replace(core_to_legacy_field_spec(core), frame=frame)
    assert not is_field_spec_equivalent(core, legacy)
    with pytest.raises(ValueError, match="frame"):
        legacy_to_core_field_spec(legacy)


@pytest.mark.parametrize("averaging", ["not nodal", "not minmax", "unknown", "none and nodal"])
def test_averaging_requires_an_exact_policy_or_explicit_context(averaging):
    core = core_shell_stress_spec()
    legacy = replace(core_to_legacy_field_spec(core), averaging=averaging)
    with pytest.raises(ValueError, match="averaging"):
        legacy_to_core_field_spec(legacy)
    # Explicit resolution remains available to callers with the missing context.
    assert legacy_to_core_field_spec(legacy, averaging="none").averaging == "none"


@pytest.mark.parametrize("frame,csid", [("global", None), ("material", None), ("local", 42)])
@pytest.mark.parametrize("averaging", ["none", "nodal", "minmax"])
def test_exact_coordinate_and_averaging_policies_roundtrip(frame, csid, averaging):
    core = core_shell_stress_spec().model_copy(update={
        "frame": frame, "coordinate_system_id": csid, "averaging": averaging})
    legacy = core_to_legacy_field_spec(core)
    assert_field_spec_equivalence(core, legacy)
    restored = legacy_to_core_field_spec(legacy)
    assert (restored.frame, restored.coordinate_system_id, restored.averaging) == (frame, csid, averaging)


@pytest.mark.parametrize("components", [["xx"], ["yy", "xx"], ["xx", "yy", "zz", "xy", "zx", "yz"]])
def test_reader_whole_array_mapping_cannot_silently_drop_component_selection(components):
    core = contracts.FieldSpec.model_validate({**core_shell_stress_spec().model_dump(),
        "backend": "lasso", "components": components, "sampling": {"kind": "stored_point", "index": 1}})
    with pytest.raises(ValueError, match="component"):
        core_to_legacy_field_spec(core)


def test_part_predicate_requires_resolved_entities_and_is_not_an_id_predicate():
    core = core_shell_stress_spec().model_copy(update={"selector": contracts.Selector(
        entity_type="shell", predicate=contracts.PartSelection(kind="parts", ids=[101]), validity="alive")})
    with pytest.raises(ValueError, match="resolved entity IDs"):
        core_to_legacy_field_spec(core)
    resolved = core_to_legacy_field_spec(core, resolved_entity_ids=[101])
    assert resolved.selection.entity_ids == (101,)
    # A coincidentally equal Part ID and element ID do not establish membership.
    assert not is_field_spec_equivalent(core, resolved)
