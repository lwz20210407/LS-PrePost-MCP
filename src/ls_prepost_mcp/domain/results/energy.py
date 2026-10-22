"""Q12 energy metrics with explicit missing data and dimensionless screening."""
from __future__ import annotations

import math

import numpy as np

ENERGIES = ("total_energy", "kinetic_energy", "internal_energy", "hourglass_energy", "sliding_energy",
            "external_work", "damping_energy", "eroded_energy", "stonewall_energy", "drilling_energy",
            "spring_and_damper_energy", "joint_internal_energy", "rigid_body_stopper_energy",
            "eroded_kinetic_energy", "eroded_internal_energy", "eroded_hourglass_energy")
PART_FIELDS = ("kinetic_energy", "internal_energy", "hourglass_energy", "eroded_kinetic_energy",
               "eroded_internal_energy", "eroded_hourglass_energy")
SERIES_HEADER = ("time", *ENERGIES[:8], "balance_residual", "relative_residual", "kinetic_ratio", "hourglass_ratio")
PART_HEADER = ("time", "part_id", *PART_FIELDS)
MAX_ROWS = 1_000_000


class EnergyBalanceError(ValueError):
    """The supplied records cannot support the requested energy calculation."""


def column(value, n, name):
    if value is None:
        return np.full(n, np.nan)
    raw = np.asarray(value, dtype=object)
    if raw.shape != (n,):
        raise EnergyBalanceError(f"{name}: expected {n} aligned scalar values")
    values = np.array([np.nan if v is None else float(v) for v in raw])
    if any(v is not None and not math.isfinite(float(v)) for v in raw):
        raise EnergyBalanceError(f"Nonfinite source values in {name}")
    return values


def nullable(values):
    return [float(v) if np.isfinite(v) else None for v in values]


def maximum(values):
    valid = values[np.isfinite(values)]
    return float(valid.max()) if valid.size else None


def _ratio(numerator, denominator, floor):
    peak = maximum(np.abs(denominator))
    valid = np.isfinite(numerator) & np.isfinite(denominator) & (np.abs(denominator) > 0)
    if peak is not None:
        valid &= np.abs(denominator) >= floor * peak
    out = np.full(len(denominator), np.nan)
    np.divide(np.abs(numerator), np.abs(denominator), out=out, where=valid)
    return out, {"defined_samples": int(valid.sum()), "undefined_samples": int((~valid).sum())}


def calculate_energy_balance(energies, parts=None, units="model_units", kinetic_ratio_limit=None,
                             hourglass_ratio_limit=None, residual_ratio_limit=None, sliding_ratio_limit=None,
                             ratio_floor=1e-3, relative_floor=1e-12):
    """Return metrics, nullable CSV rows and checks; never infer absent energies as zero.

    Energy balance uses measured TE and external work only. Erosion is reported
    separately, never added again to the measured total. Units are declarations.
    """
    limits = dict(kinetic_energy=kinetic_ratio_limit, hourglass_energy=hourglass_ratio_limit,
                  sliding_energy=sliding_ratio_limit, energy_balance=residual_ratio_limit)
    validate_parameters(units, limits, ratio_floor, relative_floor)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _calculate(energies, parts or {}, units, limits, ratio_floor, relative_floor)
    except FloatingPointError as error:
        raise EnergyBalanceError(f"Nonfinite derived energy metric: {error}") from error


def validate_parameters(units, limits, ratio_floor, relative_floor):
    """Validate screening options before a tool reads or creates any files."""
    for name, value in limits.items():
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            raise EnergyBalanceError(f"{name}: threshold must be a nonnegative finite number or None")
    for name, value in (("ratio_floor", ratio_floor), ("relative_floor", relative_floor)):
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value < 1:
            raise EnergyBalanceError(f"{name} must be a finite fraction in [0, 1)")
    if not isinstance(units, str) or not units.strip():
        raise EnergyBalanceError("Explicit energy unit label required")


