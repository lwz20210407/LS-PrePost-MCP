"""Tests for field contract adapter bridging core.contracts.FieldSpec and field_contracts.FieldSpec.

Covers I02 / M2 gap closure:
- Request vs metadata distinction ("同名不同义")
- Preservation of backend, user IDs, 1-based states, units, frame, averaging, validity
- Segregation of native layer / integration point from reader stored point
- Rejection of cross-backend sampling equivalence
- Explicit rejection of missing entity and state resolution contexts
- KI-049 rejection of unverified native solid points 2..8
- Equivalence assertions and round-trip conversions
"""

import pytest
from pydantic import ValidationError

from ls_prepost_mcp.core import contracts as core_contracts
from ls_prepost_mcp.field_contract_adapter import (
    FieldContractAdapter,
    assert_field_spec_equivalence,
    core_to_legacy_field_spec,
    describe_field_spec_mapping,
    is_field_spec_equivalent,
    legacy_to_core_field_spec,
)
from ls_prepost_mcp.field_contracts import (
    FieldSpec as LegacyFieldSpec,
)
from ls_prepost_mcp.field_contracts import (
    ResultSelection,
    SamplingSpec,
)

# --- Fixtures ---


def core_shell_stress_spec(
    layer: str = "outer",
    backend: str = "lsprepost",
    validity: str = "alive",
    ids: list[int] | None = None,
    states: list[int] | None = None,
) -> core_contracts.FieldSpec:
    return core_contracts.FieldSpec(
        quantity="stress",
        components=["xx", "yy", "zz", "xy", "yz", "zx"],
        units="MPa",
        backend=backend,  # type: ignore[arg-type]
        selector=core_contracts.Selector(
            entity_type="shell",
            predicate=core_contracts.IdSelection(kind="ids", ids=ids or [101, 102]),
            configuration="reference",
            validity=validity,  # type: ignore[arg-type]
        ),
        at=core_contracts.StateIndices(kind="states", indices=states or [1, 2]),
        sampling=core_contracts.NativeLayer(kind="native_layer", layer=layer),  # type: ignore[arg-type]
        frame="global",
        averaging="none",
    )


def core_solid_stress_spec(
    point_index: int = 1,
    backend: str = "lsprepost",
    ids: list[int] | None = None,
    states: list[int] | None = None,
) -> core_contracts.FieldSpec:
    sampling: core_contracts.Sampling
    if point_index == 0:
        sampling = core_contracts.NativeDefault(kind="native_default")
    else:
        sampling = core_contracts.NativePoint(kind="native_point", index=point_index)

    return core_contracts.FieldSpec(
        quantity="stress",
        components=["xx", "yy", "zz", "xy", "yz", "zx"],
        units="MPa",
        backend=backend,  # type: ignore[arg-type]
        selector=core_contracts.Selector(
            entity_type="solid",
            predicate=core_contracts.IdSelection(kind="ids", ids=ids or [501]),
            configuration="reference",
            validity="all",
        ),
        at=core_contracts.StateIndices(kind="states", indices=states or [1]),
        sampling=sampling,
        frame="global",
        averaging="none",
    )


def core_node_disp_spec(
    ids: list[int] | None = None,
    states: list[int] | None = None,
) -> core_contracts.FieldSpec:
    return core_contracts.FieldSpec(
        quantity="displacement",
        components=["x", "y", "z"],
        units="mm",
        backend="lsprepost",
        selector=core_contracts.Selector(
            entity_type="node",
            predicate=core_contracts.IdSelection(kind="ids", ids=ids or [1, 2, 3]),
            configuration="reference",
            validity="all",
        ),
        at=core_contracts.StateIndices(kind="states", indices=states or [1, 5]),
        sampling=core_contracts.Unlayered(kind="unlayered"),
        frame="global",
        averaging="none",
    )


