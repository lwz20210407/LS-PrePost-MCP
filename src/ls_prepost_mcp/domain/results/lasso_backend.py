"""Result reading with LASSO (lasso-python, the optional ``results`` extra): Q01 overview, Q05
histories, Q06 binout curves and element fields for Q03/Q04.

Decision D2 lets numbers come from LASSO; the cross-check against LS-PrePost belongs to the
native track. Values are returned in the model's own units (nothing is converted). d3plot stores
current nodal coordinates, so displacements are current minus initial coordinates. Element
values with several stored integration points are averaged over them and the metadata says so.
"""
from __future__ import annotations

from importlib import metadata
from pathlib import Path

import numpy as np

from . import invariants as inv
from .time_validation import validate_d3plot_times

ASCII = ("glstat", "matsum", "rcforc", "secforc", "nodout", "elout", "sleout", "nodfor", "spcforc", "rbdout",
         "ncforc", "deforc", "jntforc", "bndout", "rwforc", "abstat", "swforc", "gceout")
FAMILIES = {  # family -> (ids, alive, part indexes, history variables, stress, plastic strain)
    "solid": ("element_solid_ids", "element_solid_is_alive", "element_solid_part_indexes",
              "element_solid_history_variables", "element_solid_stress", "element_solid_effective_plastic_strain"),
    "shell": ("element_shell_ids", "element_shell_is_alive", "element_shell_part_indexes",
              "element_shell_history_vars", "element_shell_stress", "element_shell_effective_plastic_strain"),
    "tshell": ("element_tshell_ids", "element_tshell_is_alive", "element_tshell_part_indexes",
               "element_tshell_history_variables", "element_tshell_stress",
               "element_tshell_effective_plastic_strain"),
    "beam": ("element_beam_ids", "element_beam_is_alive", "element_beam_part_indexes",
             "element_beam_history_vars", None, None),
}
STRESS = ("sxx", "syy", "szz", "sxy", "syz", "szx")


class ResultsError(ValueError):
    """A result request that cannot be answered from the files."""


class MissingComponentError(ResultsError):
    """A known database does not store a requested component, rather than a read failure."""


def _lasso():
    try:
        from lasso.dyna import ArrayType, Binout, D3plot
    except ImportError as error:
        raise ResultsError("Reading results needs lasso-python (install the 'results' extra)") from error
    return ArrayType, Binout, D3plot


def backend() -> str:
    try:
        return "lasso-python " + metadata.version("lasso-python")
    except metadata.PackageNotFoundError:
        return "lasso-python (not installed)"


def _arrays(path: str | Path, state_arrays: list | None = None) -> dict:
    _, _, D3plot = _lasso()
    path = Path(path)
    if not path.exists():
        raise ResultsError(f"{path} does not exist")
    plot = D3plot(str(path)) if state_arrays is None else D3plot(str(path), state_array_filter=state_arrays)
    arrays = {str(getattr(key, "value", key)): value for key, value in plot.arrays.items()}
    try:
        validate_d3plot_times(arrays.get("timesteps", arrays.get("global_timesteps", [])))
    except ValueError as error:
        raise ResultsError(str(error)) from error
    return arrays


def _texts(values: object) -> list[str]:
    out = []
    for value in np.asarray(values).reshape(-1):
        text = value.decode("latin-1") if isinstance(value, bytes) else str(value)
        out.append(text.strip())
    return out


def _part_titles(arrays: dict) -> tuple[dict[int, str], list[str]]:
    titles = _texts(arrays["part_titles"]) if "part_titles" in arrays else []
    if not titles:
        return {}, []
    if "part_titles_ids" not in arrays:
        return {}, ["Part titles have no stored title IDs; titles left null rather than guessed by position"]
    ids = np.asarray(arrays["part_titles_ids"]).reshape(-1)
    if (ids.size != len(titles) or any(isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, np.integer)) or value <= 0 for value in ids)):
        raise ResultsError("Part title IDs must be positive integers aligned with the stored titles")
    if len(set(map(int, ids))) != len(titles):
        raise ResultsError("Duplicate part title IDs make title association ambiguous")
    return dict(zip(map(int, ids), titles)), []


