"""Adapter and equivalence verification between core.contracts.FieldSpec and legacy field_contracts.FieldSpec.

I02 / M2 semantic bridge:
`core.contracts.FieldSpec` defines high-level domain requests (declarative intent,
structured entity selectors, temporal specifications, and backend targets).
`field_contracts.FieldSpec` defines concrete result requests and provenance descriptions
(executable field keys, resolved user IDs and 1-based state integers, and backend-specific
sampling parameters).

Although both contracts share attribute names (backend, units, sampling, frame,
averaging, validity), they are '同名不同义' (same name, distinct scope and semantics).
The adapter bridges them with explicit preservation of:
- backend target ('lsprepost', 'lasso', 'lsreader', 'dpf')
- real user entity IDs and 1-based state indices (without implicit type coercion)
- units declaration (preserved verbatim, without inference or implicit conversion)
- sampling semantics (native SCL layer/point vs reader stored point strictly segregated;
  never equated across backends)
- coordinate system / frame context
- averaging and physical validity semantics
- explicit rejection of lossy mappings and missing resolution contexts
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Any, Literal

from .core import contracts as core_contracts
from .field_contracts import (
    ELEMENT_SCALARS,
    ResultSelection,
    SamplingSpec,
)
from .field_contracts import (
    FieldSpec as LegacyFieldSpec,
)
from .native_results import ELEMENT_FIELDS, NODE_FIELDS
from .result_validity import validity_scope

# Standard mapping dictionaries from (backend, domain, quantity, component) -> legacy field name
NATIVE_STRESS_MAP = {
    "xx": "stress_x",
    "yy": "stress_y",
    "zz": "stress_z",
    "xy": "stress_xy",
    "yz": "stress_yz",
    "zx": "stress_zx",
    "x": "stress_x",
    "y": "stress_y",
    "z": "stress_z",
    "von_mises": "von_mises",
    "effective_plastic_strain": "effective_plastic_strain",
    "1stprincipal": "stress_1stprincipal",
    "2ndprincipal": "stress_2ndprincipal",
    "3rdprincipal": "stress_3rdprincipal",
}

NATIVE_STRAIN_MAP = {
    "xx": "strain_x",
    "yy": "strain_y",
    "zz": "strain_z",
    "xy": "strain_xy",
    "yz": "strain_yz",
    "zx": "strain_zx",
    "x": "strain_x",
    "y": "strain_y",
    "z": "strain_z",
}

NATIVE_NODE_MAP = {
    ("displacement", "x"): "disp_x",
    ("displacement", "y"): "disp_y",
    ("displacement", "z"): "disp_z",
    ("displacement", "magnitude"): "disp_magnitude",
    ("disp", "x"): "disp_x",
    ("disp", "y"): "disp_y",
    ("disp", "z"): "disp_z",
    ("disp", "magnitude"): "disp_magnitude",
    ("velocity", "x"): "velo_x",
    ("velocity", "y"): "velo_y",
    ("velocity", "z"): "velo_z",
    ("velo", "x"): "velo_x",
    ("velo", "y"): "velo_y",
    ("velo", "z"): "velo_z",
    ("acceleration", "x"): "accel_x",
    ("acceleration", "y"): "accel_y",
    ("acceleration", "z"): "accel_z",
    ("accel", "x"): "accel_x",
    ("accel", "y"): "accel_y",
    ("accel", "z"): "accel_z",
    ("coordinates", "x"): "state_node_x",
    ("coordinates", "y"): "state_node_y",
    ("coordinates", "z"): "state_node_z",
    ("state_node", "x"): "state_node_x",
    ("state_node", "y"): "state_node_y",
    ("state_node", "z"): "state_node_z",
}


def _map_core_to_legacy_fields(
    backend: str,
    domain: str,
    quantity: str,
    components: Sequence[str],
) -> tuple[str, ...]:
    """Map core quantity and components to backend-specific legacy field names."""
    q_lower = quantity.lower()
    mapped: list[str] = []

    if backend == "lsprepost":
        if domain == "node":
            for c in components:
                key = (q_lower, c.lower())
                if key in NATIVE_NODE_MAP:
                    mapped.append(NATIVE_NODE_MAP[key])
                elif c in NODE_FIELDS:
                    mapped.append(c)
                else:
                    raise ValueError(
                        f"Unknown or unmappable component '{c}' for quantity '{quantity}' on lsprepost node domain"
                    )
        elif q_lower in ("stress", "stress_tensor"):
            for c in components:
                c_clean = c.lower()
                if c_clean in NATIVE_STRESS_MAP:
                    mapped.append(NATIVE_STRESS_MAP[c_clean])
                elif c in ELEMENT_FIELDS and (c.startswith("stress_") or c in ("von_mises", "effective_plastic_strain")):
                    mapped.append(c)
                else:
                    raise ValueError(
                        f"Unknown or unmappable stress component '{c}' for lsprepost backend"
                    )
        elif q_lower in ("strain", "strain_tensor"):
            for c in components:
                c_clean = c.lower()
                if c_clean in NATIVE_STRAIN_MAP:
                    mapped.append(NATIVE_STRAIN_MAP[c_clean])
                elif c in ELEMENT_FIELDS and c.startswith("strain_"):
                    mapped.append(c)
                else:
                    raise ValueError(
                        f"Unknown or unmappable strain component '{c}' for lsprepost backend"
                    )
        elif q_lower in ELEMENT_SCALARS:
            for c in components:
                if c.lower() == q_lower:
                    mapped.append(q_lower)
                else:
                    raise ValueError(
                        f"Element scalar '{quantity}' does not match component '{c}'"
                    )
        else:
            for c in components:
                if domain == "node" and c in NODE_FIELDS:
                    mapped.append(c)
                elif domain != "node" and c in ELEMENT_FIELDS:
                    mapped.append(c)
                else:
                    raise ValueError(
                        f"Unknown or unmappable field/component '{c}' for quantity '{quantity}' on lsprepost backend"
                    )
    elif backend in ("lasso", "lsreader"):
        if q_lower in ("stress", "stress_tensor"):
            elem_type = domain if domain in ("shell", "solid", "tshell", "beam") else "shell"
            mapped.append(f"element_{elem_type}_stress")
        elif q_lower in ("displacement", "disp"):
            mapped.append("node_displacement")
        elif q_lower in ("velocity", "velo"):
            mapped.append("node_velocity")
        elif q_lower in ("acceleration", "accel"):
            mapped.append("node_acceleration")
        else:
            mapped.extend(components)
    elif backend == "dpf":
        mapped.extend(components)
    else:
        mapped.extend(components)

    return tuple(mapped)


def _infer_core_quantity_and_components(
    legacy_fields: Sequence[str],
    domain: str,
) -> tuple[str, tuple[str, ...]]:
    """Infer semantic quantity and components from legacy field names."""
    if not legacy_fields:
        raise ValueError("Cannot infer quantity from empty legacy fields")

    first = legacy_fields[0]

    # Stress tensor components
    if all(f.startswith("stress_") or f in ("von_mises", "effective_plastic_strain") for f in legacy_fields):
        comps: list[str] = []
        for f in legacy_fields:
            if f.startswith("stress_"):
                suffix = f[len("stress_"):]
                if suffix in ("x", "y", "z"):
                    comps.append(suffix + suffix)
                else:
                    comps.append(suffix)
            else:
                comps.append(f)
        return "stress", tuple(comps)

    # Strain tensor components
    if all(f.startswith("strain_") for f in legacy_fields):
        comps = []
        for f in legacy_fields:
            suffix = f[len("strain_"):]
            if suffix in ("x", "y", "z"):
                comps.append(suffix + suffix)
            else:
                comps.append(suffix)
        return "strain", tuple(comps)

    # Nodal displacement
    if all(f.startswith("disp_") for f in legacy_fields) or first == "node_displacement":
        if first == "node_displacement":
            return "displacement", ("x", "y", "z")
        comps = [f[len("disp_"):] for f in legacy_fields]
        return "displacement", tuple(comps)

    # Nodal velocity
    if all(f.startswith("velo_") for f in legacy_fields) or first == "node_velocity":
        if first == "node_velocity":
            return "velocity", ("x", "y", "z")
        comps = [f[len("velo_"):] for f in legacy_fields]
        return "velocity", tuple(comps)

    # Nodal acceleration
    if all(f.startswith("accel_") for f in legacy_fields) or first == "node_acceleration":
        if first == "node_acceleration":
            return "acceleration", ("x", "y", "z")
        comps = [f[len("accel_"):] for f in legacy_fields]
        return "acceleration", tuple(comps)

    # Reader element stress
    if first.startswith("element_") and first.endswith("_stress"):
        return "stress", ("xx", "yy", "zz", "xy", "yz", "zx")

    # Element scalars
    if first in ELEMENT_SCALARS:
        return first, (first,)

    if len(legacy_fields) == 1:
        return first, (first,)

    return "field", tuple(legacy_fields)


def core_to_legacy_field_spec(
    core_spec: core_contracts.FieldSpec,
    *,
    resolved_entity_ids: Sequence[int] | None = None,
    resolved_states: Sequence[int] | None = None,
    field_mapping: (
        Sequence[str] | dict[str, str] | Callable[[str, Sequence[str]], Sequence[str]] | None
    ) = None,
    frame_description: str | None = None,
    averaging_description: str | None = None,
    validity_policy: str | None = None,
    transformations: Sequence[str] = (),
) -> LegacyFieldSpec:
    """Adapt a domain core.contracts.FieldSpec to an executable legacy field_contracts.FieldSpec.

    Preserves backend, user entity IDs, states, sampling, units, frame, averaging, and validity.
    Raises ValueError when lossy mappings or missing resolution contexts are encountered.
    """
    backend = core_spec.backend
    domain = core_spec.selector.entity_type

    # 1. Resolve Entity IDs
    if domain == "global":
        entity_ids: tuple[int, ...] = ()
    else:
        if resolved_entity_ids is not None:
            entity_ids = tuple(resolved_entity_ids)
        elif isinstance(core_spec.selector.predicate, core_contracts.IdSelection):
            entity_ids = core_spec.selector.predicate.ids
        elif isinstance(core_spec.selector.predicate, core_contracts.NoSelection):
            raise ValueError(
                f"Cannot adapt NoSelection to non-global ResultSelection for domain '{domain}': "
                f"explicit non-empty entity IDs are required."
            )
        else:
            predicate_kind = getattr(
                core_spec.selector.predicate, "kind", type(core_spec.selector.predicate).__name__
            )
            raise ValueError(
                f"Selector predicate '{predicate_kind}' requires resolved entity IDs context before "
                f"adapting to ResultSelection. Pass 'resolved_entity_ids' to supply explicit IDs."
            )

    # 2. Resolve States
    if resolved_states is not None:
        states: tuple[int, ...] = tuple(resolved_states)
    elif isinstance(core_spec.at, core_contracts.StateIndices):
        states = core_spec.at.indices
    elif isinstance(core_spec.at, core_contracts.PhysicalTime):
        raise ValueError(
            f"PhysicalTime (value={core_spec.at.value} {core_spec.at.units}, match='{core_spec.at.match}') "
            f"requires state-index resolution context before adapting to ResultSelection. "
            f"Pass 'resolved_states' to supply 1-based state indices."
        )
    else:
        raise ValueError(f"Unsupported temporal specification: {type(core_spec.at).__name__}")

    # Build ResultSelection
    selection = ResultSelection(domain, entity_ids, states)

    # 3. Resolve Legacy Fields
    if field_mapping is not None:
        if callable(field_mapping):
            fields = tuple(field_mapping(core_spec.quantity, core_spec.components))
        elif isinstance(field_mapping, dict):
            fields = tuple(field_mapping.get(c, c) for c in core_spec.components)
        elif isinstance(field_mapping, (list, tuple)):
            fields = tuple(field_mapping)
        else:
            raise TypeError("field_mapping must be a callable, dict, or sequence of field names")
    else:
        fields = _map_core_to_legacy_fields(backend, domain, core_spec.quantity, core_spec.components)

    # 4. Resolve Sampling
    sampling_spec: SamplingSpec
    if isinstance(core_spec.sampling, core_contracts.Unlayered):
        if domain == "node":
            sampling_spec = SamplingSpec("not_applicable", "nodal", "0")
        elif backend == "dpf":
            location = "Nodal" if domain == "node" else "Elemental" if domain in ("element", "beam") else "TimeFreq_steps"
            sampling_spec = SamplingSpec("dpf_native_location", location)
        else:
            raise ValueError(
                f"Unlayered sampling for domain '{domain}' on backend '{backend}' cannot be mapped to "
                f"legacy SamplingSpec without explicit layer or location context."
            )
    elif isinstance(core_spec.sampling, core_contracts.NativeDefault):
        if backend != "lsprepost":
            raise ValueError(
                f"NativeDefault sampling requires backend 'lsprepost', got '{backend}'. "
                f"Reader slots cannot be treated as native selectors."
            )
        if domain == "solid":
            sampling_spec = SamplingSpec("native_default", "solid_default", "0")
        elif set(fields) <= ELEMENT_SCALARS:
            sampling_spec = SamplingSpec("native_element_scalar", "element", "0")
        else:
            raise ValueError(
                f"NativeDefault sampling is only applicable to solid domain or element scalars, "
                f"got domain '{domain}' with fields {fields}."
            )
    elif isinstance(core_spec.sampling, core_contracts.NativeLayer):
        if backend != "lsprepost":
            raise ValueError(
                f"NativeLayer sampling requires backend 'lsprepost', got '{backend}'. "
                f"Native layer selectors cannot be treated as reader slots."
            )
        if domain not in ("shell", "tshell"):
            raise ValueError(f"NativeLayer applies only to shell/tshell, got domain '{domain}'.")
        sampling_spec = SamplingSpec.native(domain, core_spec.sampling.layer)
    elif isinstance(core_spec.sampling, core_contracts.NativePoint):
        if backend != "lsprepost":
            raise ValueError(
                f"NativePoint sampling requires backend 'lsprepost', got '{backend}'. "
                f"Native layer selectors cannot be treated as reader slots."
            )
        # Note: SamplingSpec.native enforces solid point 2..8 unverified rejection (KI-049)
        sampling_spec = SamplingSpec.native(domain, str(core_spec.sampling.index))
    elif isinstance(core_spec.sampling, core_contracts.StoredPoint):
        if backend == "lsprepost":
            raise ValueError(
                "StoredPoint sampling cannot be used with backend 'lsprepost'. "
                "Stored reader slots cannot be treated as native sampling selectors."
            )
        sampling_spec = SamplingSpec.stored([core_spec.sampling.index], stress=True)
    else:
        raise ValueError(f"Unsupported core sampling kind: {type(core_spec.sampling).__name__}")

    # 5. Resolve Frame
    if frame_description is not None:
        frame = frame_description
    elif core_spec.frame == "global":
        frame = "global"
    elif core_spec.frame == "material":
        frame = "material"
    elif core_spec.frame == "local":
        frame = f"local: coordinate_system_id={core_spec.coordinate_system_id}"
    else:
        frame = core_spec.frame

    # 6. Resolve Averaging
    if averaging_description is not None:
        averaging = averaging_description
    else:
        averaging = core_spec.averaging

    # 7. Resolve Validity
    if validity_policy is not None:
        validity = validity_scope(validity_policy)
    elif core_spec.selector.validity == "alive":
        validity = validity_scope("alive")
    elif core_spec.selector.validity == "all":
        validity = validity_scope("raw")
    else:
        validity = core_spec.selector.validity

    # 8. Resolve Transformations
    resolved_transformations = tuple(transformations)
    if not resolved_transformations and backend in ("lasso", "lsreader"):
        if core_spec.quantity in ("displacement", "disp"):
            resolved_transformations = ("state_coordinates_minus_reference_nodes",)

    return LegacyFieldSpec(
        backend=backend,
        fields=fields,
        units=core_spec.units,
        selection=selection,
        sampling=sampling_spec,
        frame=frame,
        averaging=averaging,
        validity=validity,
        transformations=resolved_transformations,
    )


def legacy_to_core_field_spec(
    legacy_spec: LegacyFieldSpec,
    *,
    quantity: str | None = None,
    components: Sequence[str] | None = None,
    configuration: Literal["reference", "deformed"] = "reference",
    config_state: int | None = None,
    coordinate_system_id: int | None = None,
    frame: Literal["global", "material", "local"] | None = None,
    averaging: Literal["none", "minmax", "nodal"] | None = None,
    validity: Literal["all", "alive", "deleted"] | None = None,
    allow_unmapped_transformations: bool = True,
) -> core_contracts.FieldSpec:
    """Adapt a concrete legacy field_contracts.FieldSpec back to a domain core.contracts.FieldSpec.

    Preserves backend, IDs, states, sampling, and units.
    Raises ValueError when lossy mappings or unsupported legacy structures are encountered.
    """
    backend = legacy_spec.backend
    if backend not in ("lsprepost", "lasso", "lsreader", "dpf"):
        raise ValueError(f"Unknown backend '{backend}'")

    domain = legacy_spec.selection.domain

    # Check unmapped transformations
    if not allow_unmapped_transformations and legacy_spec.transformations:
        raise ValueError(
            f"Legacy FieldSpec carries transformations {legacy_spec.transformations} "
            f"not directly representable in core.contracts.FieldSpec."
        )

    # 1. Infer / Validate Quantity and Components
    if quantity is not None and components is not None:
        resolved_quantity = quantity
        resolved_components = tuple(components)
    else:
        inferred_q, inferred_c = _infer_core_quantity_and_components(legacy_spec.fields, domain)
        resolved_quantity = quantity if quantity is not None else inferred_q
        resolved_components = tuple(components) if components is not None else inferred_c

    # 2. Build Selector Predicate
    predicate: core_contracts.SelectionPredicate
    if domain == "global":
        predicate = core_contracts.AllSelection(kind="all")
    else:
        predicate = core_contracts.IdSelection(kind="ids", ids=legacy_spec.selection.entity_ids)

    # Determine validity
    if validity is not None:
        validity_val = validity
    else:
        val_lower = legacy_spec.validity.lower()
        if "deleted only" in val_lower or "deleted elements only" in val_lower or val_lower == "deleted":
            validity_val = "deleted"
        elif (
            "raw stored population" in val_lower
            or "not requested" in val_lower
            or val_lower in ("all", "raw")
            or "no explicit alive/deletion mask" in val_lower
        ):
            validity_val = "all"
        elif (
            "positive material code=present" in val_lower
            or "physical deletion filtering" in val_lower
            or val_lower == "alive"
        ):
            validity_val = "alive"
        else:
            raise ValueError(
                f"Unrecognized legacy validity scope '{legacy_spec.validity}'; "
                f"pass explicit 'validity=' or use recognized validity policy."
            )

    # Deformed vs reference coordinate configuration
    if configuration == "deformed" and config_state is None:
        if legacy_spec.selection.states:
            config_state = legacy_spec.selection.states[0]
        else:
            raise ValueError("Deformed configuration requires an explicit 1-based state index.")
    elif configuration == "reference":
        config_state = None

    selector = core_contracts.Selector(
        entity_type=domain,
        predicate=predicate,
        configuration=configuration,
        state=config_state,
        validity=validity_val,
    )

    # 3. Build Temporal Specification
    at = core_contracts.StateIndices(kind="states", indices=legacy_spec.selection.states)

    # 4. Map Sampling
    sampling: core_contracts.Sampling
    lsamp = legacy_spec.sampling
    if lsamp.kind == "not_applicable":
        sampling = core_contracts.Unlayered(kind="unlayered")
    elif lsamp.kind == "native_default":
        if backend != "lsprepost":
            raise ValueError("native_default sampling requires backend 'lsprepost'")
        sampling = core_contracts.NativeDefault(kind="native_default")
    elif lsamp.kind == "native_element_scalar":
        if domain in ("node", "global", "part", "interface"):
            sampling = core_contracts.Unlayered(kind="unlayered")
        else:
            sampling = core_contracts.NativeDefault(kind="native_default")
    elif lsamp.kind == "native_shell_layer":
        if backend != "lsprepost":
            raise ValueError("native_shell_layer sampling requires backend 'lsprepost'")
        layer_val = str(lsamp.value).lower()
        if layer_val not in ("inner", "mid", "outer"):
            raise ValueError(f"Unknown native shell layer '{layer_val}'")
        sampling = core_contracts.NativeLayer(kind="native_layer", layer=layer_val)  # type: ignore[arg-type]
    elif lsamp.kind == "native_integration_point":
        if backend != "lsprepost":
            raise ValueError("native_integration_point sampling requires backend 'lsprepost'")
        sampling = core_contracts.NativePoint(kind="native_point", index=int(lsamp.value))
    elif lsamp.kind == "stored_integration_point":
        if backend == "lsprepost":
            raise ValueError("stored_integration_point sampling cannot be mapped to native backend 'lsprepost'")
        val_tuple = lsamp.value if isinstance(lsamp.value, tuple) else (lsamp.value,)
        sampling = core_contracts.StoredPoint(kind="stored_point", index=int(val_tuple[0]))
    elif lsamp.kind == "stored_axes":
        if backend == "lsprepost":
            raise ValueError("stored_axes sampling cannot be mapped to native backend 'lsprepost'")
        val_tuple = lsamp.value if isinstance(lsamp.value, tuple) else (lsamp.value,)
        if len(val_tuple) == 1:
            sampling = core_contracts.StoredPoint(kind="stored_point", index=int(val_tuple[0]))
        else:
            raise ValueError(
                f"Stored axes indices {val_tuple} cannot be mapped to core StoredPoint: "
                f"core StoredPoint only accepts a single scalar integration point index."
            )
    elif lsamp.kind == "dpf_native_location":
        if lsamp.value == "Nodal" and domain == "node":
            sampling = core_contracts.Unlayered(kind="unlayered")
        else:
            raise ValueError(
                f"DPF native location '{lsamp.value}' has no direct core Sampling representation; "
                f"location semantics must be handled or rejected explicitly."
            )
    else:
        raise ValueError(f"Unknown legacy sampling kind '{lsamp.kind}'")

    # 5. Map Frame
    resolved_frame: Literal["global", "material", "local"]
    if frame is not None:
        resolved_frame = frame
    else:
        frame_lower = legacy_spec.frame.lower()
        if (
            "as_stored" in frame_lower
            or "datacenter" in frame_lower
            or "no coordinate transformation" in frame_lower
        ):
            raise ValueError(
                f"Frame '{legacy_spec.frame}' denotes absence of transformation rather than a defined "
                f"coordinate system (global/local/material); pass explicit 'frame=' to disambiguate."
            )
        elif "material" in frame_lower:
            resolved_frame = "material"
        elif "local" in frame_lower:
            resolved_frame = "local"
        elif "global" in frame_lower:
            resolved_frame = "global"
        else:
            raise ValueError(
                f"Unrecognized legacy frame '{legacy_spec.frame}'; pass explicit 'frame=' to disambiguate."
            )

    resolved_csid: int | None = coordinate_system_id
    if resolved_frame == "local" and resolved_csid is None:
        match = re.search(r"(?:csid|coordinate_system_id|id)\s*[:=]\s*(\d+)", legacy_spec.frame)
        if match:
            resolved_csid = int(match.group(1))
        else:
            raise ValueError("Local frame requires explicit coordinate_system_id")
    elif resolved_frame != "local":
        resolved_csid = None


    # 6. Map Averaging
    resolved_averaging: Literal["none", "minmax", "nodal"]
    if averaging is not None:
        resolved_averaging = averaging
    else:
        avg_lower = legacy_spec.averaging.lower()
        if "minmax" in avg_lower:
            resolved_averaging = "minmax"
        elif "nodal" in avg_lower:
            resolved_averaging = "nodal"
        else:
            resolved_averaging = "none"

    return core_contracts.FieldSpec(
        quantity=resolved_quantity,
        components=resolved_components,
        units=legacy_spec.units,
        backend=backend,
        selector=selector,
        at=at,
        sampling=sampling,
        frame=resolved_frame,
        coordinate_system_id=resolved_csid,
        averaging=resolved_averaging,
    )


def assert_field_spec_equivalence(
    core_spec: core_contracts.FieldSpec,
    legacy_spec: LegacyFieldSpec,
) -> None:
    """Assert that a core.contracts.FieldSpec and a legacy field_contracts.FieldSpec are semantically equivalent.

    Raises AssertionError with clear explanation if any attribute or semantics diverge.
    Verifies that native layer/point is never equated to reader stored point.
    """
    # 1. Backend
    if core_spec.backend != legacy_spec.backend:
        raise AssertionError(
            f"Backend mismatch: core has '{core_spec.backend}', legacy has '{legacy_spec.backend}'"
        )

    # 2. Units
    if core_spec.units != legacy_spec.units:
        raise AssertionError(
            f"Units mismatch: core has '{core_spec.units}', legacy has '{legacy_spec.units}'"
        )

    # 3. Domain
    core_domain = core_spec.selector.entity_type
    legacy_domain = legacy_spec.selection.domain
    if core_domain != legacy_domain:
        raise AssertionError(
            f"Entity domain mismatch: core has '{core_domain}', legacy has '{legacy_domain}'"
        )

    # 4. Quantity and Components vs Legacy Fields
    try:
        expected_fields = _map_core_to_legacy_fields(
            core_spec.backend,
            core_domain,
            core_spec.quantity,
            core_spec.components,
        )
    except Exception as e:
        raise AssertionError(
            f"Cannot map core quantity '{core_spec.quantity}' and components {core_spec.components} to legacy fields: {e}"
        ) from e

    if expected_fields != legacy_spec.fields:
        try:
            inferred_q, _ = _infer_core_quantity_and_components(
                legacy_spec.fields, legacy_domain
            )
        except Exception:
            inferred_q = "unknown"

        if core_spec.quantity.lower() != inferred_q.lower():
            raise AssertionError(
                f"Quantity mismatch: core quantity is '{core_spec.quantity}', but legacy fields "
                f"{legacy_spec.fields} infer quantity '{inferred_q}'"
            )
        raise AssertionError(
            f"Field / component mismatch: core quantity '{core_spec.quantity}' with components "
            f"{core_spec.components} maps to fields {expected_fields}, but legacy spec has "
            f"fields {legacy_spec.fields}"
        )

    # 4. Entity IDs
    if core_domain == "global":
        if legacy_spec.selection.entity_ids:
            raise AssertionError(
                f"Global domain must not carry entity IDs, but legacy has {legacy_spec.selection.entity_ids}"
            )
    else:
        if isinstance(core_spec.selector.predicate, core_contracts.IdSelection):
            if core_spec.selector.predicate.ids != legacy_spec.selection.entity_ids:
                raise AssertionError(
                    f"Entity IDs mismatch: core has {core_spec.selector.predicate.ids}, "
                    f"legacy has {legacy_spec.selection.entity_ids}"
                )
        else:
            raise AssertionError(
                f"Cannot establish strict ID equivalence: core predicate is "
                f"'{type(core_spec.selector.predicate).__name__}', not IdSelection"
            )

    # 5. Temporal States
    if isinstance(core_spec.at, core_contracts.StateIndices):
        if core_spec.at.indices != legacy_spec.selection.states:
            raise AssertionError(
                f"State indices mismatch: core has {core_spec.at.indices}, "
                f"legacy has {legacy_spec.selection.states}"
            )
    else:
        raise AssertionError(
            "Cannot establish discrete state equivalence: core 'at' is PhysicalTime, "
            "not StateIndices"
        )

    # 6. Sampling Semantics & Cross-Backend Separation
    # Verify that cross-backend equivalence is never inferred
    described_sampling = legacy_spec.sampling.describe()
    if described_sampling.get("cross_backend_equivalence") != "not_inferred":
        raise AssertionError("Cross-backend sampling equivalence must explicitly be 'not_inferred'")

    if isinstance(core_spec.sampling, core_contracts.Unlayered):
        if legacy_spec.sampling.kind not in ("not_applicable", "dpf_native_location"):
            raise AssertionError(
                f"Unlayered sampling mismatch: legacy kind is '{legacy_spec.sampling.kind}'"
            )
    elif isinstance(core_spec.sampling, core_contracts.NativeDefault):
        if legacy_spec.sampling.kind not in ("native_default", "native_element_scalar"):
            raise AssertionError(
                f"NativeDefault sampling mismatch: legacy kind is '{legacy_spec.sampling.kind}'"
            )
    elif isinstance(core_spec.sampling, core_contracts.NativeLayer):
        if legacy_spec.sampling.kind != "native_shell_layer":
            raise AssertionError(
                f"NativeLayer sampling mismatch: legacy kind is '{legacy_spec.sampling.kind}', "
                f"expected 'native_shell_layer'"
            )
        if legacy_spec.sampling.native_selector != core_spec.sampling.layer.upper():
            raise AssertionError(
                f"Native shell layer mismatch: core has '{core_spec.sampling.layer}', "
                f"legacy has selector '{legacy_spec.sampling.native_selector}'"
            )
    elif isinstance(core_spec.sampling, core_contracts.NativePoint):
        if legacy_spec.sampling.kind != "native_integration_point":
            raise AssertionError(
                f"NativePoint sampling mismatch: legacy kind is '{legacy_spec.sampling.kind}', "
                f"expected 'native_integration_point'"
            )
        if legacy_spec.sampling.native_selector != str(core_spec.sampling.index):
            raise AssertionError(
                f"Native point index mismatch: core has {core_spec.sampling.index}, "
                f"legacy selector is '{legacy_spec.sampling.native_selector}'"
            )
    elif isinstance(core_spec.sampling, core_contracts.StoredPoint):
        if legacy_spec.sampling.kind not in ("stored_integration_point", "stored_axes"):
            raise AssertionError(
                f"StoredPoint sampling mismatch: legacy kind is '{legacy_spec.sampling.kind}', "
                f"expected 'stored_integration_point' or 'stored_axes'"
            )
        val = legacy_spec.sampling.value
        val_tuple = val if isinstance(val, tuple) else (val,)
        if val_tuple != (core_spec.sampling.index,):
            raise AssertionError(
                f"Stored point index mismatch: core has {core_spec.sampling.index}, "
                f"legacy has {val_tuple}"
            )
    else:
        raise AssertionError(f"Unknown core sampling: {core_spec.sampling}")

    # 7. Coordinate System / Frame
    legacy_frame_lower = legacy_spec.frame.lower()
    if "as_stored" in legacy_frame_lower or "datacenter" in legacy_frame_lower:
        raise AssertionError(
            f"Frame mismatch: legacy frame '{legacy_spec.frame}' denotes lack of coordinate "
            f"transformation rather than an explicit coordinate system; cannot equate to core '{core_spec.frame}'"
        )
    if core_spec.frame == "global" and "global" not in legacy_frame_lower:
        raise AssertionError(f"Frame mismatch: core is 'global', legacy is '{legacy_spec.frame}'")
    if core_spec.frame == "material" and "material" not in legacy_frame_lower:
        raise AssertionError(f"Frame mismatch: core is 'material', legacy is '{legacy_spec.frame}'")
    if core_spec.frame == "local":
        if "local" not in legacy_frame_lower:
            raise AssertionError(f"Frame mismatch: core is 'local', legacy is '{legacy_spec.frame}'")
        if core_spec.coordinate_system_id is not None:
            if str(core_spec.coordinate_system_id) not in legacy_spec.frame:
                raise AssertionError(
                    f"Local coordinate system ID {core_spec.coordinate_system_id} not reflected in legacy frame '{legacy_spec.frame}'"
                )


    # 8. Averaging
    if core_spec.averaging == "nodal" and "nodal" not in legacy_spec.averaging.lower():
        raise AssertionError(f"Averaging mismatch: core is 'nodal', legacy is '{legacy_spec.averaging}'")
    if core_spec.averaging == "minmax" and "minmax" not in legacy_spec.averaging.lower():
        raise AssertionError(f"Averaging mismatch: core is 'minmax', legacy is '{legacy_spec.averaging}'")

    # 9. Validity
    val_lower = legacy_spec.validity.lower()
    if core_spec.selector.validity == "alive":
        is_alive = (
            "positive material code=present" in val_lower
            or ("physical deletion filtering" in val_lower and "not requested" not in val_lower and "deleted only" not in val_lower and "deleted elements only" not in val_lower)
            or ("alive" in val_lower and "not requested" not in val_lower and "extrema are not alive-only" not in val_lower)
        )
        if not is_alive:
            raise AssertionError(
                f"Validity mismatch: core is 'alive', legacy is '{legacy_spec.validity}'"
            )
    elif core_spec.selector.validity == "all":
        is_all = (
            "raw stored population" in val_lower
            or "not requested" in val_lower
            or val_lower in ("all", "raw")
            or "no explicit alive/deletion mask" in val_lower
        )
        if not is_all:
            raise AssertionError(
                f"Validity mismatch: core is 'all', legacy is '{legacy_spec.validity}'"
            )
    elif core_spec.selector.validity == "deleted":
        is_deleted = "deleted only" in val_lower or "deleted elements only" in val_lower or val_lower == "deleted"
        if not is_deleted:
            raise AssertionError(
                f"Validity mismatch: core is 'deleted', legacy is '{legacy_spec.validity}'"
            )


def is_field_spec_equivalent(
    core_spec: core_contracts.FieldSpec,
    legacy_spec: LegacyFieldSpec,
) -> bool:
    """Return True if core_spec and legacy_spec are semantically equivalent, False otherwise."""
    try:
        assert_field_spec_equivalence(core_spec, legacy_spec)
        return True
    except (AssertionError, ValueError):
        return False


def describe_field_spec_mapping(
    core_spec: core_contracts.FieldSpec,
    legacy_spec: LegacyFieldSpec,
) -> dict[str, Any]:
    """Produce a structured comparison dictionary contrasting domain request and legacy provenance."""
    is_equiv = is_field_spec_equivalent(core_spec, legacy_spec)
    return {
        "equivalent": is_equiv,
        "semantic_distinction": (
            "core.contracts.FieldSpec represents a declarative domain request (algebraic/geometric "
            "selectors, continuous or discrete time, solver-invariant component identifiers); "
            "field_contracts.FieldSpec represents an executable result request and provenance "
            "contract (backend-specific field keys, resolved user IDs and 1-based states, "
            "low-level SCL or reader sampling parameters)."
        ),
        "backend": {
            "core": core_spec.backend,
            "legacy": legacy_spec.backend,
            "match": core_spec.backend == legacy_spec.backend,
        },
        "units": {
            "core": core_spec.units,
            "legacy": legacy_spec.units,
            "match": core_spec.units == legacy_spec.units,
        },
        "domain": {
            "core": core_spec.selector.entity_type,
            "legacy": legacy_spec.selection.domain,
            "match": core_spec.selector.entity_type == legacy_spec.selection.domain,
        },
        "sampling": {
            "core_kind": core_spec.sampling.kind,
            "legacy_kind": legacy_spec.sampling.kind,
            "cross_backend_equivalence": "not_inferred",
        },
        "frame": {
            "core": core_spec.frame,
            "legacy": legacy_spec.frame,
            "coordinate_system_id": core_spec.coordinate_system_id,
        },
        "averaging": {
            "core": core_spec.averaging,
            "legacy": legacy_spec.averaging,
        },
        "validity": {
            "core": core_spec.selector.validity,
            "legacy": legacy_spec.validity,
        },
        "legacy_fields": list(legacy_spec.fields),
        "legacy_transformations": list(legacy_spec.transformations),
    }


class FieldContractAdapter:
    """Stateful / configured adapter between core.contracts and field_contracts."""

    def __init__(
        self,
        *,
        entity_resolver: Callable[[core_contracts.Selector], Sequence[int]] | None = None,
        state_resolver: Callable[[core_contracts.PhysicalTime], Sequence[int]] | None = None,
        field_mapping: (
            Sequence[str] | dict[str, str] | Callable[[str, Sequence[str]], Sequence[str]] | None
        ) = None,
    ) -> None:
        self.entity_resolver = entity_resolver
        self.state_resolver = state_resolver
        self.field_mapping = field_mapping

    def to_legacy(
        self,
        core_spec: core_contracts.FieldSpec,
        *,
        resolved_entity_ids: Sequence[int] | None = None,
        resolved_states: Sequence[int] | None = None,
        **kwargs: Any,
    ) -> LegacyFieldSpec:
        """Adapt core FieldSpec to legacy FieldSpec using configured or explicit resolvers."""
        if resolved_entity_ids is None and self.entity_resolver is not None:
            resolved_entity_ids = self.entity_resolver(core_spec.selector)
        if resolved_states is None and self.state_resolver is not None and isinstance(core_spec.at, core_contracts.PhysicalTime):
            resolved_states = self.state_resolver(core_spec.at)
        mapping = kwargs.pop("field_mapping", self.field_mapping)
        return core_to_legacy_field_spec(
            core_spec,
            resolved_entity_ids=resolved_entity_ids,
            resolved_states=resolved_states,
            field_mapping=mapping,
            **kwargs,
        )

    def to_core(
        self,
        legacy_spec: LegacyFieldSpec,
        **kwargs: Any,
    ) -> core_contracts.FieldSpec:
        """Adapt legacy FieldSpec to core FieldSpec."""
        return legacy_to_core_field_spec(legacy_spec, **kwargs)

    def verify_equivalence(
        self,
        core_spec: core_contracts.FieldSpec,
        legacy_spec: LegacyFieldSpec,
    ) -> None:
        """Assert semantic equivalence between core and legacy specifications."""
        assert_field_spec_equivalence(core_spec, legacy_spec)