def core_reader_stress_spec(
    stored_point: int = 1,
    backend: str = "lasso",
    ids: list[int] | None = None,
    states: list[int] | None = None,
) -> core_contracts.FieldSpec:
    return core_contracts.FieldSpec(
        quantity="stress",
        components=["xx", "yy", "zz", "xy", "yz", "zx"],
        units="MPa",
        backend=backend,  # type: ignore[arg-type]
        selector=core_contracts.Selector(
            entity_type="shell",
            predicate=core_contracts.IdSelection(kind="ids", ids=ids or [101]),
            configuration="reference",
            validity="alive",
        ),
        at=core_contracts.StateIndices(kind="states", indices=states or [1]),
        sampling=core_contracts.StoredPoint(kind="stored_point", index=stored_point),
        frame="global",
        averaging="none",
    )


# --- Core to Legacy Tests ---


def test_core_to_legacy_shell_native_layer():
    core_spec = core_shell_stress_spec(layer="outer", ids=[101, 102], states=[1, 2])
    legacy_spec = core_to_legacy_field_spec(core_spec)

    assert legacy_spec.backend == "lsprepost"
    assert legacy_spec.units == "MPa"
    assert legacy_spec.selection.domain == "shell"
    assert legacy_spec.selection.entity_ids == (101, 102)
    assert legacy_spec.selection.states == (1, 2)
    assert legacy_spec.sampling.kind == "native_shell_layer"
    assert legacy_spec.sampling.native_selector == "OUTER"
    assert legacy_spec.sampling.value == "outer"
    assert legacy_spec.fields == (
        "stress_x", "stress_y", "stress_z", "stress_xy", "stress_yz", "stress_zx"
    )
    assert "physical deletion filtering" in legacy_spec.validity.lower()


def test_core_to_legacy_solid_native_default_and_point_1():
    # Native default
    core_default = core_solid_stress_spec(point_index=0, ids=[501], states=[1])
    legacy_default = core_to_legacy_field_spec(core_default)
    assert legacy_default.sampling.kind == "native_default"
    assert legacy_default.sampling.native_selector == "0"

    # Native point 1
    core_p1 = core_solid_stress_spec(point_index=1, ids=[501], states=[1])
    legacy_p1 = core_to_legacy_field_spec(core_p1)
    assert legacy_p1.sampling.kind == "native_integration_point"
    assert legacy_p1.sampling.native_selector == "1"


def test_core_to_legacy_nodal_displacement():
    core_spec = core_node_disp_spec(ids=[10, 20], states=[3])
    legacy_spec = core_to_legacy_field_spec(core_spec)

    assert legacy_spec.backend == "lsprepost"
    assert legacy_spec.units == "mm"
    assert legacy_spec.selection.domain == "node"
    assert legacy_spec.selection.entity_ids == (10, 20)
    assert legacy_spec.selection.states == (3,)
    assert legacy_spec.sampling.kind == "not_applicable"
    assert legacy_spec.sampling.native_selector == "0"
    assert legacy_spec.fields == ("disp_x", "disp_y", "disp_z")


def test_core_to_legacy_reader_stored_point():
    core_spec = core_reader_stress_spec(stored_point=2, backend="lasso", ids=[101], states=[1])
    legacy_spec = core_to_legacy_field_spec(core_spec)

    assert legacy_spec.backend == "lasso"
    assert legacy_spec.sampling.kind == "stored_integration_point"
    assert legacy_spec.sampling.value == (2,)
    assert legacy_spec.sampling.native_selector is None
    assert legacy_spec.fields == ("element_shell_stress",)


def test_core_to_legacy_local_frame_preserves_csid():
    core_spec = core_contracts.FieldSpec(
        quantity="displacement",
        components=["x", "y", "z"],
        units="mm",
        backend="lsprepost",
        selector=core_contracts.Selector(
            entity_type="node",
            predicate=core_contracts.IdSelection(kind="ids", ids=[1]),
            configuration="reference",
        ),
        at=core_contracts.StateIndices(kind="states", indices=[1]),
        sampling=core_contracts.Unlayered(kind="unlayered"),
        frame="local",
        coordinate_system_id=42,
        averaging="none",
    )
    legacy_spec = core_to_legacy_field_spec(core_spec)
    assert "local" in legacy_spec.frame.lower()
    assert "42" in legacy_spec.frame