def overview(path: str | Path) -> dict:
    """Q01: states, times, variables, parts, element counts with deletions, sibling files
    (binout shards with the shards holding each database / branch)."""
    from . import mpp_shards

    arrays = _arrays(path)
    times = np.asarray(arrays.get("timesteps", arrays.get("global_timesteps", [])), dtype=float)
    elements = {}
    for family, (ids, alive, _, history, _, _) in FAMILIES.items():
        if ids not in arrays:
            continue
        count = int(np.asarray(arrays[ids]).size)
        if not count:
            continue
        entry = {"count": count, "history_variables": int(np.asarray(arrays[history]).shape[-1])
                 if history in arrays else 0}
        if alive in arrays:
            final = np.asarray(arrays[alive])[-1]
            entry["deleted_at_last_state"] = int(count - np.count_nonzero(final))
        elements[family] = entry
    parts = [int(p) for p in _part_ids(arrays)]
    titles, warnings = _part_titles(arrays)
    folder = Path(path).parent
    binout = {"shards": [], "entries": {}, "split": {}}
    if any(mpp_shards.SHARD.match(p.name) for p in folder.iterdir()):
        binout = mpp_shards.catalog(folder)
    return {"backend": backend(), "states": int(times.size),
            "time_range": [float(times[0]), float(times[-1])] if times.size else None,
            "times": times.tolist(), "variables": sorted(arrays),
            "elements": elements, "parts": [{"id": p, "title": titles.get(p)} for p in parts],
            "warnings": warnings,
            "binout_files": binout["shards"], "binout_databases": sorted({k.split("/")[0] for k in binout["entries"]}),
            "binout_entries": binout["entries"], "binout_split": binout["split"],
            "ascii_files": sorted(p.name for p in folder.iterdir() if p.name in ASCII)}


def header(path: str | Path) -> dict:
    """d3plot control words beside the readable arrays (Q01): extra values per integration point
    (NEIPH solids, NEIPS shells/thick shells, NEIPB beams) and which tensors / deletion data are
    stored. LASSO moves stored strain tensors out of the history arrays, so a family can declare
    extra values while exposing no history-variable array."""
    try:
        from lasso.dyna.d3plot_header import D3plotHeader
    except ImportError as error:
        raise ResultsError("Reading results needs lasso-python (install the 'results' extra)") from error
    path = Path(path)
    if not path.exists():
        raise ResultsError(f"{path} does not exist")
    h = D3plotHeader().load_file(str(path))
    return {"neiph_solid": int(h.n_solid_history_vars), "neips_shell_tshell": int(h.n_shell_tshell_history_vars),
            "neipb_beam": int(h.n_beam_history_vars), "strain_tensor_stored": bool(h.has_element_strain),
            "plastic_strain_tensor_stored": bool(h.has_solid_shell_plastic_strain_tensor),
            "thermal_strain_tensor_stored": bool(h.has_solid_shell_thermal_strain_tensor),
            "deletion_data_stored": bool(h.has_element_deletion_data)}


def _part_ids(arrays: dict) -> np.ndarray:
    """Part IDs in d3plot order (part_ids, or part_titles_ids when the file only has titles)."""
    for key in ("part_ids", "part_titles_ids"):
        if key in arrays and np.asarray(arrays[key]).size:
            return np.asarray(arrays[key]).reshape(-1)
    return np.empty(0, dtype=int)


def _times(arrays: dict) -> np.ndarray:
    return np.asarray(arrays.get("timesteps", arrays.get("global_timesteps")), dtype=float)


def _index(ids: np.ndarray, wanted: list[int], kind: str) -> np.ndarray:
    position = {int(v): i for i, v in enumerate(np.asarray(ids).reshape(-1))}
    missing = [w for w in wanted if int(w) not in position]
    if missing:
        raise ResultsError(f"{kind} IDs not in the result: {missing[:10]}")
    return np.asarray([position[int(w)] for w in wanted])


