"""Q12 complete energy balance, ratio screening, and MATSUM part dissipation.

Evaluates:
- Total energy, kinetic, internal, hourglass, sliding interface, external work, damping, eroded energy;
- Energy balance residual time series and relative error;
- Hourglass/internal and kinetic/internal screening ratios;
- Part-level (MATSUM) energy and dissipation breakdown;
- Caller-specified screening thresholds (no pass/fail conclusion asserted without thresholds).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np


class EnergyBalanceError(ValueError):
    """Raised when energy balance data is invalid, nonfinite, or cannot be read."""


def read_ascii_glstat(path: str | Path) -> dict[str, np.ndarray]:
    """Parse LS-DYNA ASCII glstat file into dictionary of energy time arrays."""
    path = Path(path)
    if not path.is_file():
        raise EnergyBalanceError(f"glstat file not found: {path}")

    # Standard glstat column positions (varies slightly by format, so we match headers or standard layouts)
    times, ke, ie, hg, se, ew, de, ee, te = [], [], [], [], [], [], [], [], []

    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith(("$", "#")):
                continue
            tokens = stripped.split()
            try:
                values = [float(t.replace("D", "E").replace("d", "e")) for t in tokens]
            except ValueError:
                continue

            if len(values) < 8:
                continue

            times.append(values[0])
            ke.append(values[1])
            ie.append(values[2])
            # Common LS-DYNA layout: time, kinetic, internal, spring, hourglass, damping, sliding, external_work, ...
            if len(values) >= 12:
                hg.append(values[4])
                de.append(values[5])
                se.append(values[6])
                ew.append(values[7])
                # eroded kin + int + hg
                eroded = values[8] + values[9] + values[10]
                ee.append(eroded)
                te.append(values[11])
            elif len(values) >= 9:
                hg.append(values[4])
                de.append(values[5])
                se.append(values[6])
                ew.append(values[7])
                ee.append(0.0)
                te.append(values[8])
            else:
                hg.append(values[3])
                se.append(0.0)
                ew.append(values[4] if len(values) > 4 else 0.0)
                de.append(0.0)
                ee.append(0.0)
                te.append(values[1] + values[2] + values[3])

    if not times:
        raise EnergyBalanceError(f"No numeric rows in glstat file {path}")

    return {
        "time": np.asarray(times, dtype=float),
        "kinetic_energy": np.asarray(ke, dtype=float),
        "internal_energy": np.asarray(ie, dtype=float),
        "hourglass_energy": np.asarray(hg, dtype=float),
        "sliding_energy": np.asarray(se, dtype=float),
        "external_work": np.asarray(ew, dtype=float),
        "damping_energy": np.asarray(de, dtype=float),
        "eroded_energy": np.asarray(ee, dtype=float),
        "total_energy": np.asarray(te, dtype=float),
    }


def _open_binout(path: str | Path):
    from lasso.dyna import Binout
    p = Path(path)
    if p.is_dir():
        pattern = str(p / "binout*")
        return Binout(pattern)
    return Binout(str(p))


def read_binout_glstat(path: str | Path) -> dict[str, np.ndarray]:
    """Read glstat database from binout file or directory using lasso."""
    b = _open_binout(path)
    try:
        time_arr = np.asarray(b.read("glstat", "time"), dtype=float).reshape(-1)
    except Exception as e:
        raise EnergyBalanceError(f"Could not read glstat time from {path}") from e

    zeros = np.zeros_like(time_arr)

    def fetch(name: str) -> np.ndarray:
        try:
            val = b.read("glstat", name)
            if val is not None and len(val) > 0:
                arr = np.asarray(val, dtype=float).reshape(-1)
                if arr.shape == time_arr.shape:
                    return arr
        except Exception:
            pass
        return zeros

    ke = fetch("kinetic_energy")
    ie = fetch("internal_energy")
    hg = fetch("hourglass_energy")
    se = fetch("sliding_interface_energy")
    if not np.any(se):
        se = fetch("sliding_energy")
    ew = fetch("external_work")
    de = fetch("system_damping_energy")
    if not np.any(de):
        de = fetch("damping_energy")

    eke = fetch("eroded_kinetic_energy")
    eie = fetch("eroded_internal_energy")
    ehg = fetch("eroded_hourglass_energy")
    ee = eke + eie + ehg

    te = fetch("total_energy")
    if not np.any(te):
        te = ke + ie + hg + se + de + ee

    return {
        "time": time_arr,
        "kinetic_energy": ke,
        "internal_energy": ie,
        "hourglass_energy": hg,
        "sliding_energy": se,
        "external_work": ew,
        "damping_energy": de,
        "eroded_energy": ee,
        "total_energy": te,
    }


def read_binout_matsum(path: str | Path) -> dict[int, dict[str, np.ndarray]]:
    """Read matsum database from binout file or directory."""
    try:
        b = _open_binout(path)
        time_raw = b.read("matsum", "time")
        if time_raw is None:
            return {}
        time_arr = np.asarray(time_raw, dtype=float).reshape(-1)
        ids_raw = b.read("matsum", "ids")
        if ids_raw is None:
            ids_raw = b.read("matsum", "mat_ids")
        if ids_raw is None:
            ids_raw = [1]
        part_ids = [int(p) for p in np.asarray(ids_raw).reshape(-1)]

        zeros = np.zeros((len(time_arr), len(part_ids)), dtype=float)

        def fetch_mat(comp: str) -> np.ndarray:
            try:
                v = b.read("matsum", comp)
                if v is not None and len(v) > 0:
                    arr = np.asarray(v, dtype=float)
                    if arr.ndim == 1:
                        arr = arr[:, None]
                    if arr.shape == zeros.shape:
                        return arr
            except Exception:
                pass
            return zeros

        ie_val = fetch_mat("internal_energy")
        ke_val = fetch_mat("kinetic_energy")
        hg_val = fetch_mat("hourglass_energy")
        eie_val = fetch_mat("eroded_internal_energy")

        parts: dict[int, dict[str, np.ndarray]] = {}
        for idx, pid in enumerate(part_ids):
            parts[pid] = {
                "time": time_arr,
                "internal_energy": ie_val[:, idx],
                "kinetic_energy": ke_val[:, idx],
                "hourglass_energy": hg_val[:, idx],
                "eroded_internal_energy": eie_val[:, idx],
            }
        return parts
    except Exception:
        return {}


def read_glstat(path: str | Path) -> dict[str, np.ndarray]:
    """Read glstat data from either binout or ASCII file, auto-detecting format."""
    p = Path(path)
    if p.is_dir() or "binout" in p.name.lower():
        try:
            return read_binout_glstat(p)
        except Exception as e:
            if p.is_file():
                return read_ascii_glstat(p)
            raise e
    else:
        return read_ascii_glstat(p)


def calculate_energy_balance(
    energies: dict[str, np.ndarray],
    parts: dict[int, dict[str, np.ndarray]] | None = None,
    units: str = "J",
    kinetic_ratio_limit: float | None = None,
    hourglass_ratio_limit: float | None = None,
    residual_ratio_limit: float | None = None,
    sliding_ratio_limit: float | None = None,
) -> dict:
    """Core energy balance computation and threshold evaluation.

    If thresholds are None, reports ratios and maximums without asserting a pass/fail conclusion.
    """
    time = np.asarray(energies["time"], dtype=float)
    if len(time) < 1:
        raise EnergyBalanceError("Energy histories must contain at least one state")

    ke = np.asarray(energies["kinetic_energy"], dtype=float)
    ie = np.asarray(energies["internal_energy"], dtype=float)
    hg = np.asarray(energies["hourglass_energy"], dtype=float)
    se = np.asarray(energies["sliding_energy"], dtype=float)
    ew = np.asarray(energies["external_work"], dtype=float)
    de = np.asarray(energies["damping_energy"], dtype=float)
    ee = np.asarray(energies["eroded_energy"], dtype=float)
    te = np.asarray(energies["total_energy"], dtype=float)

    # Validate finite values
    for name, arr in (("time", time), ("ke", ke), ("ie", ie), ("hg", hg),
                     ("se", se), ("ew", ew), ("de", de), ("ee", ee), ("te", te)):
        if not np.isfinite(arr).all():
            raise EnergyBalanceError(f"Nonfinite values detected in {name}")

    # Energy balance residual: Delta(Total Energy) - Delta(External Work)
    # Physical relation: E_total(t) - E_total(0) = W_ext(t) - W_ext(0)
    delta_te = te - te[0]
    delta_ew = ew - ew[0]
    residual = delta_te - delta_ew

    denom_scale = np.maximum.reduce([np.abs(te), np.abs(ew), np.abs(ie), np.full_like(te, 1e-12)])
    relative_residual = np.abs(residual) / denom_scale
    max_relative_residual = float(np.max(relative_residual))
    max_residual = float(np.max(np.abs(residual)))
    final_residual = float(residual[-1])

    # Screening ratios (against internal energy)
    floor = max(float(np.max(np.abs(ie))) * 1e-12, np.finfo(float).tiny)
    defined_ie = np.abs(ie) > floor

    ke_ratio = np.divide(np.abs(ke), np.abs(ie), out=np.zeros_like(ke), where=defined_ie)
    hg_ratio = np.divide(np.abs(hg), np.abs(ie), out=np.zeros_like(hg), where=defined_ie)
    se_ratio = np.divide(np.abs(se), np.abs(ie), out=np.zeros_like(se), where=defined_ie)

    max_ke_ratio = float(np.max(ke_ratio[defined_ie])) if np.any(defined_ie) else 0.0
    final_ke_ratio = float(ke_ratio[-1]) if defined_ie[-1] else 0.0

    max_hg_ratio = float(np.max(hg_ratio[defined_ie])) if np.any(defined_ie) else 0.0
    final_hg_ratio = float(hg_ratio[-1]) if defined_ie[-1] else 0.0

    max_se_ratio = float(np.max(se_ratio[defined_ie])) if np.any(defined_ie) else 0.0
    min_se = float(np.min(se))
    negative_sliding_detected = bool(min_se < -floor)

    # Threshold checks
    def check_limit(val: float, limit: float | None, series: np.ndarray, mask: np.ndarray) -> dict:
        if limit is None:
            return {"limit": None, "max_ratio": float(val), "exceedances": None, "passed": None}
        if not (math.isfinite(limit) and limit >= 0):
            raise EnergyBalanceError(f"Screening limit must be finite nonnegative number: {limit}")
        exceedances = int(np.count_nonzero((series > limit) & mask))
        return {
            "limit": float(limit),
            "max_ratio": float(val),
            "exceedances": exceedances,
            "passed": bool(exceedances == 0),
        }

    ke_check = check_limit(max_ke_ratio, kinetic_ratio_limit, ke_ratio, defined_ie)
    hg_check = check_limit(max_hg_ratio, hourglass_ratio_limit, hg_ratio, defined_ie)
    res_check = check_limit(max_relative_residual, residual_ratio_limit, relative_residual, np.ones_like(defined_ie, dtype=bool))
    se_check = check_limit(max_se_ratio, sliding_ratio_limit, se_ratio, defined_ie)

    thresholds_provided = any(x is not None for x in (kinetic_ratio_limit, hourglass_ratio_limit, residual_ratio_limit, sliding_ratio_limit))
    if thresholds_provided:
        all_passed = True
        for chk in (ke_check, hg_check, res_check, se_check):
            if chk["passed"] is False:
                all_passed = False
        verdict = "passed" if all_passed else "exceeded"
    else:
        all_passed = None
        verdict = "metrics_only_no_thresholds"

    # Part-level dissipation breakdown (MATSUM)
    part_breakdown = {}
    if parts:
        final_global_ie = float(ie[-1]) if ie[-1] != 0 else 1.0
        for pid, pdata in parts.items():
            pie = np.asarray(pdata["internal_energy"], dtype=float)
            phg = np.asarray(pdata["hourglass_energy"], dtype=float)
            pke = np.asarray(pdata["kinetic_energy"], dtype=float)
            peie = np.asarray(pdata.get("eroded_internal_energy", np.zeros_like(pie)), dtype=float)

            p_floor = max(float(np.max(np.abs(pie))) * 1e-12, np.finfo(float).tiny)
            p_defined = np.abs(pie) > p_floor
            p_hg_ratio = np.divide(np.abs(phg), np.abs(pie), out=np.zeros_like(phg), where=p_defined)

            part_breakdown[int(pid)] = {
                "part_id": int(pid),
                "peak_internal_energy": float(np.max(pie)),
                "final_internal_energy": float(pie[-1]),
                "fraction_of_total_internal_energy": float(pie[-1] / final_global_ie) if final_global_ie else 0.0,
                "peak_hourglass_energy": float(np.max(phg)),
                "final_hourglass_energy": float(phg[-1]),
                "max_part_hourglass_ratio": float(np.max(p_hg_ratio[p_defined])) if np.any(p_defined) else 0.0,
                "peak_kinetic_energy": float(np.max(pke)),
                "final_eroded_internal_energy": float(peie[-1]),
            }

    summary = {
        "units": units,
        "sample_count": int(len(time)),
        "time_range": [float(time[0]), float(time[-1])],
        "energy_budget": {
            "initial_total_energy": float(te[0]),
            "final_total_energy": float(te[-1]),
            "peak_total_energy": float(np.max(te)),
            "peak_kinetic_energy": float(np.max(ke)),
            "final_kinetic_energy": float(ke[-1]),
            "peak_internal_energy": float(np.max(ie)),
            "final_internal_energy": float(ie[-1]),
            "peak_hourglass_energy": float(np.max(hg)),
            "final_hourglass_energy": float(hg[-1]),
            "peak_sliding_energy": float(np.max(se)),
            "min_sliding_energy": min_se,
            "final_sliding_energy": float(se[-1]),
            "negative_sliding_detected": negative_sliding_detected,
            "peak_external_work": float(np.max(ew)),
            "final_external_work": float(ew[-1]),
            "peak_damping_energy": float(np.max(de)),
            "final_damping_energy": float(de[-1]),
            "peak_eroded_energy": float(np.max(ee)),
            "final_eroded_energy": float(ee[-1]),
        },
        "balance_residual": {
            "max_absolute_residual": max_residual,
            "final_absolute_residual": final_residual,
            "max_relative_residual": max_relative_residual,
        },
        "screening_ratios": {
            "max_kinetic_ratio": max_ke_ratio,
            "final_kinetic_ratio": final_ke_ratio,
            "max_hourglass_ratio": max_hg_ratio,
            "final_hourglass_ratio": final_hg_ratio,
            "max_sliding_ratio": max_se_ratio,
        },
        "checks": {
            "kinetic_energy": ke_check,
            "hourglass_energy": hg_check,
            "energy_balance": res_check,
            "sliding_energy": se_check,
        },
        "verdict": verdict,
        "passed": all_passed,
        "parts": part_breakdown,
        "parts_analyzed": len(part_breakdown),
    }

    # Prepare time-series rows for CSV export
    rows = []
    for i in range(len(time)):
        rows.append([
            float(time[i]),
            float(te[i]),
            float(ke[i]),
            float(ie[i]),
            float(hg[i]),
            float(se[i]),
            float(ew[i]),
            float(de[i]),
            float(ee[i]),
            float(residual[i]),
            float(relative_residual[i]),
            float(ke_ratio[i]),
            float(hg_ratio[i]),
        ])

    return {"summary": summary, "series_rows": rows}