def _calculate(energies, parts, units, limits, ratio_floor, relative_floor):
    time = np.asarray(energies.get("time"), dtype=float)
    if time.ndim != 1 or not time.size or time.size > MAX_ROWS or not np.isfinite(time).all():
        raise EnergyBalanceError("Energy time must be a nonempty finite vector within the CSV row limit")
    n = len(time)
    if sum(len(part.get("time", [])) for part in parts.values()) > MAX_ROWS:
        raise EnergyBalanceError("MATSUM export exceeds one million rows")
    monotonic = bool(np.all(np.diff(time) > 0))
    warnings = [] if monotonic else ["Nonmonotonic energy time axis; screening is incomplete"]
    values = {key: column(energies.get(key), n, key) for key in ENERGIES}
    # Derive the erosion total only if all three recorded components exist at that sample.
    erosion = values["eroded_energy"]
    components = [values[key] for key in ENERGIES[-3:]]
    available = np.all(np.isfinite(components), axis=0)
    derive = ~np.isfinite(erosion) & available
    if derive.any():
        erosion[derive] = sum(component[derive] for component in components)
    for key, array in values.items():
        missing = int((~np.isfinite(array)).sum())
        if missing:
            warnings.append(f"{key}: {missing}/{n} samples not recorded; preserved as null")
    ratios, defined = {}, {}
    for key in ("kinetic_energy", "hourglass_energy", "sliding_energy"):
        ratios[key], defined[key] = _ratio(values[key], values["internal_energy"], ratio_floor)
    te, work = values["total_energy"], values["external_work"]
    residual, relative = np.full(n, np.nan), np.full(n, np.nan)
    complete = bool(np.isfinite(te).all() and np.isfinite(work).all())
    if complete:
        expected = te[0] + (work - work[0])
        residual = te - expected
        denominator = np.maximum(np.abs(expected), np.max(np.abs(te)))
        reference = max(float(np.max(np.abs(te))), float(np.max(np.abs(expected))))
        valid = (denominator > 0) & (denominator >= relative_floor * reference)
        np.divide(np.abs(residual), denominator, out=relative, where=valid)
    checks = {}
    for key, limit in limits.items():
        metric = relative if key == "energy_balance" else ratios[key]
        needed = (te, work) if key == "energy_balance" else (values[key], values["internal_energy"])
        usable = monotonic and all(np.isfinite(a).all() for a in needed) and np.isfinite(metric).any()
        if key == "energy_balance":
            usable &= n >= 2
        peak = maximum(metric)
        status = "not_applicable" if limit is None or not usable else ("passed" if peak <= limit else "failed")
        checks[key] = dict(status=status, passed=None if status == "not_applicable" else status == "passed",
                           limit=limit, maximum=peak)
        if limit is not None and not usable:
            warnings.append(f"{key}: requested threshold not applicable to incomplete/undefined measurements")
    requested = [c for c in checks.values() if c["limit"] is not None]
    verdict, passed = "metrics_only_no_thresholds", None
    if any(c["status"] == "failed" for c in requested):
        verdict, passed = "exceeded", False
    elif requested:
        verdict = "passed" if all(c["status"] == "passed" for c in requested) else "incomplete"
        passed = True if verdict == "passed" else None
    budgets = {}
    for key, array in values.items():
        budgets["peak_" + key] = maximum(array)
        budgets["final_" + key] = nullable(array[-1:])[0]
    sliding = values["sliding_energy"]
    if np.any(sliding < 0):
        warnings.append("Negative sliding_energy values recorded; inspect contact behaviour")
    part_summaries, part_rows = {}, []
    for pid, part in parts.items():
        if type(pid) not in (int, str) or not str(pid).isdigit() or int(pid) < 1:
            raise EnergyBalanceError("MATSUM requires positive stored part IDs")
        pt = np.asarray(part.get("time"), dtype=float)
        if pt.ndim != 1 or not pt.size or not np.isfinite(pt).all() or not np.all(np.diff(pt) > 0):
            raise EnergyBalanceError(f"MATSUM part {pid}: invalid time axis")
        pv = {key: column(part.get(key), len(pt), f"MATSUM {pid} {key}") for key in PART_FIELDS}
        for key, array in pv.items():
            if not np.isfinite(array).all():
                warnings.append(f"MATSUM part {pid}: {key} missing samples preserved as null")
        pr, pd = _ratio(pv["hourglass_energy"], pv["internal_energy"], ratio_floor)
        part_budget = {"peak_" + key: maximum(array) for key, array in pv.items()}
        part_budget.update({"final_" + key: nullable(array[-1:])[0] for key, array in pv.items()})
        part_summaries[str(pid)] = dict(part_id=int(pid), sample_count=len(pt),
            time_range=[float(pt[0]), float(pt[-1])], energy_budget=part_budget,
            missing_samples={key: int((~np.isfinite(array)).sum()) for key, array in pv.items()},
            max_hourglass_ratio=maximum(pr), ratio_defined=pd)
        part_rows.extend([[float(t), int(pid), *row] for t, row in zip(pt, zip(*(nullable(v) for v in pv.values())))])
    summary = dict(units=units, sample_count=n, time_range=[float(time[0]), float(time[-1])],
        verdict=verdict, passed=passed, checks=checks, warnings=warnings, time_monotonic=monotonic,
        screening_ratios={"max_kinetic_energy_ratio": maximum(ratios["kinetic_energy"]),
                          "max_hourglass_ratio": maximum(ratios["hourglass_energy"]),
                          "max_sliding_energy_ratio": maximum(ratios["sliding_energy"])},
        ratio_defined=defined, ratio_floor=ratio_floor, relative_floor=relative_floor,
        balance_residual=dict(max_absolute_residual=maximum(np.abs(residual)),
            max_relative_residual=maximum(relative), final_residual=nullable(residual[-1:])[0],
            residual_denominator="max(abs(TE0 + (W(t)-W0)), max_t abs(TE))",
            formula="TE(t) - TE(0) - (W(t)-W(0))", undefined_samples=int((~np.isfinite(relative)).sum())),
        energy_budget=budgets, missing_samples={key: int((~np.isfinite(array)).sum()) for key, array in values.items()},
        peak_policy="algebraic maxima of recorded samples; missing samples are not bounds",
        parts_analyzed=len(part_summaries), parts=part_summaries)
    rows = [[float(t), *row] for t, row in zip(time, zip(*(nullable(values[k]) for k in ENERGIES[:8]),
                nullable(residual), nullable(relative), nullable(ratios["kinetic_energy"]),
                nullable(ratios["hourglass_energy"])))]
    return dict(summary=summary, series_rows=rows, part_series_rows=part_rows, warnings=warnings)
