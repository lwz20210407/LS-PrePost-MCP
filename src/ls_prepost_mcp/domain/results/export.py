"""Field export to CSV / NPZ with semantic metadata (tasks.yaml Q03).

Takes the result of :func:`lasso_backend.field` and writes one row per element: ID, value and
the alive flag of that state. The metadata travels with the data: quantity, family, state, time,
how stored integration points were treated, the mask policy (Q04), backend, coordinate system
and units. Values are in the model's own units and nothing is converted; ``units`` only labels
them (the caller declares the unit system, as for every other recipe).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from . import invariants as inv
from .lasso_backend import ResultsError

FORMATS = ("csv", "npz")


def _meta(result: dict, units: str | None) -> dict:
    meta = {"quantity": result["quantity"], "family": result["family"], "state": result["state"],
            "time": result["time"], "points": result.get("note", "stored value"), "mask": result["mask"],
            "coordinate_system": "global (as stored in d3plot)", "backend": result["backend"],
            "units": units or "model units, not converted (unit system not declared)",
            "rows": int(np.asarray(result["ids"]).size), "extrema": result.get("extrema"),
            "formula": inv.definition(result["quantity"]), "conventions": dict(inv.CONVENTIONS)}
    if result.get("deletion_data") is False:
        meta["deletion_status"] = "unknown: the d3plot stores no element deletion data; alive column is not a deletion flag"
    if result.get("mask_policy") is not None:
        meta["mask_policy"] = result["mask_policy"]
    if result.get("part_ids") is not None:
        meta["part_ids"] = [int(p) for p in result["part_ids"]]
    return meta


def export_field(result: dict, path: str | Path, units: str | None = None, fmt: str | None = None) -> dict:
    """Write ``result`` to ``path`` as CSV (``# key: value`` header lines, then ``id,value,alive``)
    or NPZ (arrays ids / values / alive and ``meta`` as JSON); returns the file and its SHA-256."""
    path = Path(path)
    fmt = (fmt or path.suffix.lstrip(".")).lower()
    if fmt not in FORMATS:
        raise ResultsError(f"Format must be one of {FORMATS} (or the file suffix), not {fmt!r}")
    ids = np.asarray(result["ids"]).reshape(-1)
    values = np.asarray(result["values"], dtype=float).reshape(-1)
    alive = np.asarray(result["alive"], dtype=bool).reshape(-1)
    if not ids.size == values.size == alive.size:
        raise ResultsError(f"ids, values and alive differ in length ({ids.size}, {values.size}, {alive.size})")
    if path.exists():
        raise ResultsError(f"{path} exists; choose a new file name")
    meta = _meta(result, units)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        header = "".join(f"# {key}: {json.dumps(value, default=str)}\n" for key, value in meta.items())
        rows = "".join(f"{int(i)},{v:.9g},{int(a)}\n" for i, v, a in zip(ids, values, alive))
        path.write_text(header + "id,value,alive\n" + rows, encoding="utf-8")
    else:
        with path.open("wb") as handle:
            np.savez(handle, ids=ids, values=values, alive=alive, meta=np.asarray(json.dumps(meta, default=str)))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": str(path), "format": fmt, "rows": int(ids.size), "sha256": digest, "meta": meta}


def read_field(path: str | Path) -> dict:
    """Read a file written by :func:`export_field` back into ids / values / alive / meta."""
    path = Path(path)
    if path.suffix.lower() == ".npz":
        with np.load(path, allow_pickle=False) as data:
            return {"ids": data["ids"], "values": data["values"], "alive": data["alive"],
                    "meta": json.loads(str(data["meta"]))}
    meta, rows = {}, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            key, _, value = line[2:].partition(": ")
            meta[key] = json.loads(value)
        elif line and line != "id,value,alive":
            rows.append(line.split(","))
    if not rows:  # zero-row export (for example mask=deleted before any deletion)
        return {"ids": np.empty(0, dtype=np.int64), "values": np.empty(0, dtype=float),
                "alive": np.empty(0, dtype=bool), "meta": meta}
    table = np.asarray(rows, dtype=object)
    return {"ids": table[:, 0].astype(np.int64), "values": table[:, 1].astype(float),
            "alive": table[:, 2].astype(int).astype(bool), "meta": meta}


__all__ = ["FORMATS", "export_field", "read_field"]
