"""Q12 complete energy balance, ratio screening, and MATSUM part dissipation.

Evaluates:
- Total energy, kinetic, internal, hourglass, sliding interface, external work, damping, eroded, and stonewall energies;
- Energy balance residual time series, relative residual, and energy closure error;
- Hourglass/internal and kinetic/internal screening ratios;
- Part-level (MATSUM) energy breakdown and sum-of-parts vs GLSTAT discrepancy;
- Caller-specified screening thresholds (no pass/fail conclusion asserted without thresholds).
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from . import mpp_shards
from .lasso_backend import ResultsError, _lasso


class EnergyBalanceError(ValueError):
    """Raised when energy balance data is invalid, nonfinite, or cannot be read."""


GLSTAT_LINE_PATTERN = re.compile(
    r"^\s*([a-zA-Z0-9_ /()#]+?)\s*(?:\.{2,}|:)\s*([+-]?\d+(?:\.\d+)?(?:[eEdD][+-]?\d+)?)\s*(.*)$"
)


def read_ascii_glstat(path: str | Path) -> dict[str, np.ndarray | None]:
    """Parse LS-DYNA ASCII glstat file into dictionary of energy time arrays.

    Robustly handles block-formatted key...value pairs across standard LS-DYNA
    versions (one block per time state), as well as legacy columnar data.
    Missing quantities remain None rather than being filled with zero.
    """
    path = Path(path)
    if not path.is_file():
        raise EnergyBalanceError(f"glstat file not found: {path}")

    # Step 1: Attempt block-based parsing
    times: list[float] = []
    ke: list[float] = []
    ie: list[float] = []
    hg: list[float] = []
    se: list[float] = []
    ew: list[float] = []
    de: list[float] = []
    eroded_ke: list[float] = []
    eroded_ie: list[float] = []
    eroded_hg: list[float] = []
    te: list[float] = []
    stonewall: list[float] = []
    spring_damper: list[float] = []
    added_mass: list[float] = []
    percent_increase: list[float] = []

    has_ke = False
    has_ie = False
    has_hg = False
    has_se = False
    has_ew = False
    has_de = False
    has_eroded = False
    has_te = False
    has_stonewall = False
    has_spring_damper = False
    has_added_mass = False
    has_percent_increase = False

    current_step: dict[str, float] = {}

    def commit_block(step: dict[str, float]) -> None:
        if "time" not in step:
            return
        times.append(step["time"])
        ke.append(step.get("kinetic_energy", 0.0))
        ie.append(step.get("internal_energy", 0.0))
        hg.append(step.get("hourglass_energy", 0.0))
        se.append(step.get("sliding_energy", 0.0))
        ew.append(step.get("external_work", 0.0))
        de.append(step.get("damping_energy", 0.0))
        eroded_ke.append(step.get("eroded_kinetic_energy", 0.0))
        eroded_ie.append(step.get("eroded_internal_energy", 0.0))
        eroded_hg.append(step.get("eroded_hourglass_energy", 0.0))
        te.append(step.get("total_energy", 0.0))
        stonewall.append(step.get("stonewall_energy", 0.0))
        spring_damper.append(step.get("spring_and_damper_energy", 0.0))
        added_mass.append(step.get("added_mass", 0.0))
        percent_increase.append(step.get("percent_increase", 0.0))

    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith(("$", "#")):
                continue

            match = GLSTAT_LINE_PATTERN.match(line)
            if match:
                key = match.group(1).strip().lower()
                val_str = match.group(2).replace("D", "E").replace("d", "e")
                suffix = match.group(3).strip().lower()
                try:
                    val = float(val_str)
                except ValueError:
                    continue

                if key == "time":
                    commit_block(current_step)
                    current_step = {"time": val}
                elif key == "kinetic energy":
                    current_step["kinetic_energy"] = val
                    has_ke = True
                elif key == "internal energy":
                    current_step["internal_energy"] = val
                    has_ie = True
                elif key in ("hourglass energy", "drilling energy"):
                    current_step["hourglass_energy"] = current_step.get("hourglass_energy", 0.0) + val
                    has_hg = True
                elif key in ("sliding interface energy", "sliding energy"):
                    current_step["sliding_energy"] = val
                    has_se = True
                elif key == "external work":
                    current_step["external_work"] = val
                    has_ew = True
                elif key in ("system damping energy", "damping energy"):
                    current_step["damping_energy"] = val
                    has_de = True
                elif key == "eroded kinetic energy":
                    current_step["eroded_kinetic_energy"] = val
                    has_eroded = True
                elif key == "eroded internal energy":
                    current_step["eroded_internal_energy"] = val
                    has_eroded = True
                elif key == "eroded hourglass energy":
                    current_step["eroded_hourglass_energy"] = val
                    has_eroded = True
                elif key == "total energy":
                    current_step["total_energy"] = val
                    has_te = True
                elif "stonewall" in key or "wall#" in key or "wall#" in suffix:
                    current_step["stonewall_energy"] = current_step.get("stonewall_energy", 0.0) + val
                    has_stonewall = True
                elif "spring" in key and "damper" in key:
                    current_step["spring_and_damper_energy"] = val
                    has_spring_damper = True
                elif key == "added mass":
                    current_step["added_mass"] = val
                    has_added_mass = True
                elif key in ("percent increase", "percentage increase"):
                    current_step["percent_increase"] = val
                    has_percent_increase = True

        commit_block(current_step)

    # If block parsing succeeded and found at least one time step
    if times:
        t_arr = np.asarray(times, dtype=float)
        ee_arr = (
            np.asarray(eroded_ke, dtype=float) + np.asarray(eroded_ie, dtype=float) + np.asarray(eroded_hg, dtype=float)
            if has_eroded
            else None
        )
        return {
            "time": t_arr,
            "kinetic_energy": np.asarray(ke, dtype=float) if has_ke else None,
            "internal_energy": np.asarray(ie, dtype=float) if has_ie else None,
            "hourglass_energy": np.asarray(hg, dtype=float) if has_hg else None,
            "sliding_energy": np.asarray(se, dtype=float) if has_se else None,
            "external_work": np.asarray(ew, dtype=float) if has_ew else None,
            "damping_energy": np.asarray(de, dtype=float) if has_de else None,
            "eroded_energy": ee_arr,
            "total_energy": np.asarray(te, dtype=float) if has_te else None,
            "stonewall_energy": np.asarray(stonewall, dtype=float) if has_stonewall else None,
            "spring_and_damper_energy": np.asarray(spring_damper, dtype=float) if has_spring_damper else None,
            "added_mass": np.asarray(added_mass, dtype=float) if has_added_mass else None,
            "percent_increase": np.asarray(percent_increase, dtype=float) if has_percent_increase else None,
        }

    # Step 2: Fallback to space-separated tabular format (for simplified test files)
    t_list, ke_list, ie_list, hg_list, se_list, ew_list, de_list, ee_list, te_list = (
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    )
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

            t_list.append(values[0])
            ke_list.append(values[1])
            ie_list.append(values[2])
            if len(values) >= 12:
                hg_list.append(values[4])
                de_list.append(values[5])
                se_list.append(values[6])
                ew_list.append(values[7])
                eroded = values[8] + values[9] + values[10]
                ee_list.append(eroded)
                te_list.append(values[11])
            elif len(values) >= 9:
                hg_list.append(values[4])
                de_list.append(values[5])
                se_list.append(values[6])
                ew_list.append(values[7])
                ee_list.append(0.0)
                te_list.append(values[8])
            else:
                hg_list.append(values[3])
                se_list.append(0.0)
                ew_list.append(values[4] if len(values) > 4 else 0.0)
                de_list.append(0.0)
                ee_list.append(0.0)
                te_list.append(values[1] + values[2] + values[3])

    if not t_list:
        raise EnergyBalanceError(f"No numeric rows or recognizable glstat blocks in {path}")

    return {
        "time": np.asarray(t_list, dtype=float),
        "kinetic_energy": np.asarray(ke_list, dtype=float),
        "internal_energy": np.asarray(ie_list, dtype=float),
        "hourglass_energy": np.asarray(hg_list, dtype=float),
        "sliding_energy": np.asarray(se_list, dtype=float),
        "external_work": np.asarray(ew_list, dtype=float),
        "damping_energy": np.asarray(de_list, dtype=float),
        "eroded_energy": np.asarray(ee_list, dtype=float),
        "total_energy": np.asarray(te_list, dtype=float),
        "stonewall_energy": None,
        "spring_and_damper_energy": None,
        "added_mass": None,
        "percent_increase": None,
    }


def read_binout_glstat(path: str | Path) -> dict[str, np.ndarray | None]:
    """Read glstat database from binout file or directory.

    Accesses through mpp_shards.read for MPP shard awareness.
    If path points to a non-standard single binout file, accesses directly
    via lasso_backend reader without globbing.
    Missing quantities return None rather than being filled with zero.
    """
    p = Path(path)
    if not p.exists():
        raise EnergyBalanceError(f"glstat path not found: {p}")

    use_mpp = True
    single_binout = None
    try:
        mpp_shards.shards(p)
    except ResultsError:
        if p.is_file():
            use_mpp = False
            _, Binout, _ = _lasso()
            try:
                single_binout = Binout(str(p))
            except Exception as e:
                raise EnergyBalanceError(f"Failed to open binout file {p}: {e}") from e
        else:
            raise

    # Extract time series
    time_arr: np.ndarray | None = None
    if use_mpp:
        try:
            res = mpp_shards.read(p, "glstat", "time")
            time_arr = np.asarray(res["time"], dtype=float).reshape(-1)
        except ResultsError as e:
            raise EnergyBalanceError(f"No glstat time array found in {p}: {e}") from e
    else:
        try:
            t_raw = single_binout.read("glstat", "time")
            if t_raw is None or len(t_raw) == 0:
                raise EnergyBalanceError(f"No glstat time array in {p}")
            time_arr = np.asarray(t_raw, dtype=float).reshape(-1)
        except Exception as e:
            raise EnergyBalanceError(f"Could not read glstat time from {p}: {e}") from e

    def fetch(comp: str) -> np.ndarray | None:
        if use_mpp:
            try:
                res = mpp_shards.read(p, "glstat", comp)
                arr = np.asarray(res["values"], dtype=float).reshape(-1)
                if arr.shape == time_arr.shape:
                    return arr
            except ResultsError:
                return None
        else:
            try:
                val = single_binout.read("glstat", comp)
                if val is not None and len(val) > 0:
                    arr = np.asarray(val, dtype=float).reshape(-1)
                    if arr.shape == time_arr.shape:
                        return arr
            except Exception:
                pass
        return None

    ke = fetch("kinetic_energy")
    ie = fetch("internal_energy")
    hg = fetch("hourglass_energy")
    se = fetch("sliding_interface_energy")
    if se is None:
        se = fetch("sliding_energy")
    ew = fetch("external_work")
    de = fetch("system_damping_energy")
    if de is None:
        de = fetch("damping_energy")

    eke = fetch("eroded_kinetic_energy")
    eie = fetch("eroded_internal_energy")
    ehg = fetch("eroded_hourglass_energy")
    if eke is not None or eie is not None or ehg is not None:
        ee = (
            (eke if eke is not None else 0.0)
            + (eie if eie is not None else 0.0)
            + (ehg if ehg is not None else 0.0)
        )
    else:
        ee = None

    te = fetch("total_energy")
    stonewall = fetch("stonewall_energy")
    spring_damper = fetch("spring_and_damper_energy")
    added_mass = fetch("added_mass")
    percent_increase = fetch("percent_increase")

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
        "stonewall_energy": stonewall,
        "spring_and_damper_energy": spring_damper,
        "added_mass": added_mass,
        "percent_increase": percent_increase,
    }


def read_ascii_matsum(path: str | Path) -> dict[int, dict[str, np.ndarray]]:
    """Parse LS-DYNA ASCII matsum file into part-level energy histories."""
    path = Path(path)
    if not path.is_file():
        raise EnergyBalanceError(f"matsum file not found: {path}")

    parts_data: dict[int, dict[str, list[float]]] = {}
    current_time: float | None = None
    in_legend = False

    time_pattern = re.compile(r"time\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eEdD][+-]?\d+)?)", re.IGNORECASE)
    mat_pattern = re.compile(r"mat\.#=\s*(\d+)", re.IGNORECASE)

    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith(("$", "#")):
                continue

            if "{BEGIN LEGEND}" in stripped:
                in_legend = True
                continue
            if "{END LEGEND}" in stripped:
                in_legend = False
                continue
            if in_legend:
                continue

            tm = time_pattern.search(stripped)
            if tm:
                try:
                    current_time = float(tm.group(1).replace("D", "E").replace("d", "e"))
                except ValueError:
                    current_time = None
                continue

            mm = mat_pattern.search(stripped)
            if mm and current_time is not None:
                pid = int(mm.group(1))
                if pid not in parts_data:
                    parts_data[pid] = {
                        "time": [],
                        "internal_energy": [],
                        "kinetic_energy": [],
                        "hourglass_energy": [],
                        "eroded_internal_energy": [],
                        "added_mass": [],
                    }

                def get_val(key_name: str) -> float:
                    m = re.search(rf"{key_name}=\s*([+-]?\d+(?:\.\d+)?(?:[eEdD][+-]?\d+)?)", stripped, re.IGNORECASE)
                    if m:
                        return float(m.group(1).replace("D", "E").replace("d", "e"))
                    return 0.0

                parts_data[pid]["time"].append(current_time)
                parts_data[pid]["internal_energy"].append(get_val("inten"))
                parts_data[pid]["kinetic_energy"].append(get_val("kinen"))
                parts_data[pid]["hourglass_energy"].append(get_val("hgeng"))
                parts_data[pid]["eroded_internal_energy"].append(get_val("eroded_ie"))
                parts_data[pid]["added_mass"].append(get_val(r"\+mass"))

    results: dict[int, dict[str, np.ndarray]] = {}
    for pid, curves in parts_data.items():
        if curves["time"]:
            results[pid] = {k: np.asarray(v, dtype=float) for k, v in curves.items()}

    return results


def read_binout_matsum(path: str | Path) -> dict[int, dict[str, np.ndarray]]:
    """Read matsum database from binout file or directory."""
    p = Path(path)
    if not p.exists():
        return {}

    use_mpp = True
    single_binout = None
    try:
        mpp_shards.shards(p)
    except ResultsError:
        if p.is_file():
            use_mpp = False
            _, Binout, _ = _lasso()
            try:
                single_binout = Binout(str(p))
            except Exception:
                return {}
        else:
            return {}

    try:
        if use_mpp:
            res_ie = mpp_shards.read(p, "matsum", "internal_energy")
            time_arr = np.asarray(res_ie["time"], dtype=float)
            part_ids = [int(x) for x in res_ie["ids"]] if res_ie.get("ids") else []
            if not part_ids:
                return {}

            def fetch_mpp(comp: str) -> np.ndarray:
                try:
                    res = mpp_shards.read(p, "matsum", comp)
                    arr = np.asarray(res["values"], dtype=float)
                    if arr.ndim == 1 and len(part_ids) == 1:
                        arr = arr[:, None]
                    return arr
                except ResultsError:
                    return np.zeros((len(time_arr), len(part_ids)), dtype=float)

            ie_val = np.asarray(res_ie["values"], dtype=float)
            if ie_val.ndim == 1 and len(part_ids) == 1:
                ie_val = ie_val[:, None]
            ke_val = fetch_mpp("kinetic_energy")
            hg_val = fetch_mpp("hourglass_energy")
            eie_val = fetch_mpp("eroded_internal_energy")

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

        else:
            t_raw = single_binout.read("matsum", "time")
            if t_raw is None:
                return {}
            time_arr = np.asarray(t_raw, dtype=float).reshape(-1)
            ids_raw = single_binout.read("matsum", "ids")
            if ids_raw is None:
                ids_raw = single_binout.read("matsum", "mat_ids")
            if ids_raw is None:
                return {}
            part_ids = [int(x) for x in np.asarray(ids_raw).reshape(-1)]

            zeros = np.zeros((len(time_arr), len(part_ids)), dtype=float)

            def fetch_single(comp: str) -> np.ndarray:
                try:
                    v = single_binout.read("matsum", comp)
                    if v is not None and len(v) > 0:
                        arr = np.asarray(v, dtype=float)
                        if arr.ndim == 1:
                            arr = arr[:, None]
                        if arr.shape == zeros.shape:
                            return arr
                except Exception:
                    pass
                return zeros

            ie_val = fetch_single("internal_energy")
            ke_val = fetch_single("kinetic_energy")
            hg_val = fetch_single("hourglass_energy")
            eie_val = fetch_single("eroded_internal_energy")

            parts_res: dict[int, dict[str, np.ndarray]] = {}
            for idx, pid in enumerate(part_ids):
                parts_res[pid] = {
                    "time": time_arr,
                    "internal_energy": ie_val[:, idx],
                    "kinetic_energy": ke_val[:, idx],
                    "hourglass_energy": hg_val[:, idx],
                    "eroded_internal_energy": eie_val[:, idx],
                }
            return parts_res
    except Exception:
        return {}


def read_glstat(path: str | Path) -> dict[str, np.ndarray | None]:
    """Read glstat data from either binout or ASCII file, auto-detecting format."""
    p = Path(path)
    if p.is_dir() or "binout" in p.name.lower():
        try:
            return read_binout_glstat(p)
        except Exception as e:
            if p.is_file():
                return read_ascii_glstat(p)
            raise e
        return read_ascii_glstat(p)
    else:
        return read_ascii_glstat(p)


def calculate_energy_balance(
    energies: dict[str, np.ndarray | None],
    parts: dict[int, dict[str, np.ndarray]] | None = None,
    units: str = "J",
    kinetic_ratio_limit: float | None = None,
    hourglass_ratio_limit: float | None = None,
    residual_ratio_limit: float | None = None,
    sliding_ratio_limit: float | None = None,
) -> dict:
    """Core energy balance computation and threshold evaluation.

    If thresholds are None, reports ratios and maximums without asserting a pass/fail conclusion.
    Missing quantities produce explicit warnings and not_applicable checks.
    """
    time = energies.get("time")
    if time is None or len(time) < 1:
        raise EnergyBalanceError("Energy histories must contain at least one state")
    time = np.asarray(time, dtype=float)

    warnings: list[str] = []

    # Non-monotonic time check (P1-6)
    time_monotonic = bool(len(time) <= 1 or np.all(np.diff(time) > 0))
    if not time_monotonic:
        warnings.append("时间序列非严格单调递增（检测到重启或时间步回退）")

    # Extract components
    def get_arr(key: str) -> np.ndarray | None:
        val = energies.get(key)
        if val is None:
            return None
        arr = np.asarray(val, dtype=float)
        if not np.isfinite(arr).all():
            raise EnergyBalanceError(f"Nonfinite values detected in {key}")
        return arr

    ke = get_arr("kinetic_energy")
    ie = get_arr("internal_energy")
    hg = get_arr("hourglass_energy")
    se = get_arr("sliding_energy")
    ew = get_arr("external_work")
    de = get_arr("damping_energy")
    ee = get_arr("eroded_energy")
    te = get_arr("total_energy")
    stonewall = get_arr("stonewall_energy")
    spring_damper = get_arr("spring_and_damper_energy")
    added_mass = get_arr("added_mass")
    percent_increase = get_arr("percent_increase")

    zeros = np.zeros_like(time)
    ke_eff = ke if ke is not None else zeros
    ie_eff = ie if ie is not None else zeros
    hg_eff = hg if hg is not None else zeros
    se_eff = se if se is not None else zeros
    ew_eff = ew if ew is not None else zeros
    de_eff = de if de is not None else zeros
    ee_eff = ee if ee is not None else zeros
    stonewall_eff = stonewall if stonewall is not None else zeros

    # Missing quantities handling (P0-2)
    if hg is None:
        warnings.append("沙漏能未输出（需 *CONTROL_ENERGY HGEN=2）")
    if ke is None:
        warnings.append("动能未输出")
    if ie is None:
        warnings.append("内能未输出")

    # If total energy is not stored, synthesize it
    if te is None:
        te = ke_eff + ie_eff + hg_eff + se_eff + de_eff + stonewall_eff

    # Energy closure formula (P1-4):
    # spring&damper is already included in IE; eroded is not included in baseline closure.
    computed_total = ke_eff + ie_eff + hg_eff + de_eff + se_eff + stonewall_eff
    closure_diff = np.abs(te - computed_total)
    closure_denom = np.maximum(np.maximum(np.abs(te), np.abs(computed_total)), 1e-12)
    rel_closure_error = closure_diff / closure_denom
    max_rel_closure = float(np.max(rel_closure_error))

    # Energy balance residual: Delta(Total Energy) - Delta(External Work)
    # Physical relation: E_total(t) - E_total(0) = W_ext(t) - W_ext(0)
    delta_te = te - te[0]
    delta_ew = ew_eff - ew_eff[0]
    balance_residual = delta_te - delta_ew

    scale = np.maximum(np.maximum(np.abs(te), np.abs(ew_eff)), 1.0)
    relative_residual = np.abs(balance_residual) / scale
    max_rel_residual = float(np.max(relative_residual))

    # LS-DYNA ratio: te / (te0 + W_ext) (P2)
    denom_lsdyna = te[0] + ew_eff
    valid_denom_mask = np.abs(denom_lsdyna) > 1e-12
    lsdyna_ratio = np.full_like(te, np.nan)
    np.divide(te, denom_lsdyna, out=lsdyna_ratio, where=valid_denom_mask)
    max_lsdyna_ratio = float(np.nanmax(lsdyna_ratio)) if np.any(valid_denom_mask) else None

    # Kinetic / Internal ratio
    eps = 1e-12
    if ke is not None and ie is not None:
        ke_ratio = ke / np.maximum(ie, eps)
        max_ke_ratio: float | None = float(np.max(ke_ratio))
    else:
        ke_ratio = np.zeros_like(time)
        max_ke_ratio = None

    # Hourglass / Internal ratio
    if hg is not None and ie is not None:
        hg_ratio = hg / np.maximum(ie, eps)
        max_hg_ratio: float | None = float(np.max(hg_ratio))
    else:
        hg_ratio = np.zeros_like(time)
        max_hg_ratio = None

    # Sliding / Internal ratio
    if se is not None and ie is not None:
        sliding_ratio = np.abs(se) / np.maximum(ie, eps)
        max_sliding_ratio: float | None = float(np.max(sliding_ratio))
    else:
        sliding_ratio = np.zeros_like(time)
        max_sliding_ratio = None

    # Part analysis & sum-of-parts discrepancy vs GLSTAT (P1-3)
    part_summaries: dict[int, dict] = {}
    matsum_vs_glstat: dict[str, float | None] = {
        "sum_part_internal_energy": None,
        "glstat_internal_energy": None,
        "max_internal_discrepancy": None,
        "max_relative_discrepancy": None,
        "spring_and_damper_energy": None,
        "unaccounted_discrepancy": None,
    }

    if parts:
        total_final_ie = float(ie[-1]) if ie is not None and len(ie) > 0 and ie[-1] > 0 else None
        sum_part_ie = np.zeros_like(time)
        for pid, pdata in parts.items():
            pie = pdata.get("internal_energy", zeros)
            phg = pdata.get("hourglass_energy", zeros)
            pke = pdata.get("kinetic_energy", zeros)
            peie = pdata.get("eroded_internal_energy", zeros)

            if len(pie) == len(time):
                sum_part_ie += pie

            peak_pie = float(np.max(pie)) if len(pie) else 0.0
            final_pie = float(pie[-1]) if len(pie) else 0.0
            frac_total = float(final_pie / total_final_ie) if total_final_ie is not None else None

            peak_phg = float(np.max(phg)) if len(phg) else 0.0
            final_phg = float(phg[-1]) if len(phg) else 0.0
            phg_ratio = phg / np.maximum(pie, eps) if len(phg) else np.zeros(1)
            max_phg_ratio = float(np.max(phg_ratio))

            peak_pke = float(np.max(pke)) if len(pke) else 0.0
            final_peie = float(peie[-1]) if len(peie) else 0.0

            part_summaries[pid] = {
                "part_id": pid,
                "peak_internal_energy": peak_pie,
                "final_internal_energy": final_pie,
                "fraction_of_total_internal_energy": frac_total,
                "peak_hourglass_energy": peak_phg,
                "final_hourglass_energy": final_phg,
                "max_part_hourglass_ratio": max_phg_ratio,
                "peak_kinetic_energy": peak_pke,
                "final_eroded_internal_energy": final_peie,
            }

        if ie is not None and len(ie) == len(sum_part_ie):
            ie_diff = np.abs(sum_part_ie - ie)
            max_diff = float(np.max(ie_diff))
            matsum_vs_glstat["sum_part_internal_energy"] = float(sum_part_ie[-1])
            matsum_vs_glstat["glstat_internal_energy"] = float(ie[-1])
            matsum_vs_glstat["max_internal_discrepancy"] = max_diff
            matsum_vs_glstat["max_relative_discrepancy"] = float(
                np.max(ie_diff / np.maximum(np.abs(ie), eps))
            )
            if spring_damper is not None:
                final_sd = float(spring_damper[-1])
                matsum_vs_glstat["spring_and_damper_energy"] = final_sd
                matsum_vs_glstat["unaccounted_discrepancy"] = float(abs(max_diff - final_sd))

    # Threshold evaluation
    checks: dict[str, dict] = {}
    passed_all = True
    any_check_performed = False

    def eval_check(name: str, actual: float | None, limit: float | None, series: np.ndarray | None = None) -> None:
        nonlocal passed_all, any_check_performed
        if actual is None:
            # Missing quantity cannot pass if limit was provided (P0-2)
            if limit is not None:
                passed_all = False
                any_check_performed = True
                checks[name] = {
                    "threshold": limit,
                    "actual_max": None,
                    "passed": False,
                    "status": "not_applicable",
                    "exceedances": 0,
                    "reason": f"Quantity {name} missing from database",
                }
            else:
                checks[name] = {
                    "threshold": None,
                    "actual_max": None,
                    "passed": None,
                    "status": "not_applicable",
                    "exceedances": 0,
                }
            return

        if limit is None:
            checks[name] = {
                "threshold": None,
                "actual_max": actual,
                "passed": None,
                "status": "not_applicable",
                "exceedances": 0,
            }
            return

        any_check_performed = True
        is_pass = bool(actual <= limit) and time_monotonic
        if not is_pass:
            passed_all = False
        exceedances = int(np.count_nonzero(series > limit)) if series is not None else (0 if is_pass else 1)
        checks[name] = {
            "threshold": limit,
            "actual_max": actual,
            "passed": is_pass,
            "status": "passed" if is_pass else "failed",
            "exceedances": exceedances,
        }

    eval_check("kinetic_energy", max_ke_ratio, kinetic_ratio_limit, ke_ratio if ke is not None else None)
    eval_check("hourglass_energy", max_hg_ratio, hourglass_ratio_limit, hg_ratio if hg is not None else None)
    eval_check("energy_balance", max_rel_residual, residual_ratio_limit, relative_residual)
    eval_check("sliding_energy", max_sliding_ratio, sliding_ratio_limit, sliding_ratio if se is not None else None)

    if any_check_performed:
        verdict = "passed" if (passed_all and time_monotonic) else "exceeded"
        passed_conclusion: bool | None = (passed_all and time_monotonic)
    else:
        verdict = "metrics_only_no_thresholds"
        passed_conclusion = None

    # Negative sliding check (P2)
    min_se = float(np.min(se_eff)) if len(se_eff) else 0.0
    neg_sliding = bool(min_se < -1e-6)
    if neg_sliding:
        warnings.append(f"检测到负滑移界面能 (最小值: {min_se:.4e})，可能存在接触穿透或刚度不足")

    # Mass increase summary (P1-4)
    mass_summary = {
        "peak_added_mass": float(np.max(added_mass)) if added_mass is not None else None,
        "final_added_mass": float(added_mass[-1]) if added_mass is not None else None,
        "max_percent_increase": float(np.max(percent_increase)) if percent_increase is not None else None,
    }

    summary = {
        "units": units,
        "sample_count": len(time),
        "time_range": [float(time[0]), float(time[-1])],
        "verdict": verdict,
        "passed": passed_conclusion,
        "checks": checks,
        "screening_ratios": {
            "max_kinetic_energy_ratio": max_ke_ratio,
            "max_hourglass_ratio": max_hg_ratio,
            "max_sliding_energy_ratio": max_sliding_ratio,
            "max_lsdyna_energy_ratio": max_lsdyna_ratio,
        },
        "balance_residual": {
            "max_absolute_residual": float(np.max(np.abs(balance_residual))),
            "max_relative_residual": max_rel_residual,
            "final_residual": float(balance_residual[-1]),
            "final_relative_residual": float(relative_residual[-1]),
            "residual_denominator": "max(max(|TE|, |W_ext|), 1.0)",
        },
        "energy_closure": {
            "max_relative_closure_error": max_rel_closure,
            "stonewall_included": stonewall is not None,
            "formula": "KE + IE + HG + damping + sliding + stonewall vs Total",
        },
        "energy_budget": {
            "peak_kinetic_energy": float(np.max(ke_eff)),
            "final_kinetic_energy": float(ke_eff[-1]),
            "peak_internal_energy": float(np.max(ie_eff)),
            "final_internal_energy": float(ie_eff[-1]),
            "peak_hourglass_energy": float(np.max(hg_eff)),
            "final_hourglass_energy": float(hg_eff[-1]),
            "total_external_work": float(ew_eff[-1]),
            "negative_sliding_detected": neg_sliding,
            "min_sliding_energy": min_se,
        },
        "mass_increase": mass_summary,
        "parts_analyzed": len(part_summaries),
        "parts": part_summaries,
        "matsum_vs_glstat": matsum_vs_glstat,
        "warnings": warnings,
    }

    # Prepare series tabular rows for CSV export
    series_rows = []
    for i in range(len(time)):
        series_rows.append(
            [
                float(time[i]),
                float(te[i]),
                float(ke_eff[i]),
                float(ie_eff[i]),
                float(hg_eff[i]),
                float(se_eff[i]),
                float(ew_eff[i]),
                float(de_eff[i]),
                float(ee_eff[i]),
                float(balance_residual[i]),
                float(relative_residual[i]),
                float(ke_ratio[i]) if ke is not None else 0.0,
                float(hg_ratio[i]) if hg is not None else 0.0,
            ]
        )

    return {
        "summary": summary,
        "series_rows": series_rows,
        "warnings": warnings,
    }


__all__ = [
    "EnergyBalanceError",
    "calculate_energy_balance",
    "read_ascii_glstat",
    "read_ascii_matsum",
    "read_binout_glstat",
    "read_binout_matsum",
    "read_glstat",
]
