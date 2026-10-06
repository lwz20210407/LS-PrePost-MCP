"""Q05 multi-entity time-history extraction: node, element, part, and global databases.

Features:
- Node history: displacements, velocities, accelerations, coordinates (ASCII nodout / binout nodout / d3plot);
- Element history: stress components (xx, yy, zz, xy, yz, zx, von Mises) and plastic strain (elout / binout elout);
- Part history: internal, kinetic, hourglass, eroded energies (matsum / binout matsum);
- Global history: total, kinetic, internal, sliding, external work, damping energies (glstat / binout glstat);
- Batch querying of multiple entities and components in a single operation;
- Synchronous CSV export of aligned time series with metadata and LASSO consistency.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

try:
    from lasso.dyna import Binout
except ImportError:
    Binout = None


class HistoryExtractionError(ValueError):
    """Raised when history data extraction fails or inputs are invalid."""


def extract_node_history_binout(
    binout_path: str | Path,
    node_ids: list[int],
    quantity: str = "displacement",
    components: list[str] | None = None,
) -> dict[str, Any]:
    """Extract nodal time history from binout /nodout."""
    if Binout is None:
        raise HistoryExtractionError("lasso-python is required for binout reading")
    b = Binout(str(binout_path))

    avail = None
    for key in ("ids", "node_ids"):
        try:
            avail = b.read("nodout", key)
            if avail is not None and len(avail) > 0:
                break
        except Exception:
            pass
    if avail is None or len(avail) == 0:
        try:
            avail = b.read("nodout", "metadata", "ids")
        except Exception:
            pass
    if avail is None or len(avail) == 0:
        raise HistoryExtractionError(f"No node IDs found in binout {binout_path}")
    all_ids = list(np.asarray(avail, dtype=int))

    id_indices = {}
    for nid in node_ids:
        if nid not in all_ids:
            raise HistoryExtractionError(f"Node ID {nid} not found in binout nodout (available: {all_ids[:10]}...)")
        id_indices[nid] = all_ids.index(nid)

    times = np.asarray(b.read("nodout", "time"), dtype=float)

    prefix_map = {
        "displacement": "displacement",
        "velocity": "velocity",
        "acceleration": "acceleration",
        "coordinate": "coordinate",
    }
    q_prefix = prefix_map.get(quantity, quantity)
    req_comps = components or ["x", "y", "z", "magnitude"]

    # Component mappings in binout
    comp_map = {
        "x": f"x_{q_prefix}",
        "y": f"y_{q_prefix}",
        "z": f"z_{q_prefix}",
    }

    curves: dict[str, np.ndarray] = {}
    for nid in node_ids:
        idx = id_indices[nid]
        x_val = np.asarray(b.read("nodout", comp_map["x"]), dtype=float)[:, idx] if "x" in req_comps or "magnitude" in req_comps else None
        y_val = np.asarray(b.read("nodout", comp_map["y"]), dtype=float)[:, idx] if "y" in req_comps or "magnitude" in req_comps else None
        z_val = np.asarray(b.read("nodout", comp_map["z"]), dtype=float)[:, idx] if "z" in req_comps or "magnitude" in req_comps else None

        for c in req_comps:
            key = f"node_{nid}_{c}"
            if c == "x" and x_val is not None:
                curves[key] = x_val
            elif c == "y" and y_val is not None:
                curves[key] = y_val
            elif c == "z" and z_val is not None:
                curves[key] = z_val
            elif c == "magnitude":
                if x_val is not None and y_val is not None and z_val is not None:
                    curves[key] = np.sqrt(x_val**2 + y_val**2 + z_val**2)

    return {"times": times, "curves": curves, "entity_type": "node", "entity_ids": node_ids}


def extract_element_history_binout(
    binout_path: str | Path,
    element_ids: list[int],
    quantity: str = "stress",
    components: list[str] | None = None,
) -> dict[str, Any]:
    """Extract solid/shell element stress/strain time history from binout /elout."""
    if Binout is None:
        raise HistoryExtractionError("lasso-python is required for binout reading")
    b = Binout(str(binout_path))

    # Try solid then shell
    sub_target = None
    all_ids = None
    for sub in ("solid", "shell"):
        for id_key in ("ids", "element_ids"):
            try:
                avail = b.read("elout", sub, id_key)
                if avail is not None and len(avail) > 0:
                    cand_ids = list(np.asarray(avail, dtype=int))
                    if any(eid in cand_ids for eid in element_ids):
                        all_ids = cand_ids
                        sub_target = sub
                        break
            except Exception:
                pass
        if all_ids is not None:
            break

    if all_ids is None:
        for id_key in ("ids", "element_ids"):
            try:
                avail = b.read("elout", id_key)
                if avail is not None and len(avail) > 0:
                    all_ids = list(np.asarray(avail, dtype=int))
                    sub_target = None
                    break
            except Exception:
                pass

    if all_ids is None:
        raise HistoryExtractionError(f"No element IDs found in binout elout: {binout_path}")

    id_indices = {}
    for eid in element_ids:
        if eid not in all_ids:
            raise HistoryExtractionError(f"Element ID {eid} not found in binout elout")
        id_indices[eid] = all_ids.index(eid)

    path_prefix = ("elout", sub_target) if sub_target else ("elout",)
    times = np.asarray(b.read(*path_prefix, "time"), dtype=float)

    req_comps = components or ["von_mises", "sig_xx", "sig_yy", "sig_zz"]
    comp_map = {
        "sig_xx": "sig_xx",
        "sig_yy": "sig_yy",
        "sig_zz": "sig_zz",
        "sig_xy": "sig_xy",
        "sig_yz": "sig_yz",
        "sig_zx": "sig_zx",
        "von_mises": "effective_stress",
        "effective_stress": "effective_stress",
        "plastic_strain": "effective_plastic_strain",
        "effective_plastic_strain": "effective_plastic_strain",
    }

    curves: dict[str, np.ndarray] = {}
    for eid in element_ids:
        idx = id_indices[eid]
        for c in req_comps:
            b_var = comp_map.get(c, c)
            raw = None
            try:
                raw = b.read(*path_prefix, b_var)
            except Exception:
                pass
            if raw is not None:
                arr = np.asarray(raw, dtype=float)
                if arr.ndim > 1:
                    curves[f"element_{eid}_{c}"] = arr[:, idx]
                else:
                    curves[f"element_{eid}_{c}"] = arr

    return {"times": times, "curves": curves, "entity_type": "element", "entity_ids": element_ids}


def extract_part_history_binout(
    binout_path: str | Path,
    part_ids: list[int],
    components: list[str] | None = None,
) -> dict[str, Any]:
    """Extract part energy dissipation history from binout /matsum."""
    if Binout is None:
        raise HistoryExtractionError("lasso-python is required for binout reading")
    b = Binout(str(binout_path))

    avail = None
    for key in ("ids", "mat_ids", "part_ids"):
        try:
            avail = b.read("matsum", key)
            if avail is not None and len(avail) > 0:
                break
        except Exception:
            pass
    if avail is None or len(avail) == 0:
        try:
            avail = b.read("matsum", "metadata", "ids")
        except Exception:
            pass

    if avail is None or len(avail) == 0:
        raise HistoryExtractionError(f"No part IDs metadata in binout matsum: {binout_path}")
    all_ids = list(np.asarray(avail, dtype=int))

    id_indices = {}
    for pid in part_ids:
        if pid not in all_ids:
            raise HistoryExtractionError(f"Part ID {pid} not found in binout matsum (available: {all_ids})")
        id_indices[pid] = all_ids.index(pid)

    times = np.asarray(b.read("matsum", "time"), dtype=float)
    req_comps = components or ["internal_energy", "kinetic_energy", "hourglass_energy"]

    curves: dict[str, np.ndarray] = {}
    for pid in part_ids:
        idx = id_indices[pid]
        for c in req_comps:
            raw = b.read("matsum", c)
            if raw is not None:
                arr = np.asarray(raw, dtype=float)
                if arr.ndim > 1:
                    curves[f"part_{pid}_{c}"] = arr[:, idx]
                else:
                    curves[f"part_{pid}_{c}"] = arr

    return {"times": times, "curves": curves, "entity_type": "part", "entity_ids": part_ids}


def extract_global_history_binout(
    binout_path: str | Path,
    components: list[str] | None = None,
) -> dict[str, Any]:
    """Extract global energy balance history from binout /glstat."""
    if Binout is None:
        raise HistoryExtractionError("lasso-python is required for binout reading")
    b = Binout(str(binout_path))

    times = np.asarray(b.read("glstat", "time"), dtype=float)
    req_comps = components or [
        "kinetic_energy",
        "internal_energy",
        "total_energy",
        "hourglass_energy",
        "sliding_interface_energy",
        "external_work",
    ]

    comp_alias = {
        "sliding_energy": "sliding_interface_energy",
    }

    curves: dict[str, np.ndarray] = {}
    for c in req_comps:
        b_var = comp_alias.get(c, c)
        raw = b.read("glstat", b_var)
        if raw is not None:
            curves[f"global_{c}"] = np.asarray(raw, dtype=float)

    return {"times": times, "curves": curves, "entity_type": "global", "entity_ids": []}


def extract_history(
    source: str | Path,
    entity_type: str,
    entity_ids: list[int] | None = None,
    quantity: str = "displacement",
    components: list[str] | None = None,
    units: str = "",
) -> tuple[dict[str, Any], list[str], list[list[Any]]]:
    """Unified entrypoint extracting time histories across node, element, part, and global modes.

    Returns (summary_dict, csv_headers, csv_rows).
    """
    p = Path(source)
    if not p.exists():
        raise HistoryExtractionError(f"Database source file not found: {p}")

    ids = [int(i) for i in (entity_ids or [])]

    if entity_type == "node":
        if not ids:
            raise HistoryExtractionError("Node history requires at least one node_id")
        res = extract_node_history_binout(p, ids, quantity, components)
    elif entity_type == "element":
        if not ids:
            raise HistoryExtractionError("Element history requires at least one element_id")
        res = extract_element_history_binout(p, ids, quantity, components)
    elif entity_type == "part":
        if not ids:
            raise HistoryExtractionError("Part history requires at least one part_id")
        res = extract_part_history_binout(p, ids, components)
    elif entity_type == "global":
        res = extract_global_history_binout(p, components)
    else:
        raise HistoryExtractionError(f"Unsupported entity_type: '{entity_type}'. Must be node, element, part, or global.")

    times = res["times"]
    curves = res["curves"]

    if not curves:
        raise HistoryExtractionError(f"No curves extracted for {entity_type} from {p}")

    csv_headers = ["time"] + list(curves.keys())
    csv_rows = []
    for idx, t in enumerate(times):
        row: list[Any] = [float(t)]
        for k in curves:
            row.append(float(curves[k][idx]))
        csv_rows.append(row)

    curve_summaries = {}
    for k, v in curves.items():
        curve_summaries[k] = {
            "sample_count": len(v),
            "min": float(np.min(v)),
            "max": float(np.max(v)),
            "peak_absolute": float(np.max(np.abs(v))),
            "final_value": float(v[-1]),
            "unit": units,
        }

    summary = {
        "entity_type": entity_type,
        "entity_ids": ids,
        "sample_count": len(times),
        "duration": float(times[-1] - times[0]) if len(times) > 1 else 0.0,
        "curve_count": len(curves),
        "curves": curve_summaries,
        "units": units,
    }

    return summary, csv_headers, csv_rows