# --- Segregation and Negative Rejection Tests ---


def test_never_equate_native_layer_with_reader_stored_point():
    """Reader stored points must never be converted or equated to native layers."""
    core_reader = core_reader_stress_spec(stored_point=1, backend="lasso")
    legacy_reader = core_to_legacy_field_spec(core_reader)

    core_native = core_shell_stress_spec(layer="mid", backend="lsprepost")
    legacy_native = core_to_legacy_field_spec(core_native)

    # Cross-backend equivalence is strictly forbidden
    assert legacy_reader.sampling.describe()["cross_backend_equivalence"] == "not_inferred"
    assert legacy_native.sampling.describe()["cross_backend_equivalence"] == "not_inferred"

    assert not is_field_spec_equivalent(core_reader, legacy_native)
    assert not is_field_spec_equivalent(core_native, legacy_reader)

    with pytest.raises(AssertionError, match="Backend mismatch"):
        assert_field_spec_equivalence(core_reader, legacy_native)


def test_solid_native_points_2_to_8_rejected_by_scl_guard():
    """LS-PrePost 4.13 SCL bug (KI-049): solid integration points 2..8 must be rejected."""
    for pt in (2, 5, 8):
        core_spec = core_solid_stress_spec(point_index=pt, ids=[501], states=[1])
        with pytest.raises(ValueError, match="can return point 1"):
            core_to_legacy_field_spec(core_spec)


def test_cross_backend_sampling_rejected():
    """Native sampling on reader backends or stored points on native backend must fail."""
    # StoredPoint cannot be passed with lsprepost backend
    with pytest.raises(ValidationError):
        core_contracts.FieldSpec(
            quantity="stress",
            components=["xx"],
            units="MPa",
            backend="lsprepost",
            selector=core_contracts.Selector(
                entity_type="shell",
                predicate=core_contracts.IdSelection(kind="ids", ids=[1]),
            ),
            at=core_contracts.StateIndices(kind="states", indices=[1]),
            sampling=core_contracts.StoredPoint(kind="stored_point", index=1),
            frame="global",
            averaging="none",
        )

    # NativeLayer cannot be passed with lasso backend
    with pytest.raises(ValidationError):
        core_contracts.FieldSpec(
            quantity="stress",
            components=["xx"],
            units="MPa",
            backend="lasso",
            selector=core_contracts.Selector(
                entity_type="shell",
                predicate=core_contracts.IdSelection(kind="ids", ids=[1]),
            ),
            at=core_contracts.StateIndices(kind="states", indices=[1]),
            sampling=core_contracts.NativeLayer(kind="native_layer", layer="mid"),
            frame="global",
            averaging="none",
        )


def test_missing_entity_resolution_context_rejected():
    """Symbolic/geometric predicates without explicit resolved_entity_ids must raise ValueError."""
    # BoxSelection without resolved IDs
    core_box = core_contracts.FieldSpec(
        quantity="displacement",
        components=["x", "y", "z"],
        units="mm",
        backend="lsprepost",
        selector=core_contracts.Selector(
            entity_type="node",
            predicate=core_contracts.BoxSelection(
                kind="box", minimum=[0.0, 0.0, 0.0], maximum=[10.0, 10.0, 10.0]
            ),
        ),
        at=core_contracts.StateIndices(kind="states", indices=[1]),
        sampling=core_contracts.Unlayered(kind="unlayered"),
        frame="global",
        averaging="none",
    )
    with pytest.raises(ValueError, match="requires resolved entity IDs context"):
        core_to_legacy_field_spec(core_box)

    # Supply resolved IDs -> succeeds
    legacy_resolved = core_to_legacy_field_spec(core_box, resolved_entity_ids=[101, 102])
    assert legacy_resolved.selection.entity_ids == (101, 102)


