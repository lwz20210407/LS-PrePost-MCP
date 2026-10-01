"""Read-only d3plot header validation; result extraction remains native LS-PrePost."""

from importlib.metadata import version

from .jobs import fingerprint


def header_field_contract(header, native_counts, domain, field, sampling):
    counts = {
        "node": int(header.n_nodes),
        "solid": int(header.n_solids),
        "shell": int(header.n_shells),
        "tshell": int(header.n_thick_shells),
        "beam": int(header.n_beams),
    }
    if (
        counts["node"] != native_counts["nodes"]
        or sum(counts[k] for k in ("solid", "shell", "tshell", "beam")) != native_counts["elements"]
    ):
        raise ValueError(
            "Staged d3plot header and current native model counts differ; reopen the managed model"
        )
    if counts[domain] < 1:
        raise ValueError("Requested entity domain is absent from the d3plot header")
    flags = []
    if domain == "node":
        if field.startswith(("disp_", "state_node_")):
            flags = ["has_node_displacement"]
        elif field.startswith("velo_"):
            flags = ["has_node_velocity"]
        elif field.startswith("accel_"):
            flags = ["has_node_acceleration"]
    elif field.startswith("stress_") or field in ("von_mises", "mean_stress", "pressure"):
        flags = ["has_solid_stress" if domain == "solid" else "has_shell_tshell_stress"]
    elif field == "effective_plastic_strain":
        flags = ["has_solid_pstrain" if domain == "solid" else "has_shell_tshell_pstrain"]
    elif field.startswith("strain_"):
        flags = ["has_element_strain"]
    elif field in ("area", "volume"):
        if (field == "area" and domain != "shell") or (
            field == "volume" and domain not in ("solid", "tshell")
        ):
            raise ValueError("Geometric field is unsupported for this native element domain")
        flags = ["has_node_displacement"]
    elif field == "thickness":
        if domain != "shell":
            raise ValueError("Thickness availability is implemented for shells only")
        flags = ["has_shell_extra_variables"]
    elif field == "internal_energy_density":
        flags = [
            {
                "solid": "has_solid_internal_energy_density",
                "shell": "has_shell_extra_variables",
                "tshell": "has_thick_shell_energy_density",
            }[domain]
        ]
    if not flags:
        raise ValueError("No verified d3plot availability mapping for this field")
    observed = {name: bool(getattr(header, name, False)) for name in flags}
    if not all(observed.values()):
        raise ValueError(
            "Requested field prerequisites are absent from the d3plot header: "
            + ", ".join(name for name, present in observed.items() if not present)
        )
    layers = (
        int(header.n_solid_layers if domain == "solid" else header.n_shell_tshell_layers)
        if domain != "node"
        else None
    )
    if sampling.kind == "native_integration_point" and sampling.value > layers:
        raise ValueError("Requested integration point exceeds the recorded output count")
    if sampling.kind == "native_shell_layer" and layers < 1:
        raise ValueError("No recorded shell layers")
    return dict(
        metadata_backend="lasso-header",
        data_backend="lsprepost",
        native_counts_match=True,
        prerequisite_flags=observed,
        recorded_layer_count=layers,
        scope="File-level prerequisites only; no per-material/rigid/eroded validity inference",
    )


def validate_field_availability(settings, staged_model, counts, domain, field, sampling):
    try:
        if version("lasso-python") != "2.0.4":
            raise ValueError("Header validation is pinned to lasso-python2.0.4")
        from lasso.dyna.d3plot_header import D3plotHeader
    except ImportError as exc:
        raise ValueError(
            "Named field rendering requires the results extra for read-only header validation"
        ) from exc
    source = settings.input_path(staged_model)
    identity = fingerprint(source)
    try:
        header = D3plotHeader(str(source))
    except Exception as exc:
        raise ValueError(
            "Cannot validate this d3plot header with the supported metadata reader; this is not proof that a variable is absent"
        ) from exc
    report = header_field_contract(header, counts, domain, field, sampling)
    if fingerprint(source) != identity:
        raise ValueError("Staged result changed during header validation")
    report.update(metadata_version="2.0.4", input_header=identity)
    return report