def _element_values(arrays: dict, family: str, quantity: str, stored_point: int | None = None) -> tuple[np.ndarray, str]:
    """(states, elements) values of a stress component, invariant or plastic strain; IP-averaged."""
    _, _, _, _, stress_key, eps_key = FAMILIES[family]
    if quantity == "effective_plastic_strain":
        if eps_key not in arrays:
            raise ResultsError(f"No effective plastic strain for {family} elements in this d3plot")
        values = np.asarray(arrays[eps_key], dtype=float)
        note = "stored value"
        if values.ndim == 3:
            values, note = values.mean(axis=2), f"mean of {values.shape[2]} stored points"
        return values, note
    if stress_key not in arrays:
        raise ResultsError(f"No stresses for {family} elements in this d3plot")
    stress = np.asarray(arrays[stress_key], dtype=float)
    note = "stored value"
    if stress.ndim == 4:  # states, elements, points, 6
        if stored_point is not None:
            if stored_point > stress.shape[2]:
                raise ResultsError("Stored integration point is outside the stress array")
            stress, note = stress[:, :, stored_point-1, :], f"stored point {stored_point} (1-based); no averaging"
        else:
            stress, note = stress.mean(axis=2), f"mean of {stress.shape[2]} stored points"
    elif stored_point is not None:
        if stored_point != 1:
            raise ResultsError("This stress array has one stored point")
        note = "stored point 1 (1-based); no averaging"
    if quantity == "stress":
        return stress, note
    if quantity in STRESS:
        return stress[..., STRESS.index(quantity)], note
    if quantity in inv.QUANTITIES:
        flat = inv.invariants(stress.reshape(-1, 6))[quantity]
        return flat.reshape(stress.shape[:2]), note + "; " + inv.CONVENTIONS.get(quantity, quantity)
    raise ResultsError(f"Unknown element quantity {quantity!r}; use {list(STRESS)}, {list(inv.QUANTITIES)} "
                       "or effective_plastic_strain")


def history(path: str | Path, kind: str, quantity: str, ids: list[int] | None = None) -> list[dict]:
    """Q05 time histories: kind node / solid / shell / part / global; one curve per entity."""
    arrays = _arrays(path)
    times = _times(arrays)
    if kind == "global":
        key = f"global_{quantity}"
        if key not in arrays:
            raise ResultsError(f"No global {quantity!r}; available: {sorted(k[7:] for k in arrays if k.startswith('global_'))}")
        return [{"entity": None, "quantity": quantity, "time": times.tolist(),
                 "values": np.asarray(arrays[key], dtype=float).reshape(times.size, -1)[:, 0].tolist()}]
    if not ids:
        raise ResultsError(f"{kind} histories need entity IDs")
    if kind == "node":
        axis = {"x": 0, "y": 1, "z": 2}
        name, _, component = quantity.partition("_")
        if name not in ("displacement", "velocity") or component not in (*axis, "magnitude"):
            raise ResultsError("Node quantities: displacement_/velocity_ + x, y, z or magnitude")
        where = _index(arrays["node_ids"], ids, "Node")
        data = np.asarray(arrays["node_displacement" if name == "displacement" else "node_velocity"], dtype=float)
        if name == "displacement":  # d3plot holds current coordinates
            data = data - np.asarray(arrays["node_coordinates"], dtype=float)[None]
        picked = data[:, where, :]
        values = np.linalg.norm(picked, axis=2) if component == "magnitude" else picked[:, :, axis[component]]
        return [{"entity": int(i), "quantity": quantity, "time": times.tolist(), "values": values[:, n].tolist()}
                for n, i in enumerate(ids)]
    if kind == "part":
        key = f"part_{quantity}"
        if key not in arrays:
            raise ResultsError(f"No part {quantity!r}; available: {sorted(k[5:] for k in arrays if k.startswith('part_'))}")
        where = _index(_part_ids(arrays), ids, "Part")
        values = np.asarray(arrays[key], dtype=float)
        return [{"entity": int(i), "quantity": quantity, "time": times.tolist(), "values": values[:, w].tolist()}
                for i, w in zip(ids, where)]
    if kind not in FAMILIES:
        raise ResultsError("kind must be node, solid, shell, tshell, beam, part or global")
    values, note = _element_values(arrays, kind, quantity)
    where = _index(arrays[FAMILIES[kind][0]], ids, kind.capitalize())
    return [{"entity": int(i), "quantity": quantity, "time": times.tolist(), "values": values[:, w].tolist(),
             "note": note} for i, w in zip(ids, where)]


