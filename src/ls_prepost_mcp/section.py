"""Q10 section cuts and SECFORC force history verification.

Reads cross-section forces and moments from binout and ASCII secforc databases,
validates internal physical consistency, and compares section force histories.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np


class SectionForceError(ValueError):
    """Raised when section force data is invalid, unreadable, or inconsistent."""


def read_ascii_secforc(path: str | Path) -> dict:
    """Read LS-DYNA ASCII secforc file into structured section time histories.

    Returns dict mapping section_id (int) -> dict of curve arrays.
    """
    path = Path(path)
    if not path.is_file():
        raise SectionForceError(f"SECFORC file does not exist: {path}")

    sections: dict[int, dict[str, list[float]]] = {}
    current_section: int | None = None

    # Matches section headers like:
    # " cross section id:       1" or " section:       1" or " cross section:   1"
    section_pattern = re.compile(r"(?:cross\s*section|section)(?:\s*id)?[:\s]+(\d+)", re.IGNORECASE)

    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith(("$", "#")):
                continue

            sec_match = section_pattern.search(stripped)
            if sec_match:
                current_section = int(sec_match.group(1))
                if current_section not in sections:
                    sections[current_section] = {
                        "time": [],
                        "x_force": [],
                        "y_force": [],
                        "z_force": [],
                        "total_force": [],
                        "x_moment": [],
                        "y_moment": [],
                        "z_moment": [],
                        "total_moment": [],
                        "x_centroid": [],
                        "y_centroid": [],
                        "z_centroid": [],
                        "area": [],
                    }
                continue

            # Data lines contain numbers
            tokens = stripped.split()
            # Must start with a float (time) and have at least 5 tokens (time, fx, fy, fz, ftotal)
            try:
                values = [float(token.replace("D", "E").replace("d", "e")) for token in tokens]
            except ValueError:
                continue

            if len(values) < 5 or current_section is None:
                continue

            sec = sections[current_section]
            sec["time"].append(values[0])
            sec["x_force"].append(values[1])
            sec["y_force"].append(values[2])
            sec["z_force"].append(values[3])
            sec["total_force"].append(values[4])

            if len(values) >= 9:
                sec["x_moment"].append(values[5])
                sec["y_moment"].append(values[6])
                sec["z_moment"].append(values[7])
                sec["total_moment"].append(values[8])
            if len(values) >= 13:
                sec["x_centroid"].append(values[9])
                sec["y_centroid"].append(values[10])
                sec["z_centroid"].append(values[11])
                sec["area"].append(values[12])

    if not sections:
        raise SectionForceError(f"No valid section data could be parsed from {path}")

    # Convert to numpy arrays
    result = {}
    for sec_id, data in sections.items():
        time_arr = np.asarray(data["time"], dtype=float)
        fx = np.asarray(data["x_force"], dtype=float)
        fy = np.asarray(data["y_force"], dtype=float)
        fz = np.asarray(data["z_force"], dtype=float)
        ftot = np.asarray(data["total_force"], dtype=float)
        f_res = np.sqrt(fx**2 + fy**2 + fz**2)

        entry = {
            "section_id": sec_id,
            "time": time_arr,
            "x_force": fx,
            "y_force": fy,
            "z_force": fz,
            "total_force": ftot,
            "resultant_force": f_res,
        }
        for opt in ("x_moment", "y_moment", "z_moment", "total_moment", "x_centroid", "y_centroid", "z_centroid", "area"):
            if data[opt]:
                entry[opt] = np.asarray(data[opt], dtype=float)
        result[sec_id] = entry

    return result


def read_binout_secforc(path: str | Path, section_id: int | None = None) -> dict:
    """Read secforc data from binout file or directory using lasso.

    Returns dict mapping section_id (int) -> dict of curve arrays.
    """
    from .domain.results import mpp_shards

    path = Path(path)
    shards_list = mpp_shards.shards(path)
    if not shards_list:
        raise SectionForceError(f"No binout files found at {path}")

    # Read available components from secforc
    components = ("x_force", "y_force", "z_force", "total_force",
                  "x_moment", "y_moment", "z_moment", "total_moment",
                  "x_centroid", "y_centroid", "z_centroid", "area")
    
    extracted: dict[str, dict] = {}
    for comp in components:
        try:
            extracted[comp] = mpp_shards.read(path, "secforc", comp)
        except Exception:
            pass

    if "x_force" not in extracted or "time" not in extracted["x_force"]:
        raise SectionForceError(f"Could not read secforc force components from {path}")

    time_arr = np.asarray(extracted["x_force"]["time"], dtype=float)
    sec_ids = extracted["x_force"].get("ids") or [1]

    results: dict[int, dict] = {}
    for idx, sid in enumerate(sec_ids):
        if section_id is not None and sid != section_id:
            continue

        fx = np.asarray(extracted["x_force"]["values"], dtype=float)
        fy = np.asarray(extracted["y_force"]["values"], dtype=float)
        fz = np.asarray(extracted["z_force"]["values"], dtype=float)

        fx_col = fx[:, idx] if fx.ndim == 2 else fx
        fy_col = fy[:, idx] if fy.ndim == 2 else fy
        fz_col = fz[:, idx] if fz.ndim == 2 else fz

        if "total_force" in extracted:
            ftot_raw = np.asarray(extracted["total_force"]["values"], dtype=float)
            ftot_col = ftot_raw[:, idx] if ftot_raw.ndim == 2 else ftot_raw
        else:
            ftot_col = np.sqrt(fx_col**2 + fy_col**2 + fz_col**2)

        entry = {
            "section_id": int(sid),
            "time": time_arr,
            "x_force": fx_col,
            "y_force": fy_col,
            "z_force": fz_col,
            "total_force": ftot_col,
            "resultant_force": np.sqrt(fx_col**2 + fy_col**2 + fz_col**2),
        }

        for comp in ("x_moment", "y_moment", "z_moment", "total_moment", "x_centroid", "y_centroid", "z_centroid", "area"):
            if comp in extracted:
                c_val = np.asarray(extracted[comp]["values"], dtype=float)
                entry[comp] = c_val[:, idx] if c_val.ndim == 2 else c_val

        results[int(sid)] = entry

    if not results:
        raise SectionForceError(f"Section {section_id} not found in secforc")

    return results


def read_secforc(path: str | Path, section_id: int | None = None) -> dict:
    """Read secforc from either binout or ASCII format.

    Auto-detects format from path name and contents.
    """
    p = Path(path)
    if p.is_dir() or "binout" in p.name.lower():
        try:
            return read_binout_secforc(p, section_id)
        except Exception as e:
            # If path was a file and binout reading failed, try ASCII
            if p.is_file():
                return read_ascii_secforc(p)
            raise e
    else:
        return read_ascii_secforc(p)


def check_secforc_consistency(section_data: dict, rtol: float = 1e-3, atol: float = 1e-4) -> dict:
    """Check physical consistency between stored total_force and computed sqrt(Fx^2+Fy^2+Fz^2).

    Returns summary of differences and whether all samples match within tolerance.
    """
    tot = np.asarray(section_data["total_force"], dtype=float)
    res = np.asarray(section_data["resultant_force"], dtype=float)

    diff = np.abs(tot - res)
    max_diff = float(np.max(diff)) if diff.size else 0.0
    denom = np.maximum(np.abs(res), 1e-12)
    rel_diff = np.abs(diff / denom)
    max_rel_diff = float(np.max(rel_diff)) if rel_diff.size else 0.0

    consistent = bool(np.allclose(tot, res, rtol=rtol, atol=atol))
    return {
        "section_id": section_data.get("section_id"),
        "sample_count": int(tot.size),
        "max_absolute_difference": max_diff,
        "max_relative_difference": max_rel_diff,
        "consistent": consistent,
        "tolerance": {"rtol": rtol, "atol": atol},
    }


def compare_section_forces(
    computed_forces: dict | np.ndarray | list[float],
    secforc_target: dict | str | Path,
    section_id: int | None = None,
    rtol: float = 1e-3,
    atol: float = 1e-3,
) -> dict:
    """Compare an independently computed section force history with SECFORC data.

    Accepts:
      computed_forces: dict with 'time' and 'resultant_force'/'total_force', or array of values.
      secforc_target: path to secforc or dict returned by read_secforc.
    """
    if isinstance(secforc_target, (str, Path)):
        sec_dict = read_secforc(secforc_target, section_id)
        first_id = next(iter(sec_dict)) if section_id is None else section_id
        target = sec_dict[first_id]
    elif isinstance(secforc_target, dict) and "total_force" in secforc_target:
        target = secforc_target
    elif isinstance(secforc_target, dict):
        first_id = next(iter(secforc_target)) if section_id is None else section_id
        target = secforc_target[first_id]
    else:
        raise SectionForceError("Invalid secforc target")

    target_time = np.asarray(target["time"], dtype=float)
    target_force = np.asarray(target.get("resultant_force", target["total_force"]), dtype=float)

    if isinstance(computed_forces, dict):
        comp_time = np.asarray(computed_forces["time"], dtype=float)
        comp_force = np.asarray(computed_forces.get("resultant_force", computed_forces.get("total_force", computed_forces.get("value"))), dtype=float)
        # Interpolate if times differ
        if not np.array_equal(comp_time, target_time):
            if comp_time[0] > target_time[0] or comp_time[-1] < target_time[-1]:
                # Overlapping interval
                mask = (target_time >= comp_time[0]) & (target_time <= comp_time[-1])
                eval_times = target_time[mask]
                target_eval = target_force[mask]
                comp_eval = np.interp(eval_times, comp_time, comp_force)
            else:
                eval_times = target_time
                target_eval = target_force
                comp_eval = np.interp(target_time, comp_time, comp_force)
        else:
            eval_times = target_time
            target_eval = target_force
            comp_eval = comp_force
    else:
        comp_force = np.asarray(computed_forces, dtype=float)
        if comp_force.shape != target_force.shape:
            raise SectionForceError(f"Computed force array shape {comp_force.shape} does not match SECFORC shape {target_force.shape}")
        eval_times = target_time
        target_eval = target_force
        comp_eval = comp_force

    diff = np.abs(comp_eval - target_eval)
    max_abs_diff = float(np.max(diff)) if diff.size else 0.0
    denom = np.maximum(np.abs(target_eval), 1e-12)
    rel_diff = diff / denom
    max_rel_diff = float(np.max(rel_diff)) if rel_diff.size else 0.0

    agrees = bool(np.allclose(comp_eval, target_eval, rtol=rtol, atol=atol))

    return {
        "section_id": target.get("section_id"),
        "sample_count": int(eval_times.size),
        "max_absolute_difference": max_abs_diff,
        "max_relative_difference": max_rel_diff,
        "consistent_with_secforc": agrees,
        "tolerance": {"rtol": rtol, "atol": atol},
    }
