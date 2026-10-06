"""Element quality and node checks computed from the keyword deck (no LS-PrePost).

Metric definitions are the engine's own (Verdict-style), stated in every result; they are
not LS-PrePost's quality panel numbers. Only objective defects (inverted or zero-measure
elements, undefined nodes) are errors; every other metric is reported as a distribution
with worst elements and judged only against thresholds the caller provides.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from .geometry import _index, elements, nodes

if TYPE_CHECKING:
    from .deck import KeywordDeck

# Hexahedron corner -> its three edge neighbours, right-handed (Verdict ordering = LS-DYNA numbering).
HEX_CORNERS = ((1, 3, 4), (2, 0, 5), (3, 1, 6), (0, 2, 7), (7, 5, 0), (4, 6, 1), (5, 7, 2), (6, 4, 3))
HEX_EDGES = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7))
HEX_TETS = ((0, 1, 2, 6), (0, 2, 3, 6), (0, 3, 7, 6), (0, 7, 4, 6), (0, 4, 5, 6), (0, 5, 1, 6))
TET_EDGES = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))
DEFINITIONS = {
    "min_scaled_jacobian": "min over the 8 corners of det(e1,e2,e3)/(|e1||e2||e3|); 1 ideal, <= 0 inverted",
    "aspect_ratio": "longest edge / shortest edge",
    "volume": "signed volume (hexahedron: 6 tetrahedra around diagonal n1-n7); <= 0 inverted or degenerate",
    "warpage_deg": "quad: angle between the two triangle normals, worse of the two diagonals",
    "min_angle_deg": "smallest interior corner angle", "max_angle_deg": "largest interior corner angle",
    "area": "quad: half the norm of the diagonal cross product; triangle: half the edge cross product",
}
WORST = 20


def _edges_ratio(points: np.ndarray, edges: tuple) -> np.ndarray:
    lengths = np.stack([np.linalg.norm(points[:, b] - points[:, a], axis=1) for a, b in edges], axis=1)
    shortest = lengths.min(axis=1)
    return np.divide(lengths.max(axis=1), shortest, out=np.full(len(points), np.inf), where=shortest > 0)


def _triple(p: np.ndarray, a: int, b: int, c: int, d: int) -> np.ndarray:
    return np.einsum("ij,ij->i", np.cross(p[:, b] - p[:, a], p[:, c] - p[:, a]), p[:, d] - p[:, a])


def _hex_metrics(p: np.ndarray) -> dict[str, np.ndarray]:
    jac = []
    for corner, (a, b, c) in enumerate(HEX_CORNERS):
        e1, e2, e3 = p[:, a] - p[:, corner], p[:, b] - p[:, corner], p[:, c] - p[:, corner]
        det = np.einsum("ij,ij->i", np.cross(e1, e2), e3)
        norm = np.linalg.norm(e1, axis=1) * np.linalg.norm(e2, axis=1) * np.linalg.norm(e3, axis=1)
        jac.append(np.divide(det, norm, out=np.zeros_like(det), where=norm > 0))
    volume = sum(_triple(p, *tet) for tet in HEX_TETS) / 6.0
    return {"min_scaled_jacobian": np.min(jac, axis=0), "aspect_ratio": _edges_ratio(p, HEX_EDGES), "volume": volume}


def _tet_metrics(p: np.ndarray) -> dict[str, np.ndarray]:
    return {"aspect_ratio": _edges_ratio(p, TET_EDGES), "volume": _triple(p, 0, 1, 2, 3) / 6.0}


def _angles(p: np.ndarray, count: int) -> np.ndarray:
    result = []
    for i in range(count):
        a, b = p[:, (i - 1) % count] - p[:, i], p[:, (i + 1) % count] - p[:, i]
        norm = np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-300)
        result.append(np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", a, b) / norm, -1.0, 1.0))))
    return np.stack(result, axis=1)


def _shell_metrics(p: np.ndarray, triangle: np.ndarray) -> dict[str, np.ndarray]:
    out = {k: np.zeros(len(p)) for k in ("warpage_deg", "min_angle_deg", "max_angle_deg", "aspect_ratio", "area")}
    quads = ~triangle
    if quads.any():
        q = p[quads]
        angles = _angles(q, 4)
        warp = []
        for a, b, c, d in ((0, 1, 2, 3), (1, 2, 3, 0)):
            n1, n2 = np.cross(q[:, b] - q[:, a], q[:, c] - q[:, a]), np.cross(q[:, c] - q[:, a], q[:, d] - q[:, a])
            norm = np.maximum(np.linalg.norm(n1, axis=1) * np.linalg.norm(n2, axis=1), 1e-300)
            warp.append(np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", n1, n2) / norm, -1.0, 1.0))))
        out["warpage_deg"][quads] = np.max(warp, axis=0)
        out["min_angle_deg"][quads], out["max_angle_deg"][quads] = angles.min(axis=1), angles.max(axis=1)
        out["aspect_ratio"][quads] = _edges_ratio(q, ((0, 1), (1, 2), (2, 3), (3, 0)))
        out["area"][quads] = 0.5 * np.linalg.norm(np.cross(q[:, 2] - q[:, 0], q[:, 3] - q[:, 1]), axis=1)
    if triangle.any():
        t = p[triangle][:, :3]
        angles = _angles(t, 3)
        out["min_angle_deg"][triangle], out["max_angle_deg"][triangle] = angles.min(axis=1), angles.max(axis=1)
        out["aspect_ratio"][triangle] = _edges_ratio(t, ((0, 1), (1, 2), (2, 0)))
        out["area"][triangle] = 0.5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)
    return out


def _summary(eids: np.ndarray, metrics: dict[str, np.ndarray], thresholds: dict, low_is_bad: set[str]) -> dict:
    result = {}
    for name, values in metrics.items():
        finite = np.isfinite(values)
        entry = {"min": float(values[finite].min()) if finite.any() else None,
                 "max": float(values[finite].max()) if finite.any() else None,
                 "mean": float(values[finite].mean()) if finite.any() else None,
                 "non_finite": int((~finite).sum())}
        order = np.argsort(values) if name in low_is_bad else np.argsort(-np.where(finite, values, np.inf))
        entry["worst"] = [{"id": int(eids[i]), "value": float(values[i])} for i in order[:WORST]]
        limit = thresholds.get(name)
        if limit is not None:
            failing = values < limit if name in low_is_bad else values > limit
            entry.update(threshold=limit, failing=int(failing.sum()), failing_ids=eids[failing][:200].tolist())
        result[name] = entry
    return result


# Offsets to the cell itself and to 13 of its 26 neighbours: every neighbouring pair once.
_FORWARD = np.array([(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
                     if (dx, dy, dz) >= (0, 0, 0)], dtype=np.int64)


def _cell_hash(keys: np.ndarray) -> np.ndarray:
    """splitmix64-style mix of the three cell indices (lookups still compare the keys exactly)."""
    value = np.zeros(len(keys), dtype=np.uint64)
    with np.errstate(over="ignore"):
        for column in range(3):
            value = (value ^ keys[:, column].astype(np.uint64)) + np.uint64(0x9E3779B97F4A7C15)
            value = (value ^ (value >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
            value = (value ^ (value >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
            value ^= value >> np.uint64(31)
    return value


def _expand(lengths: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """``(owner, rank)`` for ``lengths[k]`` items per owner: owner index and position in its run."""
    owner = np.repeat(np.arange(len(lengths)), lengths)
    return owner, np.arange(int(lengths.sum())) - np.repeat(np.cumsum(lengths) - lengths, lengths)


def coincident_nodes(ids: np.ndarray, xyz: np.ndarray, tolerance: float) -> list[tuple[int, int, float]]:
    """All node pairs closer than ``tolerance`` (exact: cells of size ``tolerance``, 27 neighbours)."""
    if tolerance <= 0 or len(ids) < 2:
        return []
    keys = np.floor(np.asarray(xyz, dtype=float) / tolerance).astype(np.int64)
    cells, inverse, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.ravel()
    members = np.argsort(inverse, kind="stable")  # point indices grouped by cell
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    codes = _cell_hash(cells)
    order = np.argsort(codes)
    sorted_codes = codes[order]
    found_a, found_b = [], []
    for offset in _FORWARD:
        target = cells + offset
        hashes = _cell_hash(target)
        low = np.searchsorted(sorted_codes, hashes, "left")
        source, rank = _expand(np.searchsorted(sorted_codes, hashes, "right") - low)
        candidate = order[low[source] + rank]  # every cell sharing the hash; exact match below
        match = (cells[candidate] == target[source]).all(axis=1)
        first, second = source[match], candidate[match]
        sizes = counts[first] * counts[second]
        if not sizes.size:
            continue
        pair, local = _expand(sizes)
        width = counts[second][pair]
        a = members[starts[first][pair] + local // width]
        b = members[starts[second][pair] + local % width]
        if not offset.any():
            keep = a < b
            a, b = a[keep], b[keep]
        found_a.append(a)
        found_b.append(b)
    if not found_a:
        return []
    a, b = np.concatenate(found_a), np.concatenate(found_b)
    distance = np.linalg.norm(xyz[a] - xyz[b], axis=1)
    close = distance <= tolerance
    pairs = {}
    for i, j, d in zip(a[close], b[close], distance[close]):
        low, high = sorted((int(ids[i]), int(ids[j])))
        pairs[(low, high)] = float(d)
    return sorted((low, high, d) for (low, high), d in pairs.items())


def _defined(conn: np.ndarray, lookup: np.ndarray) -> np.ndarray:
    """Rows whose node IDs all exist."""
    inside = (conn >= 0) & (conn < lookup.size)
    found = np.zeros_like(inside)
    found[inside] = lookup[conn[inside]] >= 0
    return found.all(axis=1)


def check_quality(deck: KeywordDeck, thresholds: dict | None = None, coincident_tol: float | None = None) -> dict:
    """Element quality distributions, objective errors and optional coincident-node pairs."""
    thresholds = thresholds or {}
    skipped: list[str] = []
    node_ids, xyz = nodes(deck, skipped)
    node_gaps = bool(skipped)  # unread *NODE blocks: missing nodes are not proof of an error
    lookup = _index(node_ids)
    report: dict = {"definitions": DEFINITIONS, "errors": [], "not_graded": [], "nodes": int(node_ids.size)}
    used: set[int] = set()

    def keep_defined(kind: str, eids: np.ndarray, conn: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        ok = _defined(conn, lookup)
        if not ok.all():
            entry = {"kind": f"{kind}_with_undefined_nodes", "count": int((~ok).sum()), "ids": eids[~ok][:200].tolist()}
            if node_gaps:
                report["not_graded"].append({**entry, "reason": "some *NODE blocks were not read"})
            else:
                report["errors"].append(entry)
        return eids[ok], conn[ok]

    eids, _, conn = elements(deck, "*ELEMENT_SOLID", 8, skipped)
    used.update(np.unique(conn).tolist())
    eids, conn = keep_defined("solids", eids, conn)
    if eids.size:
        distinct = (np.diff(np.sort(conn, axis=1), axis=1) != 0).sum(axis=1) + 1
        hexa, tet = distinct == 8, (distinct == 4) & (conn[:, 4:] == conn[:, [3]]).all(axis=1)
        solids: dict = {}
        for name, mask, metrics, low in (("hexahedra", hexa, _hex_metrics, {"min_scaled_jacobian", "volume"}),
                                         ("tetrahedra", tet, _tet_metrics, {"volume"})):
            if not mask.any():
                continue
            points = xyz[lookup[conn[mask] if name == "hexahedra" else conn[mask][:, :4]]]
            values = metrics(points)
            solids[name] = {"count": int(mask.sum()), **_summary(eids[mask], values, thresholds, low)}
            bad = values["volume"] <= 0
            if name == "hexahedra":
                bad |= values["min_scaled_jacobian"] <= 0
            if bad.any():
                report["errors"].append({"kind": f"inverted_or_degenerate_{name}", "count": int(bad.sum()),
                                         "ids": eids[mask][bad][:200].tolist()})
        other = ~hexa & ~tet
        if other.any():
            solids["other_degenerate_solids"] = {"count": int(other.sum()), "note": "pentahedra/pyramids not graded"}
        report["solids"] = solids
    eids, _, conn = elements(deck, "*ELEMENT_SHELL", 4, skipped)
    triangle = (conn[:, 3] == conn[:, 2]) | (conn[:, 3] == 0) if eids.size else np.zeros(0, dtype=bool)
    conn = np.where(conn == 0, conn[:, [2]], conn) if eids.size else conn
    used.update(np.unique(conn).tolist())
    ok = _defined(conn, lookup) if eids.size else np.zeros(0, dtype=bool)
    eids, conn, triangle = keep_defined("shells", eids, conn)[0], conn[ok], triangle[ok]
    if eids.size:
        values = _shell_metrics(xyz[lookup[conn]], triangle)
        report["shells"] = {"count": int(eids.size), "triangles": int(triangle.sum()),
                            **_summary(eids, values, thresholds, {"min_angle_deg", "area"})}
        bad = values["area"] <= 0
        if bad.any():
            report["errors"].append({"kind": "zero_area_shells", "count": int(bad.sum()), "ids": eids[bad][:200].tolist()})
    unused = np.setdiff1d(node_ids, np.asarray(sorted(used), dtype=np.int64))
    note = "may be used by beams, masses, constraints or sets"
    if skipped:
        note += "; incomplete because some mesh blocks were not read (see unchecked_mesh_blocks)"
    report["unchecked_mesh_blocks"] = skipped
    report["nodes_not_in_solid_or_shell_elements"] = {"count": int(unused.size), "sample": unused[:50].tolist(),
                                                      "note": note}
    if coincident_tol is not None:
        pairs = coincident_nodes(node_ids, xyz, coincident_tol)
        report["coincident_nodes"] = {"tolerance": coincident_tol, "count": len(pairs),
                                      "pairs": [{"a": a, "b": b, "distance": d} for a, b, d in pairs[:200]]}
    report["ok"] = not report["errors"]
    return report
