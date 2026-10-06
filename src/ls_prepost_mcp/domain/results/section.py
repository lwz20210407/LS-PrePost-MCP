"""Q10 section cuts and SECFORC force history verification.

Reads cross-section forces and moments from binout and ASCII secforc databases,
validates internal physical consistency, and compares section force histories.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from . import mpp_shards
from .lasso_backend import ResultsError, _lasso


class SectionForceError(ValueError):
    """Raised when section force data is invalid, unreadable, or inconsistent."""


def read_ascii_secforc(path: str | Path) -> dict[int, dict]:
    """Read LS-DYNA ASCII secforc file into structured section time histories.

    Supports standard LS-DYNA 3-line record structures with legend blocks and
    accelerometer tags, as well as single-line tabular formats.
    Returns dict mapping section_id (int) -> dict of curve arrays.
    """
    path = Path(path)
    if not path.is_file():
        raise SectionForceError(f"SECFORC file does not exist: {path}")

    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()

    # Step 1: Parse {BEGIN LEGEND} ... {END LEGEND}
    legend_titles: dict[int, str] = {}
    in_legend = False
    cleaned_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if "{BEGIN LEGEND}" in stripped:
            in_legend = True
            continue
        if "{END LEGEND}" in stripped:
            in_legend = False
            continue
        if in_legend:
            parts = stripped.split(None, 1)
            if len(parts) == 2 and parts[0].isdigit():
                legend_titles[int(parts[0])] = parts[1].strip()
            continue
        if stripped.startswith(("$", "#")) or "line#" in stripped.lower():
            continue
        cleaned_lines.append(stripped)

    # Step 2: Try 3-line record format (standard LS-DYNA)
    sections_3line: dict[int, dict[str, list[float]]] = {}
    i = 0
    parsed_as_3line = False

    while i < len(cleaned_lines):
        line1 = cleaned_lines[i]
        # Ignore lines like "cross section id: ..." when scanning for 3-line records
        if "cross section" in line1.lower() or "section id" in line1.lower():
            i += 1
            continue

        tokens1 = line1.split()
        if len(tokens1) >= 6:
            try:
                sec_id = int(tokens1[0])
                time_val = float(tokens1[1].replace("D", "E").replace("d", "e"))
                fx = float(tokens1[2].replace("D", "E").replace("d", "e"))
                fy = float(tokens1[3].replace("D", "E").replace("d", "e"))
                fz = float(tokens1[4].replace("D", "E").replace("d", "e"))
                fmag = float(tokens1[5].replace("D", "E").replace("d", "e"))

                mx = my = mz = mmag = 0.0
                has_moment = False
                if i + 1 < len(cleaned_lines):
                    line2 = cleaned_lines[i + 1]
                    line2_clean = re.sub(r"ac\s*ID\s*=\s*\d+", "", line2, flags=re.IGNORECASE).strip()
                    tokens2 = [float(x.replace("D", "E").replace("d", "e")) for x in line2_clean.split()]
                    if len(tokens2) >= 4:
                        mx, my, mz, mmag = tokens2[:4]
                        has_moment = True

                cx = cy = cz = area = 0.0
                has_geom = False
                if i + 2 < len(cleaned_lines):
                    line3 = cleaned_lines[i + 2]
                    tokens3 = [float(x.replace("D", "E").replace("d", "e")) for x in line3.split()]
                    if len(tokens3) >= 4:
                        cx, cy, cz, area = tokens3[:4]
                        has_geom = True

                if sec_id not in sections_3line:
                    sections_3line[sec_id] = {
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

                sec = sections_3line[sec_id]
                sec["time"].append(time_val)
                sec["x_force"].append(fx)
                sec["y_force"].append(fy)
                sec["z_force"].append(fz)
                sec["total_force"].append(fmag)
                if has_moment:
                    sec["x_moment"].append(mx)
                    sec["y_moment"].append(my)
                    sec["z_moment"].append(mz)
                    sec["total_moment"].append(mmag)
                if has_geom:
                    sec["x_centroid"].append(cx)
                    sec["y_centroid"].append(cy)
                    sec["z_centroid"].append(cz)
                    sec["area"].append(area)

                parsed_as_3line = True
                i += 3
                continue
            except ValueError:
                pass
        i += 1

    if parsed_as_3line and sections_3line:
        results: dict[int, dict] = {}
        for sec_id, data in sections_3line.items():
            t_arr = np.asarray(data["time"], dtype=float)
            fx = np.asarray(data["x_force"], dtype=float)
            fy = np.asarray(data["y_force"], dtype=float)
            fz = np.asarray(data["z_force"], dtype=float)
            ftot = np.asarray(data["total_force"], dtype=float)
            entry = {
                "section_id": sec_id,
                "title": legend_titles.get(sec_id),
                "time": t_arr,
                "x_force": fx,
                "y_force": fy,
                "z_force": fz,
                "total_force": ftot,
                "resultant_force": np.sqrt(fx**2 + fy**2 + fz**2),
            }
            if data["x_moment"]:
                mx = np.asarray(data["x_moment"], dtype=float)
                my = np.asarray(data["y_moment"], dtype=float)
                mz = np.asarray(data["z_moment"], dtype=float)
                mtot = np.asarray(data["total_moment"], dtype=float)
                entry.update(
                    {
                        "x_moment": mx,
                        "y_moment": my,
                        "z_moment": mz,
                        "total_moment": mtot,
                        "resultant_moment": np.sqrt(mx**2 + my**2 + mz**2),
                    }
                )
            if data["x_centroid"]:
                entry.update(
                    {
                        "x_centroid": np.asarray(data["x_centroid"], dtype=float),
                        "y_centroid": np.asarray(data["y_centroid"], dtype=float),
                        "z_centroid": np.asarray(data["z_centroid"], dtype=float),
                        "area": np.asarray(data["area"], dtype=float),
                    }
                )
            results[sec_id] = entry
        return results

    # Step 3: Single-line columnar format (fallback)
    sections_single: dict[int, dict[str, list[float]]] = {}
    current_sec: int | None = None
    section_pattern = re.compile(r"^\s*(?:cross\s*section|section)(?:\s*id)?[:\s]+(\d+)", re.IGNORECASE)

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("$", "#")):
            continue

        sec_match = section_pattern.search(stripped)
        if sec_match:
            current_sec = int(sec_match.group(1))
            if current_sec not in sections_single:
                sections_single[current_sec] = {
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

        tokens = stripped.split()
        try:
            values = [float(tok.replace("D", "E").replace("d", "e")) for tok in tokens]
        except ValueError:
            continue

        if len(values) < 5 or current_sec is None:
            continue

        s = sections_single[current_sec]
        s["time"].append(values[0])
        s["x_force"].append(values[1])
        s["y_force"].append(values[2])
        s["z_force"].append(values[3])
        s["total_force"].append(values[4])
        if len(values) >= 9:
            s["x_moment"].append(values[5])
            s["y_moment"].append(values[6])
            s["z_moment"].append(values[7])
            s["total_moment"].append(values[8])
        if len(values) >= 13:
            s["x_centroid"].append(values[9])
            s["y_centroid"].append(values[10])
            s["z_centroid"].append(values[11])
            s["area"].append(values[12])

    if not sections_single:
        raise SectionForceError(f"No valid section data could be parsed from {path}")

    res = {}
    for sid, data in sections_single.items():
        time_arr = np.asarray(data["time"], dtype=float)
        fx = np.asarray(data["x_force"], dtype=float)
        fy = np.asarray(data["y_force"], dtype=float)
        fz = np.asarray(data["z_force"], dtype=float)
        ftot = np.asarray(data["total_force"], dtype=float)
        item = {
            "section_id": sid,
            "title": legend_titles.get(sid),
            "time": time_arr,
            "x_force": fx,
            "y_force": fy,
            "z_force": fz,
            "total_force": ftot,
            "resultant_force": np.sqrt(fx**2 + fy**2 + fz**2),
        }
        if data["x_moment"]:
            item.update(
                {
                    "x_moment": np.asarray(data["x_moment"], dtype=float),
                    "y_moment": np.asarray(data["y_moment"], dtype=float),
                    "z_moment": np.asarray(data["z_moment"], dtype=float),
                    "total_moment": np.asarray(data["total_moment"], dtype=float),
                    "resultant_moment": np.sqrt(
                        np.asarray(data["x_moment"], dtype=float) ** 2
                        + np.asarray(data["y_moment"], dtype=float) ** 2
                        + np.asarray(data["z_moment"], dtype=float) ** 2
                    ),
                }
            )
        if data["x_centroid"]:
            item.update(
                {
                    "x_centroid": np.asarray(data["x_centroid"], dtype=float),
                    "y_centroid": np.asarray(data["y_centroid"], dtype=float),
                    "z_centroid": np.asarray(data["z_centroid"], dtype=float),
                    "area": np.asarray(data["area"], dtype=float),
                }
            )
        res[sid] = item

    return res


def read_binout_secforc(path: str | Path, section_id: int | None = None) -> dict[int, dict]:
    """Read secforc data from binout file or directory.

    Directly accesses through mpp_shards or single-file Binout reader without globbing.
    Returns dict mapping section_id (int) -> dict of curve arrays.
    """
    p = Path(path)
    if not p.exists():
        raise SectionForceError(f"Path does not exist: {p}")

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
            except Exception as exc:
                raise SectionForceError(f"Failed to open binout at {path}: {exc}") from exc
        else:
            raise SectionForceError(f"No binout files found at {path}")

    # Extract time series and IDs
    if use_mpp:
        try:
            res_any = mpp_shards.read(p, "secforc", "time")
            time_arr = np.asarray(res_any["time"], dtype=float).reshape(-1)
        except ResultsError as exc:
            raise SectionForceError(f"Could not read secforc time from {path}: {exc}") from exc

        # Read section IDs (no fallback to [1])
        try:
            res_fx = mpp_shards.read(p, "secforc", "x_force")
            ids_raw = res_fx.get("ids")
        except ResultsError:
            ids_raw = None

        if ids_raw is None or len(ids_raw) == 0:
            raise SectionForceError(f"No section IDs found in secforc database at {path}")
        sec_ids = [int(sid) for sid in np.asarray(ids_raw).reshape(-1)]

        if section_id is not None and section_id not in sec_ids:
            raise SectionForceError(f"Section {section_id} not found in secforc (available IDs: {sec_ids})")

        def fetch_mpp(comp: str) -> np.ndarray | None:
            try:
                r = mpp_shards.read(p, "secforc", comp)
                arr = np.asarray(r["values"], dtype=float)
                if arr.ndim == 1 and len(sec_ids) == 1:
                    arr = arr[:, None]
                return arr
            except ResultsError:
                return None

        fx_table = fetch_mpp("x_force")
        fy_table = fetch_mpp("y_force")
        fz_table = fetch_mpp("z_force")
        if fx_table is None or fy_table is None or fz_table is None:
            raise SectionForceError(f"Missing force components in secforc at {path}")

        ftot_table = fetch_mpp("total_force")

        opt_tables: dict[str, np.ndarray | None] = {}
        for comp in (
            "x_moment",
            "y_moment",
            "z_moment",
            "total_moment",
            "x_centroid",
            "y_centroid",
            "z_centroid",
            "area",
        ):
            opt_tables[comp] = fetch_mpp(comp)

        results: dict[int, dict] = {}
        for idx, sid in enumerate(sec_ids):
            if section_id is not None and sid != section_id:
                continue

            fx = fx_table[:, idx] if fx_table.ndim == 2 else fx_table.reshape(-1)
            fy = fy_table[:, idx] if fy_table.ndim == 2 else fy_table.reshape(-1)
            fz = fz_table[:, idx] if fz_table.ndim == 2 else fz_table.reshape(-1)
            f_res = np.sqrt(fx**2 + fy**2 + fz**2)
            ftot = ftot_table[:, idx] if ftot_table is not None and ftot_table.ndim == 2 else f_res

            entry = {
                "section_id": sid,
                "time": time_arr,
                "x_force": fx,
                "y_force": fy,
                "z_force": fz,
                "total_force": ftot,
                "resultant_force": f_res,
            }
            for comp, arr in opt_tables.items():
                if arr is not None:
                    entry[comp] = arr[:, idx] if arr.ndim == 2 else arr.reshape(-1)

            if "x_moment" in entry and "y_moment" in entry and "z_moment" in entry:
                entry["resultant_moment"] = np.sqrt(
                    entry["x_moment"] ** 2 + entry["y_moment"] ** 2 + entry["z_moment"] ** 2
                )
            results[sid] = entry
        return results

    else:
        try:
            time_raw = single_binout.read("secforc", "time")
            if time_raw is None or len(time_raw) == 0:
                raise SectionForceError(f"No secforc time array found in {path}")
            time_arr = np.asarray(time_raw, dtype=float).reshape(-1)
        except Exception as exc:
            raise SectionForceError(f"Could not read secforc from {path}: {exc}") from exc

        # Retrieve section IDs (no fallback to [1])
        ids_raw = single_binout.read("secforc", "ids")
        if ids_raw is None or len(ids_raw) == 0:
            ids_raw = single_binout.read("secforc", "section_ids")
        if ids_raw is None or len(ids_raw) == 0:
            raise SectionForceError(f"No section IDs found in secforc database at {path}")

        sec_ids = [int(sid) for sid in np.asarray(ids_raw).reshape(-1)]

        if section_id is not None and section_id not in sec_ids:
            raise SectionForceError(f"Section {section_id} not found in secforc (available IDs: {sec_ids})")

        # Read quantities
        components = (
            "x_force",
            "y_force",
            "z_force",
            "total_force",
            "x_moment",
            "y_moment",
            "z_moment",
            "total_moment",
            "x_centroid",
            "y_centroid",
            "z_centroid",
            "area",
        )
        raw_tables: dict[str, np.ndarray] = {}
        for comp in components:
            try:
                val = single_binout.read("secforc", comp)
                if val is not None and len(val) > 0:
                    raw_tables[comp] = np.asarray(val, dtype=float)
            except Exception:
                pass

        if "x_force" not in raw_tables or "y_force" not in raw_tables or "z_force" not in raw_tables:
            raise SectionForceError(f"Missing force components in secforc at {path}")

        results_single: dict[int, dict] = {}
        for idx, sid in enumerate(sec_ids):
            if section_id is not None and sid != section_id:
                continue

            fx = raw_tables["x_force"]
            fy = raw_tables["y_force"]
            fz = raw_tables["z_force"]

            fx_col = fx[:, idx] if fx.ndim == 2 else fx.reshape(-1)
            fy_col = fy[:, idx] if fy.ndim == 2 else fy.reshape(-1)
            fz_col = fz[:, idx] if fz.ndim == 2 else fz.reshape(-1)

            f_res = np.sqrt(fx_col**2 + fy_col**2 + fz_col**2)

            if "total_force" in raw_tables:
                ftot = raw_tables["total_force"]
                ftot_col = ftot[:, idx] if ftot.ndim == 2 else ftot.reshape(-1)
            else:
                ftot_col = f_res

            entry = {
                "section_id": sid,
                "time": time_arr,
                "x_force": fx_col,
                "y_force": fy_col,
                "z_force": fz_col,
                "total_force": ftot_col,
                "resultant_force": f_res,
            }

            for comp in (
                "x_moment",
                "y_moment",
                "z_moment",
                "total_moment",
                "x_centroid",
                "y_centroid",
                "z_centroid",
                "area",
            ):
                if comp in raw_tables:
                    arr = raw_tables[comp]
                    entry[comp] = arr[:, idx] if arr.ndim == 2 else arr.reshape(-1)

            if "x_moment" in entry and "y_moment" in entry and "z_moment" in entry:
                entry["resultant_moment"] = np.sqrt(
                    entry["x_moment"] ** 2 + entry["y_moment"] ** 2 + entry["z_moment"] ** 2
                )

            results_single[sid] = entry

        return results_single


def read_secforc(path: str | Path, section_id: int | None = None) -> dict[int, dict]:
    """Read secforc from either binout or ASCII format.

    Auto-detects format from path name and contents.
    Never silently falls back to ASCII on binary decode failure.
    """
    p = Path(path)
    if p.is_dir() or "binout" in p.name.lower():
        return read_binout_secforc(p, section_id)
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

    force_consistent = bool(np.allclose(tot, res, rtol=rtol, atol=atol))

    moment_summary = None
    if "total_moment" in section_data and "resultant_moment" in section_data:
        m_tot = np.asarray(section_data["total_moment"], dtype=float)
        m_res = np.asarray(section_data["resultant_moment"], dtype=float)
        m_diff = np.abs(m_tot - m_res)
        m_denom = np.maximum(np.abs(m_res), 1e-12)
        moment_summary = {
            "max_absolute_difference": float(np.max(m_diff)) if m_diff.size else 0.0,
            "max_relative_difference": float(np.max(m_diff / m_denom)) if m_diff.size else 0.0,
            "consistent": bool(np.allclose(m_tot, m_res, rtol=rtol, atol=atol)),
        }

    return {
        "section_id": section_data.get("section_id"),
        "sample_count": int(tot.size),
        "max_absolute_difference": max_diff,
        "max_relative_difference": max_rel_diff,
        "consistent": force_consistent,
        "moment_consistency": moment_summary,
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

    Requires strictly increasing time histories and overlapping time ranges.
    Compares total resultant force as well as vector components (Fx, Fy, Fz, Mx, My, Mz).
    """
    if isinstance(secforc_target, (str, Path)):
        sec_dict = read_secforc(secforc_target, section_id)
        if not sec_dict:
            raise SectionForceError(f"No section data found in {secforc_target}")
        if section_id is not None:
            if section_id not in sec_dict:
                raise SectionForceError(f"Section {section_id} not found in target")
            target_data = sec_dict[section_id]
        else:
            target_data = next(iter(sec_dict.values()))
    elif isinstance(secforc_target, dict):
        if "time" in secforc_target and ("resultant_force" in secforc_target or "total_force" in secforc_target):
            target_data = secforc_target
        elif section_id is not None and section_id in secforc_target:
            target_data = secforc_target[section_id]
        elif len(secforc_target) == 1 and isinstance(next(iter(secforc_target.values())), dict):
            target_data = next(iter(secforc_target.values()))
        else:
            raise SectionForceError("secforc_target dict structure not recognized")
    else:
        raise SectionForceError("secforc_target must be file path or section dict")

    # Target arrays
    t_tgt = np.asarray(target_data["time"], dtype=float)
    if len(t_tgt) < 2 or np.any(np.diff(t_tgt) <= 0):
        raise SectionForceError("Target SECFORC time history must be strictly increasing with at least 2 points")

    # Computed arrays
    if isinstance(computed_forces, dict):
        t_cmp = np.asarray(computed_forces["time"], dtype=float)
    elif isinstance(computed_forces, np.ndarray) and computed_forces.ndim == 2 and computed_forces.shape[1] >= 2:
        t_cmp = computed_forces[:, 0]
    else:
        t_cmp = t_tgt

    if len(t_cmp) < 2 or np.any(np.diff(t_cmp) <= 0):
        raise SectionForceError("Computed time history must be strictly increasing with at least 2 points")

    # Check interval overlap (P1-5)
    t_start = max(float(t_tgt[0]), float(t_cmp[0]))
    t_end = min(float(t_tgt[-1]), float(t_cmp[-1]))
    if t_start > t_end:
        raise SectionForceError(
            f"No overlapping time interval between computed [{t_cmp[0]}, {t_cmp[-1]}] and target [{t_tgt[0]}, {t_tgt[-1]}]"
        )

    # Common time grid within overlap
    mask_tgt = (t_tgt >= t_start) & (t_tgt <= t_end)
    common_time = t_tgt[mask_tgt]
    if len(common_time) < 2:
        raise SectionForceError(
            f"Overlapping sample count ({len(common_time)}) below minimum (requires at least 2 points)"
        )

    # Helper to extract and interpolate a curve
    def get_interpolated(source: dict | np.ndarray, key_names: tuple[str, ...], col_idx: int | None = None) -> np.ndarray | None:
        if isinstance(source, dict):
            for kn in key_names:
                if kn in source:
                    arr = np.asarray(source[kn], dtype=float)
                    t_src = np.asarray(source["time"], dtype=float)
                    return np.interp(common_time, t_src, arr)
        elif isinstance(source, np.ndarray):
            if col_idx is not None and source.ndim == 2 and source.shape[1] > col_idx:
                return np.interp(common_time, source[:, 0], source[:, col_idx])
            elif source.ndim == 1 and len(source) == len(t_cmp):
                return np.interp(common_time, t_cmp, source)
        return None

    # Compare components
    comparisons: dict[str, dict] = {}
    all_matched = True

    comp_specs = [
        ("resultant_force", ("resultant_force", "total_force"), 1),
        ("x_force", ("x_force",), 2),
        ("y_force", ("y_force",), 3),
        ("z_force", ("z_force",), 4),
        ("resultant_moment", ("resultant_moment", "total_moment"), 5),
        ("x_moment", ("x_moment",), 6),
        ("y_moment", ("y_moment",), 7),
        ("z_moment", ("z_moment",), 8),
    ]

    for comp_name, keys, col_idx in comp_specs:
        y_tgt = get_interpolated(target_data, keys)
        y_cmp = get_interpolated(computed_forces, keys, col_idx)

        if y_tgt is not None and y_cmp is not None:
            diff = np.abs(y_cmp - y_tgt)
            max_abs = float(np.max(diff))
            denom = np.maximum(np.abs(y_tgt), 1e-12)
            rel_diff = diff / denom
            max_rel = float(np.max(rel_diff))
            is_match = bool(np.allclose(y_cmp, y_tgt, rtol=rtol, atol=atol))
            if not is_match:
                all_matched = False
            comparisons[comp_name] = {
                "max_absolute_difference": max_abs,
                "max_relative_difference": max_rel,
                "matched": is_match,
            }

    if "resultant_force" not in comparisons:
        raise SectionForceError("Could not align resultant force curves between computed and SECFORC target")

    res_force_comp = comparisons["resultant_force"]
    return {
        "section_id": target_data.get("section_id"),
        "points_compared": len(common_time),
        "time_interval": [float(t_start), float(t_end)],
        "max_absolute_difference": res_force_comp["max_absolute_difference"],
        "max_relative_difference": res_force_comp["max_relative_difference"],
        "tolerance": {"rtol": rtol, "atol": atol},
        "matched": all_matched,
        "consistent_with_secforc": all_matched,
        "components": comparisons,
    }


__all__ = [
    "SectionForceError",
    "check_secforc_consistency",
    "compare_section_forces",
    "read_ascii_secforc",
    "read_binout_secforc",
    "read_secforc",
]
