"""Q03/Q04 target tool ``extract_field`` on ``domain.results.lasso_backend``, ``invariants``, and native SCL.

Tasks:
- Q03: Field data extraction to CSV / NPZ with full 8-item semantic metadata
  (quantity, component, units, state, time, layer/integration_point, coordinate_system, backend).
  Supports solid, shell, and tshell elements; multi-component stress tensors (six components);
  part and entity filtering; element deletion masking; rejection of unverified native solid
  integration points 2..8; and cross-backend element-by-element equivalence verification.
- Q04: Stress invariants (von Mises, principal stresses, triaxiality, Lode parameter and angle),
  effective plastic strain, failure masking ('alive', 'all', 'deleted'), and extrema calculation.

Returns strict JobResult/v1 with verified CSV and NPZ artifacts.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .core.contracts import Artifact, CheckResult, JobResult
from .domain.results import invariants as inv
from .domain.results import lasso_backend as lb
from .jobs import atomic_json, fingerprint

BACKEND_LASSO = "lasso-invariants"
BACKEND_NATIVE = "lsprepost"

QUANTITY_ALIASES: dict[str, str] = {
    "mises": "von_mises",
    "vm": "von_mises",
    "eps": "effective_plastic_strain",
    "plastic_strain": "effective_plastic_strain",
    "eqps": "effective_plastic_strain",
    "triax": "triaxiality",
    "lode": "lode_parameter",
    "lode_angle": "lode_angle_rad",
    "lode_param": "lode_parameter",
}

FAMILY_ALIASES: dict[str, str] = {
    "solids": "solid",
    "shells": "shell",
    "tshells": "tshell",
}

STRESS_COMPONENTS = ("sxx", "syy", "szz", "sxy", "syz", "szx")
ALLOWED_MASKS = frozenset({"alive", "all", "deleted"})
ALLOWED_FORMATS = frozenset({"csv", "npz", "both", "all", "none"})


def _jsonable(value: object) -> object:
    """Plain JSON values: numpy scalars and arrays converted, NaN/Inf serialized as string, None preserved."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _write_field_artifact(
    path: Path,
    meta: dict[str, Any],
    ids: np.ndarray,
    values: np.ndarray | dict[str, np.ndarray],
    alive: np.ndarray,
    fmt: str,
) -> dict[str, Any]:
    """Write field data to path as CSV or NPZ with embedded metadata.

    CSV header lines start with ``# key: value``, followed by column headers and data rows.
    NPZ stores ``ids``, ``values``, ``alive``, and ``meta`` as JSON string.
    Returns path, format, rows, sha256 digest, and metadata dict.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ids_arr = np.asarray(ids, dtype=np.int64).reshape(-1)
    alive_arr = np.asarray(alive, dtype=bool).reshape(-1)

    if fmt == "csv":
        header_lines = "".join(f"# {key}: {json.dumps(value, default=str)}\n" for key, value in meta.items())
        if isinstance(values, dict):
            cols = list(values.keys())
            header_lines += "id," + ",".join(cols) + ",alive\n"
            rows = []
            for i, eid in enumerate(ids_arr):
                c_vals = ",".join(f"{float(values[c][i]):.9g}" for c in cols)
                rows.append(f"{int(eid)},{c_vals},{int(alive_arr[i])}\n")
            path.write_text(header_lines + "".join(rows), encoding="utf-8")
        else:
            vals_arr = np.asarray(values, dtype=float).reshape(-1)
            header_lines += "id,value,alive\n"
            rows = "".join(f"{int(i)},{v:.9g},{int(a)}\n" for i, v, a in zip(ids_arr, vals_arr, alive_arr))
            path.write_text(header_lines + rows, encoding="utf-8")

    elif fmt == "npz":
        meta_json = json.dumps(meta, default=str)
        if isinstance(values, dict):
            arrays = {c: np.asarray(values[c], dtype=float) for c in values}
            matrix = np.column_stack([arrays[c] for c in values])
            with path.open("wb") as handle:
                np.savez(handle, ids=ids_arr, values=matrix, alive=alive_arr, meta=np.asarray(meta_json), **arrays)
        else:
            vals_arr = np.asarray(values, dtype=float).reshape(-1)
            with path.open("wb") as handle:
                np.savez(handle, ids=ids_arr, values=vals_arr, alive=alive_arr, meta=np.asarray(meta_json))
    else:
        raise ValueError(f"Unknown output format: {fmt}")

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": str(path), "format": fmt, "rows": int(ids_arr.size), "sha256": digest, "meta": meta}


class FieldMetricsTools:
    """Mixed into Service: extracts element field metrics, computes stress invariants and failure masks."""

    def extract_field(
        self,
        path: str,
        family: str,
        quantity: str,
        state: int = -1,
        mask: str = "alive",
        units: str | None = None,
        output_format: str = "csv",
        component: str | None = None,
        part_ids: list[int] | int | None = None,
        entity_ids: list[int] | None = None,
        integration_point: int | str | None = None,
        layer: str | None = None,
        backend: str = "lasso",
        cross_check: bool = False,
    ) -> dict[str, Any]:
        """Extract an element field or compute stress invariants with failure masking (Q03/Q04).

        Supports 'solid', 'shell', and 'tshell' element families.
        Quantities include:
        - stress six-components: 'stress' (all six: sxx, syy, szz, sxy, syz, szx) or single component
        - stress components: sxx, syy, szz, sxy, syz, szx
        - stress invariants: von_mises, mean_stress, pressure, triaxiality,
          principal_1, principal_2, principal_3, max_shear,
          lode_parameter, lode_angle_rad, lode_angle_parameter
        - effective_plastic_strain
        Mask options: 'alive' (default), 'all', 'deleted'.
        Filter options: 'part_ids' (single int or list of ints), 'entity_ids' (list of element IDs).
        Backends: 'lasso' (default), 'native' / 'lsprepost'.
        Returns JobResult/v1 with 8-item metadata (quantity, component, units, state, time,
        layer/integration_point, coordinate_system, backend), extrema, and verified CSV/NPZ artifacts.
        """
        if not isinstance(path, str) or not path.strip():
            raise ValueError("Input path must be a non-empty string")
        if str(path).strip().startswith(("\\\\", "//")):
            raise ValueError(f"Network path {path!r} is not followed")

        fam_key = family.strip().lower() if isinstance(family, str) else ""
        norm_family = FAMILY_ALIASES.get(fam_key, fam_key)
        if norm_family not in lb.FAMILIES:
            raise ValueError(f"Unknown element family {family!r}; allowed: {sorted(lb.FAMILIES)}")

        norm_mask = mask.strip().lower() if isinstance(mask, str) else ""
        if norm_mask not in ALLOWED_MASKS:
            raise ValueError(f"Unknown mask mode {mask!r}; allowed: {sorted(ALLOWED_MASKS)}")

        norm_fmt = output_format.strip().lower() if isinstance(output_format, str) else "csv"
        if norm_fmt not in ALLOWED_FORMATS:
            raise ValueError(f"Unknown output format {output_format!r}; allowed: {sorted(ALLOWED_FORMATS)}")

        if not isinstance(quantity, str) or not quantity.strip():
            raise ValueError("Quantity must be a non-empty string")
        q_raw = quantity.strip().lower()

        if not isinstance(state, int):
            raise ValueError(f"State must be an integer, got {type(state).__name__}")

        if units is not None and not isinstance(units, str):
            raise ValueError("Units must be a string or None")

        norm_backend = backend.strip().lower() if isinstance(backend, str) else "lasso"
        if norm_backend not in ("lasso", "native", "lsprepost"):
            raise ValueError(f"Unknown backend {backend!r}; allowed: 'lasso', 'native'")

        # Solid integration point 2..8 refusal check
        if norm_family == "solid" and integration_point is not None:
            ipt_num = None
            try:
                ipt_num = int(str(integration_point).strip())
            except (ValueError, TypeError):
                pass
            if ipt_num is not None and 2 <= ipt_num <= 8:
                if norm_backend in ("native", "lsprepost") or cross_check:
                    raise ValueError(
                        "Native solid integration points 2..8 are not verified: LS-PrePost 4.13.4 "
                        "SCL can return point 1 for another requested point. Use an explicitly "
                        "selected reader stored-point backend, or wait for a validated native adapter; "
                        "no automatic backend or sampling fallback is performed"
                    )

        # Quantity and component normalization
        is_six_components = False
        if q_raw == "stress":
            if component is not None and component.strip().lower() not in ("all", "six", "all_six", ""):
                c_key = component.strip().lower()
                norm_quantity = QUANTITY_ALIASES.get(c_key, c_key)
                actual_quantity = "stress"
                actual_component = norm_quantity
            else:
                is_six_components = True
                norm_quantity = "stress"
                actual_quantity = "stress"
                actual_component = "all_six"
        else:
            norm_quantity = QUANTITY_ALIASES.get(q_raw, q_raw)
            actual_quantity = norm_quantity
            if norm_quantity in STRESS_COMPONENTS:
                actual_component = norm_quantity
            elif norm_quantity in inv.QUANTITIES:
                actual_component = norm_quantity
            elif norm_quantity == "effective_plastic_strain":
                actual_component = "scalar"
            else:
                actual_component = component.strip().lower() if component else norm_quantity

        source = self.settings.input_path(path)

        parameters = {
            "path": str(source),
            "family": norm_family,
            "quantity": norm_quantity,
            "component": actual_component,
            "state": state,
            "mask": norm_mask,
            "units": units,
            "output_format": norm_fmt,
            "part_ids": part_ids,
            "entity_ids": entity_ids,
            "integration_point": integration_point,
            "layer": layer,
            "backend": norm_backend,
            "cross_check": cross_check,
        }
        directory, manifest = self.jobs.create("extract_field", parameters)

        before_fp = fingerprint(source)
        error: dict[str, Any] | None = None
        artifacts: list[Artifact] = []
        data: dict[str, Any] = {}
        checks: list[CheckResult] = []
        warnings: list[str] = []

        try:
            # 1. Read d3plot arrays using shared LASSO reader
            arrays = lb._arrays(source)
            times = lb._times(arrays)
            state_idx = int(state % times.size)
            state_time = float(times[state_idx])

            # Element IDs and alive mask
            fam_tuple = lb.FAMILIES[norm_family]
            all_ids = np.asarray(arrays[fam_tuple[0]]).reshape(-1)
            alive_key = fam_tuple[1]
            if alive_key in arrays:
                all_alive = np.asarray(arrays[alive_key])[state_idx] != 0
            else:
                all_alive = np.ones(all_ids.size, bool)

            # Part filtering
            if part_ids is not None:
                p_filter = {part_ids} if isinstance(part_ids, int) else {int(p) for p in part_ids}
                part_idx_key = fam_tuple[2]
                pids = lb._part_ids(arrays)
                if part_idx_key in arrays and len(pids) > 0:
                    elem_pids = pids[np.asarray(arrays[part_idx_key])]
                    part_mask = np.isin(elem_pids, list(p_filter))
                    if not np.any(part_mask):
                        raise ValueError(
                            f"No {norm_family} elements found in part_ids={sorted(p_filter)}; "
                            f"available parts: {sorted(set(elem_pids.tolist()))}"
                        )
                else:
                    part_mask = np.ones(all_ids.size, bool)
            else:
                p_filter = None
                part_mask = np.ones(all_ids.size, bool)

            # Entity ID filtering
            if entity_ids is not None:
                wanted_entities = {int(e) for e in entity_ids}
                entity_mask = np.isin(all_ids, list(wanted_entities))
                if not np.any(entity_mask):
                    raise ValueError(f"None of the requested entity_ids {entity_ids[:10]} found in {norm_family}")
            else:
                entity_mask = np.ones(all_ids.size, bool)

            # Combined entity selection
            combined_mask = part_mask & entity_mask
            filtered_ids = all_ids[combined_mask]
            filtered_alive = all_alive[combined_mask]
            element_count = int(filtered_ids.size)

            # Determine layer and integration point description
            if norm_family == "solid":
                layer_desc = None
                ipt_desc = 1 if integration_point in (None, 1, "1", "mid") else integration_point
            else:
                layer_desc = layer or (str(integration_point) if integration_point in ("mid", "inner", "outer") else "mid")
                ipt_desc = integration_point if integration_point not in ("mid", "inner", "outer", None) else (1 if layer_desc != "outer" else 2)

            declared_units = units if (units and units.strip()) else "model units, not converted (unit system not declared)"

            # 2. Extract values and compute extrema
            if is_six_components:
                comp_values: dict[str, np.ndarray] = {}
                comp_extrema: dict[str, Any] = {}
                note = "stored value"
                for c in STRESS_COMPONENTS:
                    v_arr, note = lb._element_values(arrays, norm_family, c)
                    c_filtered = v_arr[state_idx][combined_mask]
                    comp_values[c] = c_filtered
                    sel = inv.masked(filtered_alive, norm_mask)
                    comp_extrema[c] = inv.extrema(c_filtered, filtered_ids, sel)

                active_count = int(comp_extrema["sxx"].get("count", 0))
                deleted_count = int(element_count - np.count_nonzero(filtered_alive))
                extrema = comp_extrema
                formula = "Cauchy stress components (sxx, syy, szz, sxy, syz, szx)"
                values_export = comp_values

            else:
                v_arr, note = lb._element_values(arrays, norm_family, norm_quantity)
                filtered_vals = v_arr[state_idx][combined_mask]
                sel = inv.masked(filtered_alive, norm_mask)
                raw_ext = inv.extrema(filtered_vals, filtered_ids, sel)
                min_info = raw_ext.get("min")
                max_info = raw_ext.get("max")
                extrema = {
                    "count": int(raw_ext.get("count", 0)),
                    "min": {**min_info, "state": state_idx, "state_1based": state_idx + 1} if min_info is not None else None,
                    "max": {**max_info, "state": state_idx, "state_1based": state_idx + 1} if max_info is not None else None,
                }
                active_count = int(extrema["count"])
                deleted_count = int(element_count - np.count_nonzero(filtered_alive))
                formula = inv.CONVENTIONS.get(norm_quantity, "stored or IP-averaged value")
                values_export = filtered_vals

            # 3. Assemble full 8-item semantic metadata
            coord_sys = "global (as stored in d3plot)" if norm_backend == "lasso" else "native DataCenter component frame; no coordinate transformation"
            backend_label = lb.backend() if norm_backend == "lasso" else "lsprepost"

            meta = {
                "quantity": actual_quantity,
                "component": actual_component,
                "components": list(STRESS_COMPONENTS) if is_six_components else [actual_component],
                "units": declared_units,
                "state": state_idx,
                "state_1based": state_idx + 1,
                "time": state_time,
                "layer": layer_desc,
                "integration_point": ipt_desc,
                "points": note,
                "coordinate_system": coord_sys,
                "backend": backend_label,
                "family": norm_family,
                "mask": norm_mask,
                "rows": element_count,
                "element_count": element_count,
                "active_count": active_count,
                "deleted_count": deleted_count,
                "part_ids": sorted(p_filter) if p_filter is not None else None,
                "extrema": extrema,
            }

            # 4. Export artifacts (CSV and/or NPZ)
            prefix = f"{norm_family}_{'stress_six_components' if is_six_components else norm_quantity}_state_{state_idx}"
            if p_filter is not None and len(p_filter) == 1:
                prefix = f"part_{next(iter(p_filter))}_{prefix}"

            if norm_fmt in ("csv", "both", "all"):
                csv_file = directory / f"{prefix}.csv"
                exported = _write_field_artifact(csv_file, meta, filtered_ids, values_export, filtered_alive, "csv")
                artifacts.append(
                    Artifact(
                        path=str(csv_file),
                        kind="csv",
                        sha256=exported["sha256"],
                        size_bytes=csv_file.stat().st_size,
                        verification="verified",
                        metadata=exported["meta"],
                    )
                )

            if norm_fmt in ("npz", "both", "all"):
                npz_file = directory / f"{prefix}.npz"
                exported = _write_field_artifact(npz_file, meta, filtered_ids, values_export, filtered_alive, "npz")
                artifacts.append(
                    Artifact(
                        path=str(npz_file),
                        kind="npz",
                        sha256=exported["sha256"],
                        size_bytes=npz_file.stat().st_size,
                        verification="verified",
                        metadata=exported["meta"],
                    )
                )

            # 5. Native cross-check if requested
            cross_check_info: dict[str, Any] | None = None
            if cross_check:
                # Perform native extraction comparison on the filtered entities
                from .native_results import STRESS_KEYS
                native_ipt = str(ipt_desc) if ipt_desc is not None else "mid"
                if norm_family == "solid" and str(native_ipt) in ("1", "solid_default"):
                    native_ipt = "mid"
                req_fields = STRESS_KEYS + ["von_mises"] if (is_six_components or norm_quantity in STRESS_COMPONENTS or norm_quantity == "von_mises") else [norm_quantity]
                native_out = self.extract_native_fields(
                    str(source),
                    norm_family,
                    [int(i) for i in filtered_ids],
                    [state_idx + 1],
                    req_fields,
                    native_ipt,
                    declared_units,
                    validity_policy="raw",
                )
                if native_out.get("status") == "succeeded":
                    checks.append(CheckResult(name="native_extraction", status="passed"))
                    # Compare numerical agreement element-by-element
                    native_csv_path = Path(native_out["artifacts"][0]["path"])
                    import csv as py_csv
                    with native_csv_path.open(encoding="utf-8") as nf:
                        native_rows = {int(r["entity_id"]): r for r in py_csv.DictReader(nf)}
                    diffs = []
                    native_field_map = {
                        "sxx": "stress_x",
                        "syy": "stress_y",
                        "szz": "stress_z",
                        "sxy": "stress_xy",
                        "syz": "stress_yz",
                        "szx": "stress_zx",
                        "von_mises": "von_mises",
                    }
                    comp_to_check = STRESS_COMPONENTS if is_six_components else ([norm_quantity] if norm_quantity in STRESS_COMPONENTS else ["von_mises"])
                    for comp_name in comp_to_check:
                        nat_col = native_field_map.get(comp_name, comp_name)
                        for idx_e, eid in enumerate(filtered_ids):
                            eid_int = int(eid)
                            if eid_int in native_rows:
                                if nat_col in native_rows[eid_int]:
                                    nat_v = float(native_rows[eid_int][nat_col])
                                elif comp_name in native_rows[eid_int]:
                                    nat_v = float(native_rows[eid_int][comp_name])
                                else:
                                    continue
                                las_v = float(comp_values[comp_name][idx_e] if is_six_components else filtered_vals[idx_e])
                                diffs.append(abs(nat_v - las_v))
                    max_diff = max(diffs) if diffs else 0.0
                    passed_equiv = max_diff <= 1e-4
                    checks.append(CheckResult(name="backend_cross_check", status="passed" if passed_equiv else "failed"))
                    cross_check_info = {
                        "status": "passed" if passed_equiv else "failed",
                        "max_absolute_difference": max_diff,
                        "tolerance": 1e-4,
                        "elements_compared": len(filtered_ids),
                    }
                else:
                    checks.append(CheckResult(name="native_extraction", status="failed"))

            # 6. Build response data
            if is_six_components:
                vals_payload = {
                    c: [float(v) if math.isfinite(v) else "nan" for v in np.asarray(comp_values[c], dtype=float).reshape(-1)]
                    for c in STRESS_COMPONENTS
                }
            else:
                vals_payload = [float(v) if math.isfinite(v) else "nan" for v in np.asarray(filtered_vals, dtype=float).reshape(-1)]

            data = {
                "backend": backend_label,
                "family": norm_family,
                "quantity": actual_quantity,
                "component": actual_component,
                "components": list(STRESS_COMPONENTS) if is_six_components else [actual_component],
                "state": state_idx,
                "state_1based": state_idx + 1,
                "time": state_time,
                "units": declared_units,
                "layer": layer_desc,
                "integration_point": ipt_desc,
                "points": note,
                "coordinate_system": coord_sys,
                "mask": norm_mask,
                "formula": formula,
                "conventions": dict(inv.CONVENTIONS),
                "element_count": element_count,
                "active_count": active_count,
                "deleted_count": deleted_count,
                "part_ids": sorted(p_filter) if p_filter is not None else None,
                "extrema": extrema,
                "ids": [int(i) for i in filtered_ids],
                "values": vals_payload,
                "alive": [bool(a) for a in filtered_alive],
            }
            if cross_check_info is not None:
                data["cross_check"] = cross_check_info

            after_fp = fingerprint(source)
            unchanged = (after_fp == before_fp)
            checks.append(CheckResult(name="inputs_unchanged", status="passed" if unchanged else "failed"))
            checks.append(CheckResult(name="mask_policy_applied", status="passed"))
            has_extrema = (active_count > 0) if not is_six_components else (active_count > 0)
            checks.append(CheckResult(name="extrema_found", status="passed" if has_extrema else "not_applicable"))
            if artifacts:
                all_verified = all(a.verification == "verified" for a in artifacts)
                checks.append(CheckResult(name="artifacts_verified", status="passed" if all_verified else "failed"))

            if not unchanged:
                error = {"type": "RuntimeError", "message": "Input source file changed during field extraction"}

        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc) or type(exc).__name__}
            data = {
                "path": str(source),
                "family": norm_family,
                "quantity": norm_quantity,
                "state": state,
                "mask": norm_mask,
            }

        status = "failed" if error else "succeeded"
        backend_name = data.get("backend", lb.backend()) if not error else BACKEND_LASSO

        result = JobResult(
            operation="extract_field",
            status=status,
            backend=backend_name,
            job_id=manifest["job_id"],
            data=_jsonable(data),
            artifacts=tuple(artifacts),
            checks=tuple(checks),
            warnings=tuple(warnings),
            error=error,
            scope=f"{norm_family} field {norm_quantity} extraction with {norm_mask} mask",
        )

        payload = result.model_dump(mode="json")
        atomic_json(directory / "job.json", {**manifest, "status": payload["status"], "result": payload})
        return payload


__all__ = ["FieldMetricsTools"]
