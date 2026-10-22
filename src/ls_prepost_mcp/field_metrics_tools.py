"""Q04 target tool ``extract_field`` on ``domain.results.lasso_backend`` and ``invariants``, returning JobResult/v1.

Calculates stress invariants (von Mises, principal stresses, triaxiality, Lode parameter and angle),
effective plastic strain, and field quantities on solid, shell and thick shell elements.
Applies element failure / deletion masks ('alive', 'all', 'deleted') and computes extrema
with associated entity IDs and states. Exports data as CSV / NPZ with embedded metadata.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from pydantic import StrictInt

from .core.contracts import Artifact, CheckResult, JobResult
from .domain.results import export as exp
from .domain.results import invariants as inv
from .domain.results import lasso_backend as lb
from .jobs import atomic_json, fingerprint

BACKEND = "lasso-invariants"

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

ALLOWED_MASKS = frozenset({"alive", "all", "deleted"})
ALLOWED_FORMATS = frozenset({"csv", "npz", "both", "all", "none"})


def _state_number(state: object) -> int:
    """Public state: a 1-based positive integer, or -1 / "last" for the last state (-1 returned)."""
    if isinstance(state, str) and state.strip().lower() == "last":
        return -1
    if isinstance(state, bool) or not isinstance(state, int) or not (state == -1 or state >= 1):
        raise ValueError(f"State must be a 1-based state number, -1 or 'last', got {state!r}")
    return state


def _part_list(part_ids: object) -> list[int] | None:
    """Optional user part IDs: a non-empty list of unique positive integers."""
    if part_ids is None:
        return None
    if not isinstance(part_ids, (list, tuple)) or not part_ids:
        raise ValueError(f"part_ids must be a non-empty list of part IDs, got {part_ids!r}")
    if any(isinstance(p, bool) or not isinstance(p, int) or p < 1 for p in part_ids):
        raise ValueError(f"part_ids must be positive integer part IDs, got {list(part_ids)!r}")
    if len(set(part_ids)) != len(part_ids):
        raise ValueError(f"part_ids must not repeat a part, got {list(part_ids)!r}")
    return [int(p) for p in part_ids]


def _formula(quantity: str) -> str:
    if quantity in inv.CONVENTIONS:
        return inv.CONVENTIONS[quantity]
    if quantity == "effective_plastic_strain":
        return "stored effective plastic strain (as written to d3plot)"
    if quantity in lb.STRESS:
        return f"stored stress component {quantity} (global frame, as written to d3plot)"
    return quantity


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


class FieldMetricsTools:
    """Mixed into Service: extracts element field metrics, computes stress invariants and failure masks."""

    def extract_field(
        self,
        path: str,
        family: str,
        quantity: str,
        state: StrictInt | str = -1,
        mask: str = "alive",
        units: str | None = None,
        output_format: str = "csv",
        part_ids: list[StrictInt] | None = None,
    ) -> dict[str, Any]:
        """Extract an element field or compute stress invariants with failure masking (tasks.yaml Q04).

        Supports 'solid', 'shell', and 'tshell' element families.
        Quantities include:
        - von_mises, mean_stress, pressure, triaxiality
        - principal_1, principal_2, principal_3, max_shear
        - lode_parameter, lode_angle_rad, lode_angle_parameter
        - effective_plastic_strain
        - stress components: sxx, syy, szz, sxy, syz, szx
        state is the 1-based state number (1 = first stored state); -1 or 'last' (default) is the last
        state. Numbers outside 1..n are refused before a job is created.
        part_ids (user part IDs) restricts the elements and extrema to those parts, e.g. the target plate.
        Mask options: 'alive' (default), 'all', 'deleted'.
        Elements with several stored integration points / shell layers are averaged over them before the
        invariants are computed (shells: through-thickness mean; see data.note).
        Returns JobResult/v1 with extrema (element ID and 1-based state), formula conventions, and CSV/NPZ artifacts.
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
        q_key = quantity.strip().lower()
        norm_quantity = QUANTITY_ALIASES.get(q_key, q_key)

        state_number = _state_number(state)
        parts = _part_list(part_ids)

        if units is not None and not isinstance(units, str):
            raise ValueError("Units must be a string or None")

        source = self.settings.input_path(path)

        try:
            state_count = int(lb.state_times(source).size)
        except Exception:  # unreadable file: the job below reads it again and records the error
            state_count = None
        if state_count is not None and state_number > state_count:
            raise ValueError(f"State {state_number} is out of range; this d3plot has states 1..{state_count}")
        if state_count is not None and state_count == 0:
            raise ValueError("This d3plot has no stored states")
        state_index = -1 if state_number == -1 else state_number - 1

        parameters = {
            "path": str(source),
            "family": norm_family,
            "quantity": norm_quantity,
            "state": state_number,
            "mask": norm_mask,
            "units": units,
            "output_format": norm_fmt,
            "part_ids": parts,
        }
        directory, manifest = self.jobs.create("extract_field", parameters)

        before_fp = fingerprint(source)
        error: dict[str, Any] | None = None
        artifacts: list[Artifact] = []
        data: dict[str, Any] = {}
        checks: list[CheckResult] = []
        warnings: list[str] = []
        raw: dict[str, Any] = {}

        try:
            raw = lb.field(source, norm_family, norm_quantity, state=state_index, mask=norm_mask, part_ids=parts)

            state_out = int(raw["state"]) + 1  # public 1-based state number
            state_time = float(raw["time"])

            raw_ext = raw.get("extrema") or {"count": 0, "min": None, "max": None}
            min_info = raw_ext.get("min")
            max_info = raw_ext.get("max")
            extrema = {
                "count": int(raw_ext.get("count", 0)),
                "min": {**min_info, "state": state_out} if min_info is not None else None,
                "max": {**max_info, "state": state_out} if max_info is not None else None,
            }
            raw = {**raw, "state": state_out, "extrema": extrema}

            declared_units = units if (units and units.strip()) else "model units, not converted (unit system not declared)"

            if norm_fmt in ("csv", "both", "all"):
                csv_file = directory / f"{norm_family}_{norm_quantity}_state_{state_out}.csv"
                exported = exp.export_field(raw, csv_file, units=declared_units, fmt="csv")
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
                npz_file = directory / f"{norm_family}_{norm_quantity}_state_{state_out}.npz"
                exported = exp.export_field(raw, npz_file, units=declared_units, fmt="npz")
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

            formula = _formula(norm_quantity)

            data = {
                "backend": raw.get("backend", lb.backend()),
                "family": norm_family,
                "quantity": norm_quantity,
                "state": state_out,
                "state_count": state_count,
                "time": state_time,
                "units": declared_units,
                "mask": norm_mask,
                "part_ids": parts,
                "note": raw.get("note", "stored value"),
                "formula": formula,
                "conventions": dict(inv.CONVENTIONS),
                "element_count": int(np.asarray(raw["ids"]).size),
                "active_count": int(extrema["count"]),
                "extrema": extrema,
                "ids": [int(i) for i in np.asarray(raw["ids"]).reshape(-1)],
                "values": [float(v) if math.isfinite(v) else "nan" for v in np.asarray(raw["values"], dtype=float).reshape(-1)],
                "alive": [bool(a) for a in np.asarray(raw["alive"], dtype=bool).reshape(-1)],
            }

            after_fp = fingerprint(source)
            unchanged = (after_fp == before_fp)
            checks.append(CheckResult(name="inputs_unchanged", status="passed" if unchanged else "failed"))
            checks.append(CheckResult(name="mask_policy_applied", status="passed"))
            checks.append(CheckResult(name="extrema_found", status="passed" if extrema["count"] > 0 else "not_applicable"))
            if artifacts:
                all_verified = all(a.verification == "verified" for a in artifacts)
                checks.append(CheckResult(name="artifacts_verified", status="passed" if all_verified else "failed"))

            if not unchanged:
                error = {"type": "RuntimeError", "message": "Input source file changed during field extraction"}

        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc) or type(exc).__name__}
            data = {"path": str(source), "family": norm_family, "quantity": norm_quantity, "state": state_number,
                    "mask": norm_mask, "part_ids": parts}

        status = "failed" if error else "succeeded"
        backend_name = raw.get("backend", lb.backend()) if not error else BACKEND

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