def test_missing_temporal_resolution_context_rejected():
    """PhysicalTime without explicit resolved_states must raise ValueError."""
    core_time = core_contracts.FieldSpec(
        quantity="displacement",
        components=["x", "y", "z"],
        units="mm",
        backend="lsprepost",
        selector=core_contracts.Selector(
            entity_type="node",
            predicate=core_contracts.IdSelection(kind="ids", ids=[1]),
        ),
        at=core_contracts.PhysicalTime(kind="time", value=12.5, units="ms", match="nearest"),
        sampling=core_contracts.Unlayered(kind="unlayered"),
        frame="global",
        averaging="none",
    )
    with pytest.raises(ValueError, match="requires state-index resolution context"):
        core_to_legacy_field_spec(core_time)

    # Supply resolved states -> succeeds
    legacy_resolved = core_to_legacy_field_spec(core_time, resolved_states=[25])
    assert legacy_resolved.selection.states == (25,)


def test_no_selection_on_non_global_domain_rejected():
    """NoSelection on non-global domain cannot be mapped to ResultSelection."""
    core_none = core_contracts.FieldSpec(
        quantity="displacement",
        components=["x", "y", "z"],
        units="mm",
        backend="lsprepost",
        selector=core_contracts.Selector(
            entity_type="node",
            predicate=core_contracts.NoSelection(kind="none"),
        ),
        at=core_contracts.StateIndices(kind="states", indices=[1]),
        sampling=core_contracts.Unlayered(kind="unlayered"),
        frame="global",
        averaging="none",
    )
    with pytest.raises(ValueError, match="Cannot adapt NoSelection to non-global"):
        core_to_legacy_field_spec(core_none)


# --- Legacy to Core Tests ---


def test_legacy_to_core_shell_native_layer():
    legacy_spec = LegacyFieldSpec(
        backend="lsprepost",
        fields=("stress_x", "stress_y", "stress_z", "stress_xy", "stress_yz", "stress_zx"),
        units="MPa",
        selection=ResultSelection("shell", [101, 102], [1, 2]),
        sampling=SamplingSpec.native("shell", "inner"),
        frame="global",
        averaging="none",
        validity="Physical deletion filtering: LASSO2.0.4 MDLOPT2 table; positive material code=present,0=deleted; ID/state aligned",
    )
    core_spec = legacy_to_core_field_spec(legacy_spec)

    assert core_spec.backend == "lsprepost"
    assert core_spec.units == "MPa"
    assert core_spec.quantity == "stress"
    assert core_spec.selector.entity_type == "shell"
    assert isinstance(core_spec.selector.predicate, core_contracts.IdSelection)
    assert core_spec.selector.predicate.ids == (101, 102)
    assert core_spec.selector.validity == "alive"
    assert isinstance(core_spec.sampling, core_contracts.NativeLayer)
    assert core_spec.sampling.layer == "inner"
    assert core_spec.at.indices == (1, 2)


def test_legacy_to_core_reader_stored_point():
    legacy_spec = LegacyFieldSpec(
        backend="lasso",
        fields=("element_shell_stress",),
        units="MPa",
        selection=ResultSelection("shell", [201], [1]),
        sampling=SamplingSpec.stored([3], stress=True),
        frame="as_stored; no coordinate transformation",
        averaging="none",
        validity="Raw stored population; physical deletion filtering not requested; extrema are not alive-only",
    )
    core_spec = legacy_to_core_field_spec(legacy_spec)

    assert core_spec.backend == "lasso"
    assert core_spec.units == "MPa"
    assert core_spec.selector.validity == "all"
    assert isinstance(core_spec.sampling, core_contracts.StoredPoint)
    assert core_spec.sampling.index == 3


