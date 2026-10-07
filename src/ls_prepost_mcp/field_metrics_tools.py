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
        state: int = -1,
        mask: str = "alive",
        units: str | None = None,
        output_format: str = "csv",
    ) -> dict[str, Any]:
        """Extract an element field or compute stress invariants with failure masking (tasks.yaml Q04).

        Supports 'solid', 'shell', and 'tshell' element families.
        Quantities include:
        - von_mises, mean_stress, pressure, triaxiality
        - principal_1, principal_2, principal_3, max_shear
        - lode_parameter, lode_angle_rad, lode_angle_parameter
        - effective_plastic_strain
        - stress components: sxx, syy, szz, sxy, syz, szx
        Mask options: 'alive' (default), 'all', 'deleted'.
        Returns JobResult/v1 with extrema (including element ID and state), formula conventions, and CSV/NPZ artifacts.
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

        if not isinstance(state, int):
            raise ValueError(f"State must be an integer, got {type(state).__name__}")

        if units is not None and not isinstance(units, str):
            raise ValueError("Units must be a string or None")

        source = self.settings.input_path(path)

        parameters = {
            "path": str(source),
            "family": norm_family,
            "quantity": norm_quantity,
            "state": state,
            "mask": norm_mask,
            "units": units,
            "output_format": norm_fmt,
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
            raw = lb.field(source, norm_family, norm_quantity, state=state, mask=norm_mask)

            state_idx = int(raw["state"])
            state_time = float(raw["time"])

            raw_ext = raw.get("extrema") or {"count": 0, "min": None, "max": None}
            min_info = raw_ext.get("min")
            max_info = raw_ext.get("max")
            extrema = {
                "count": int(raw_ext.get("count", 0)),
                "min": {**min_info, "state": state_idx, "state_1based": state_idx + 1} if min_info is not None else None,
                "max": {**max_info, "state": state_idx, "state_1based": state_idx + 1} if max_info is not None else None,
            }
            raw["extrema"] = extrema

            declared_units = units if (units and units.strip()) else "model units, not converted (unit system not declared)"

            if norm_fmt in ("csv", "both", "all"):
                csv_file = directory / f"{norm_family}_{norm_quantity}_state_{state_idx}.csv"
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
                npz_file = directory / f"{norm_family}_{norm_quantity}_state_{state_idx}.npz"
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

            formula = inv.CONVENTIONS.get(norm_quantity, "stored or IP-averaged value")

            data = {
                "backend": raw.get("backend", lb.backend()),
                "family": norm_family,
                "quantity": norm_quantity,
                "state": state_idx,
                "state_1based": state_idx + 1,
                "time": state_time,
                "units": declared_units,
                "mask": norm_mask,
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
            data = {"path": str(source), "family": norm_family, "quantity": norm_quantity, "state": state, "mask": norm_mask}

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
