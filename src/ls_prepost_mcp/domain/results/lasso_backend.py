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


def _arrays(path: str | Path) -> dict:
    _, _, D3plot = _lasso()
    path = Path(path)
    if not path.exists():
        raise ResultsError(f"{path} does not exist")
    return {str(getattr(key, "value", key)): value for key, value in D3plot(str(path)).arrays.items()}


def _texts(values: object) -> list[str]:
    out = []
    for value in np.asarray(values).reshape(-1):
        text = value.decode("latin-1") if isinstance(value, bytes) else str(value)
        out.append(text.strip())
    return out


def overview(path: str | Path) -> dict:
    """Q01: states, times, variables, parts, element counts with deletions, sibling files."""
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
    titles = _texts(arrays["part_titles"]) if "part_titles" in arrays else []
    folder = Path(path).parent
    binout = sorted(p.name for p in folder.glob("binout*"))
    databases = []
    if binout:
        _, Binout, _ = _lasso()
        databases = sorted(str(name) for name in Binout(str(folder / "binout*")).read())
    return {"backend": backend(), "states": int(times.size),
            "time_range": [float(times[0]), float(times[-1])] if times.size else None,
            "times": times.tolist() if times.size <= 2000 else None, "variables": sorted(arrays),
            "elements": elements, "parts": [{"id": p, "title": titles[i] if i < len(titles) else None}
                                            for i, p in enumerate(parts)],
            "binout_files": binout, "binout_databases": databases,
            "ascii_files": sorted(p.name for p in folder.iterdir() if p.name in ASCII)}


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


def _element_values(arrays: dict, family: str, quantity: str) -> tuple[np.ndarray, str]:
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
        stress, note = stress.mean(axis=2), f"mean of {stress.shape[2]} stored points"
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


def field(path: str | Path, family: str, quantity: str, state: int = -1, mask: str = "alive") -> dict:
    """Element values of one state with IDs, the alive mask and extrema (Q03/Q04)."""
    arrays = _arrays(path)
    times = _times(arrays)
    values, note = _element_values(arrays, family, quantity)
    ids = np.asarray(arrays[FAMILIES[family][0]]).reshape(-1)
    alive_key = FAMILIES[family][1]
    alive = np.asarray(arrays[alive_key])[state] != 0 if alive_key in arrays else np.ones(ids.size, bool)
    selection = inv.masked(alive, mask)
    state_index = int(state % times.size)
    return {"backend": backend(), "family": family, "quantity": quantity, "state": state_index,
            "time": float(times[state_index]), "ids": ids, "values": values[state_index], "alive": alive,
            "mask": mask, "extrema": inv.extrema(values[state_index], ids, selection), "note": note}


def binout_curves(path: str | Path, database: str, component: str) -> dict:
    """Q06: one component of a binout database by name (time plus one column per stored ID)."""
    _, Binout, _ = _lasso()
    reader = Binout(str(path))
    if database not in reader.read():
        raise ResultsError(f"binout has no {database!r}; available: {sorted(reader.read())}")
    names = reader.read(database)
    if component not in names:
        raise ResultsError(f"{database} has no {component!r}; available: {sorted(names)}")
    values = np.asarray(reader.read(database, component), dtype=float)
    ids = np.asarray(reader.read(database, "ids")).reshape(-1).tolist() if "ids" in names else None
    return {"backend": backend(), "database": database, "component": component,
            "time": np.asarray(reader.read(database, "time"), dtype=float).tolist(),
            "ids": ids, "values": values.tolist()}


__all__ = ["ASCII", "FAMILIES", "ResultsError", "backend", "binout_curves", "field", "history", "overview"]