def test_legacy_to_core_node_displacement():
    legacy_spec = LegacyFieldSpec(
        backend="lsprepost",
        fields=("disp_x", "disp_y", "disp_z"),
        units="mm",
        selection=ResultSelection("node", [1, 2, 3], [1]),
        sampling=SamplingSpec("not_applicable", "nodal", "0"),
        frame="global",
        averaging="none",
        validity="all",
    )
    core_spec = legacy_to_core_field_spec(legacy_spec)

    assert core_spec.quantity == "displacement"
    assert core_spec.components == ("x", "y", "z")
    assert isinstance(core_spec.sampling, core_contracts.Unlayered)


# --- Equivalence and Round-Trip Tests ---


def test_equivalence_and_roundtrip_shell_stress():
    core_orig = core_shell_stress_spec(layer="outer", ids=[101, 102], states=[1, 2])
    legacy_adapted = core_to_legacy_field_spec(core_orig)

    # Verify equivalence
    assert is_field_spec_equivalent(core_orig, legacy_adapted)
    assert_field_spec_equivalence(core_orig, legacy_adapted)

    # Roundtrip back to core
    core_roundtrip = legacy_to_core_field_spec(
        legacy_adapted,
        quantity=core_orig.quantity,
        components=core_orig.components,
    )
    assert core_roundtrip == core_orig


def test_equivalence_and_roundtrip_reader_stored_point():
    core_orig = core_reader_stress_spec(stored_point=1, backend="lasso", ids=[50], states=[1, 3])
    legacy_adapted = core_to_legacy_field_spec(core_orig)

    assert is_field_spec_equivalent(core_orig, legacy_adapted)
    assert_field_spec_equivalence(core_orig, legacy_adapted)

    core_roundtrip = legacy_to_core_field_spec(
        legacy_adapted,
        quantity=core_orig.quantity,
        components=core_orig.components,
    )
    assert core_roundtrip == core_orig


def test_describe_field_spec_mapping_audit_dict():
    core_spec = core_shell_stress_spec(layer="mid", ids=[101], states=[1])
    legacy_spec = core_to_legacy_field_spec(core_spec)

    audit = describe_field_spec_mapping(core_spec, legacy_spec)
    assert audit["equivalent"] is True
    assert "同名不同义" in audit["semantic_distinction"] or "declarative" in audit["semantic_distinction"]
    assert audit["backend"]["match"] is True
    assert audit["units"]["match"] is True
    assert audit["domain"]["match"] is True
    assert audit["sampling"]["cross_backend_equivalence"] == "not_inferred"


# --- Stateful FieldContractAdapter Tests ---


def test_stateful_adapter_with_resolvers():
    # Configure adapter with entity resolver (for BoxSelection) and state resolver (for PhysicalTime)
    adapter = FieldContractAdapter(
        entity_resolver=lambda selector: [1001, 1002, 1003],
        state_resolver=lambda time_spec: [1, 2, 3],
    )

    core_spec = core_contracts.FieldSpec(
        quantity="displacement",
        components=["x", "y", "z"],
        units="mm",
        backend="lsprepost",
        selector=core_contracts.Selector(
            entity_type="node",
            predicate=core_contracts.BoxSelection(
                kind="box", minimum=[0.0, 0.0, 0.0], maximum=[1.0, 1.0, 1.0]
            ),
        ),
        at=core_contracts.PhysicalTime(kind="time", value=5.0, units="ms"),
        sampling=core_contracts.Unlayered(kind="unlayered"),
        frame="global",
        averaging="none",
    )

    legacy_spec = adapter.to_legacy(core_spec)
    assert legacy_spec.selection.entity_ids == (1001, 1002, 1003)
    assert legacy_spec.selection.states == (1, 2, 3)
    assert legacy_spec.fields == ("disp_x", "disp_y", "disp_z")