def state_times(path: str | Path) -> np.ndarray:
    """Times of all states, reading no other state arrays (to validate a requested state first)."""
    ArrayType, _, _ = _lasso()
    return _times(_arrays(path, state_arrays=[ArrayType.global_timesteps]))


def _part_elements(arrays: dict, family: str, part_ids: list[int]) -> np.ndarray:
    """Boolean selection of the ``family`` elements belonging to the user part IDs ``part_ids``."""
    if not part_ids:
        raise ResultsError("part_ids must name at least one part")
    where = _index(_part_ids(arrays), part_ids, "Part")
    key = FAMILIES[family][2]
    if key not in arrays:
        raise ResultsError(f"No {family} part assignment in this d3plot")
    owner = np.asarray(arrays[key]).reshape(-1)
    empty = [int(p) for p, w in zip(part_ids, where) if not np.any(owner == w)]
    if empty:
        raise ResultsError(f"Parts {empty} have no {family} elements")
    return np.isin(owner, where)


def field(path: str | Path, family: str, quantity: str, state: int = -1, mask: str = "alive",
          part_ids: list[int] | None = None, stored_point: int | None = None) -> dict:
    """Element values of one state with IDs, the alive mask and extrema (Q03/Q04).

    ``state`` is a 0-based index (negative counts from the end); an index outside the stored
    states is refused, never wrapped. ``part_ids`` (user part IDs, resolved through part_ids or
    part_titles_ids) restricts the returned elements and the extrema to those parts."""
    if stored_point is not None and (type(stored_point) is not int or stored_point < 1):
        raise ResultsError("stored_point must be a positive 1-based integer")
    if stored_point is not None and quantity != "stress":
        raise ResultsError("Explicit stored_point currently requires the six-component stress quantity")
    arrays = _arrays(path)
    times = _times(arrays)
    if isinstance(state, bool) or not isinstance(state, (int, np.integer)) or not -times.size <= state < times.size:
        raise ResultsError(f"State index {state!r} is out of range for {times.size} states "
                           f"(0-based, negative from the end)")
    state_index = int(state) % times.size
    values, note = _element_values(arrays, family, quantity, stored_point)
    ids = np.asarray(arrays[FAMILIES[family][0]]).reshape(-1)
    row = np.asarray(values[state_index])
    alive_key = FAMILIES[family][1]
    deletion_data = alive_key in arrays
    if not deletion_data and mask != "all":
        raise ResultsError(f"This d3plot stores no element deletion data for {family} elements, so mask={mask} "
                           "cannot be applied (deletion status unknown); use mask=all")
    alive = np.asarray(arrays[alive_key])[state_index] != 0 if deletion_data else np.ones(ids.size, bool)
    parts = None
    if part_ids is not None:
        parts = [int(p) for p in part_ids]
        keep = _part_elements(arrays, family, parts)
        ids, row, alive = ids[keep], row[keep], alive[keep]
    selection = inv.masked(alive, mask)
    extrema = ({component: inv.extrema(row[:, i], ids, selection) for i, component in enumerate(STRESS)}
               if quantity == "stress" else inv.extrema(row, ids, selection))
    result = {"backend": backend(), "family": family, "quantity": quantity, "state": state_index,
            "time": float(times[state_index]), "ids": ids, "values": row, "alive": alive,
            "mask": mask, "part_ids": parts, "extrema": extrema, "note": note,
            "deletion_data": deletion_data}
    if quantity == "stress":
        stored = np.asarray(arrays[FAMILIES[family][4]])
        result.update(components=list(STRESS), sampling={"kind": "stored_point" if stored_point else "mean_stored_points",
                      "count": int(stored.shape[2]) if stored.ndim == 4 else 1,
                      "index": stored_point,
                      "native_layer_equivalence": "not inferred"})
    return result


def binout_curves(path: str | Path, database: str, component: str, branch: str | None = None,
                  shard: str | None = None) -> dict:
    """Q06: one component of a binout database (or branch) by name, over all MPP shards beside
    ``path``; see :mod:`mpp_shards` for the merge rules (time plus one column per stored ID)."""
    from . import mpp_shards

    return mpp_shards.read(path, database, component, branch, shard)


__all__ = ["ASCII", "FAMILIES", "ResultsError", "backend", "binout_curves", "field", "header", "history",
           "overview", "state_times"]
