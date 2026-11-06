"""Keyword-level initial penetration check between two contact surfaces (tasks.yaml P06).

Surfaces come from ``parts``, a ``part_set`` or a ``segment_set``; the slave side may also be a
``node_set``. Solid parts contribute their outward exterior faces (one-sided), shell parts their
elements (two-sided, contact thickness from the section thickness T1). A slave node penetrates
when it projects inside a master triangle and its signed distance to the nearest such triangle
is below the contact offset, half the slave plus half the master thickness. Contact scale
factors (SST, MST, SFST, ...) and per-element shell thickness cards are not applied; the report
lists these assumptions. Nothing is changed.
"""
from __future__ import annotations

from contextlib import nullcontext
from typing import TYPE_CHECKING

import numpy as np

from . import lists
from .fields import FieldError
from .geometry import _index, elements, exterior_segments, nodes
from .layouts import Unsupported

if TYPE_CHECKING:
    from .deck import KeywordDeck

ASSUMPTIONS = ["shell contact thickness = section T1 (element thickness cards and SST/MST/SFST not applied)",
               "segment sets are one-sided with their written orientation and zero thickness",
               "penetrations deeper than about one master face size are not searched"]

HARD_LIMITS = dict(max_contacts=100, max_slave_nodes=100_000, max_master_triangles=200_000,
                   max_cells=1_000_000, max_pairs=1_000_000, max_report=50)
SUPPORTED_CONTACTS = frozenset(("*CONTACT_AUTOMATIC_SURFACE_TO_SURFACE", "*CONTACT_AUTOMATIC_SINGLE_SURFACE",
    "*CONTACT_ERODING_SURFACE_TO_SURFACE", "*CONTACT_TIED_SURFACE_TO_SURFACE_OFFSET", "*CONTACT_AUTOMATIC_NODES_TO_SURFACE"))


class GeometryBudgetError(FieldError):
    """An estimate was not admitted; it is not a zero-penetration result."""


class GeometryBudget:
    def __init__(self, limits):
        self.limits = limits
        self.used = dict.fromkeys(("max_slave_nodes", "max_master_triangles", "max_cells", "max_pairs"), 0)
        self.reported = 0

    def claim(self, key, amount):
        amount = int(amount)
        if amount < 0 or amount > self.limits[key] - self.used[key]:
            raise GeometryBudgetError(f"{key} budget not admitted ({amount} requested)")
        self.used[key] += amount

    def bound(self, key, amount):
        if amount > self.limits[key] - self.used[key]:
            raise GeometryBudgetError(f"{key} conservative surface expansion budget not admitted")


def _surface_admission(deck, spec, budget, slave=False):
    """Bound existing builders before they expand element faces/list rows."""
    if "segment_set" in spec:
        matches = []
        for block in deck.blocks("*SET_SEGMENT*"):
            if deck.get(block, "sid").value == spec["segment_set"]:
                matches.append(block)
        if len(matches) > 1:
            raise FieldError("Multiple/collected segment definitions are not evaluated by this estimate")
        count = sum(len(deck.layout(block).rows) for block in matches)
        estimate = count * (4 if slave else 2)
    else:
        if "part_set" in spec:
            operands = sum(max(0, len(block.lines) - 2) * 8 for block in deck.blocks("*SET_PART*")
                           if deck.get(block, "sid").value == spec["part_set"])
            budget.bound("max_slave_nodes" if slave else "max_master_triangles", operands)
        # geometry.elements materializes the whole block before Part filtering.
        # This deliberately conservative upper bound does not invent coverage.
        solids = shells = 0
        for block in deck.iter_blocks():
            if block.name == "*ELEMENT_SOLID" or block.name.startswith("*ELEMENT_SOLID_"):
                solids += len(deck.layout(block).rows)
            elif block.name == "*ELEMENT_SHELL" or block.name.startswith("*ELEMENT_SHELL_"):
                shells += len(deck.layout(block).rows)
        estimate = (6 * solids + shells) * (4 if slave else 2)
    budget.bound("max_slave_nodes" if slave else "max_master_triangles", estimate)


def _set_members(deck: KeywordDeck, prefix: str, sid: int) -> list[int]:
    """Members of set ``sid``; ``_COLLECT`` blocks with that SID are merged."""
    if prefix == "*SET_NODE":
        from .node_sets import NodeSets

        return NodeSets(deck, allow_collect_lists=True).resolve(sid, check_nodes=False)
    found = []
    for block in deck.blocks(prefix + "*"):
        try:
            if deck.get(block, "sid").value == sid:
                found.append(block)
        except (FieldError, KeyError):
            continue
    if not found:
        raise FieldError(f"{prefix} {sid} not found")
    if len(found) > 1 and not all(lists.collected(block.name) for block in found):
        raise FieldError(f"{prefix} {sid} is defined by {len(found)} blocks that are not all _COLLECT")
    return [member for block in found for member in deck.members(block)]


def _shell_thickness(deck: KeywordDeck, part: int) -> float:
    hits = deck.find("*PART", pid=part)
    if not hits:
        raise FieldError(f"Part {part} not found")
    block, row = hits[0]
    secid = deck.get(block, "secid", row=row).value
    for section, _ in deck.find("*SECTION_SHELL", secid=secid):
        return float(deck.get(section, "t1").value or 0.0)
    raise FieldError(f"*SECTION_SHELL {secid} of part {part} not found")


def _surface(deck: KeywordDeck, spec: dict, budget=None, *, slave=False) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(faces[m, 4], thickness[m], two_sided[m])``; triangles as ``a b c c``."""
    if budget is not None:
        _surface_admission(deck, spec, budget, slave)
    if "segment_set" in spec:
        sid = int(spec["segment_set"])
        for block in deck.blocks("*SET_SEGMENT*"):
            try:
                layout = deck.layout(block)
                if deck.get(block, "sid").value != sid:
                    continue
            except (FieldError, KeyError, Unsupported):
                continue
            faces = np.asarray([[int(deck.get(block, f"n{i}", row=key).value or 0) for i in range(1, 5)]
                                for key in layout.rows], dtype=np.int64).reshape(-1, 4)
            faces = np.where(faces == 0, faces[:, [2]], faces)
            return faces, np.zeros(len(faces)), np.zeros(len(faces), dtype=bool)
        raise FieldError(f"*SET_SEGMENT {sid} not found")
    parts = [int(p) for p in spec["parts"]] if "parts" in spec else _set_members(deck, "*SET_PART", int(spec["part_set"]))
    solid = exterior_segments(deck, parts=parts)
    _, pids, conn = elements(deck, "*ELEMENT_SHELL", 4)
    keep = np.isin(pids, parts)
    shells = np.where(conn[keep] == 0, conn[keep][:, [2]], conn[keep])
    thickness = np.asarray([_shell_thickness(deck, int(p)) for p in pids[keep]]) if keep.any() else np.zeros(0)
    faces = np.concatenate([solid, shells]) if len(shells) else solid
    return (faces, np.concatenate([np.zeros(len(solid)), thickness]),
            np.concatenate([np.zeros(len(solid), dtype=bool), np.ones(len(shells), dtype=bool)]))


def _slave(deck: KeywordDeck, spec: dict, budget=None) -> tuple[np.ndarray, np.ndarray]:
    """Slave node IDs and their contact thickness."""
    if "node_set" in spec:
        from .node_sets import NodeSets, integer

        sid = integer(spec["node_set"], "Node set SID", positive=True)
        kwargs = {"max_work": budget.limits["max_slave_nodes"] - budget.used["max_slave_nodes"]} if budget else {}
        index = NodeSets(deck, allow_collect_lists=True, **kwargs)
        if budget is not None:
            # The shared resolver builds each LIST operand before its work
            # check. Bound that pre-existing allocation with a conservative
            # eight-slots-per-data-line estimate, without another list parser.
            estimate = sum(max(0, len(block.lines) - 2) * 8 for blocks in index.blocks.values() for block in blocks)
            budget.bound("max_slave_nodes", estimate)
        ids = np.unique(np.asarray(index.resolve(sid), dtype=np.int64))
        return ids, np.zeros(len(ids))
    faces, thickness, _ = _surface(deck, spec, budget, slave=True)
    ids = np.unique(faces)
    per_node = np.zeros(len(ids))
    np.maximum.at(per_node, np.searchsorted(ids, faces.ravel()), np.repeat(thickness, 4))
    return ids, per_node


def _cells(points_min: np.ndarray, points_max: np.ndarray, size: float, budget=None) -> tuple[np.ndarray, np.ndarray]:
    """``(owner, cell keys)`` for every grid cell overlapped by each box."""
    if budget is not None:
        if not np.isfinite(size) or size <= 0:
            raise GeometryBudgetError("grid size is not finite/positive")
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            lo, hi = np.floor(points_min / size), np.floor(points_max / size)
        if not (np.isfinite(lo).all() and np.isfinite(hi).all()) or (np.abs(lo) >= 2**60).any() or (np.abs(hi) >= 2**60).any():
            raise GeometryBudgetError("coordinate grid range is not admitted")
        low, high = lo.astype(np.int64), hi.astype(np.int64)
    else:
        low = np.floor(points_min / size).astype(np.int64)
        high = np.floor(points_max / size).astype(np.int64)
    span = high - low + 1
    if budget is not None:
        counts, total = [], 0
        for row in span:
            count = int(row[0]) * int(row[1]) * int(row[2])
            if count < 1:
                raise GeometryBudgetError("invalid cell span")
            total += count
            budget.bound("max_cells", total)
            counts.append(count)
        budget.claim("max_cells", total)
        counts = np.asarray(counts, dtype=np.int64)
    else:
        counts = span.prod(axis=1)
    owner = np.repeat(np.arange(len(low)), counts)
    rank = np.arange(int(counts.sum())) - np.repeat(np.cumsum(counts) - counts, counts)
    sx, sy = span[owner, 0], span[owner, 1]
    offset = np.stack([rank % sx, (rank // sx) % sy, rank // (sx * sy)], axis=1)
    return owner, low[owner] + offset


def _dot(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    return np.einsum("ij,ij->i", u, v)


def _closest_points(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Closest points on triangles ``abc`` (Ericson, Real-Time Collision Detection 5.1.5).

    Feature codes: 0 face, 1 edge ab, 2 edge bc, 3 edge ca, 4 vertex a, 5 vertex b, 6 vertex c.
    """
    ab, ac = b - a, c - a
    d1, d2 = _dot(ab, p - a), _dot(ac, p - a)
    d3, d4 = _dot(ab, p - b), _dot(ac, p - b)
    d5, d6 = _dot(ab, p - c), _dot(ac, p - c)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    q = np.empty_like(p)
    feature = np.full(len(p), -1)

    def take(mask: np.ndarray, point: np.ndarray, code: int) -> None:
        chosen = mask & (feature < 0)
        q[chosen], feature[chosen] = point[chosen], code

    with np.errstate(divide="ignore", invalid="ignore"):
        take((d1 <= 0) & (d2 <= 0), a, 4)
        take((d3 >= 0) & (d4 <= d3), b, 5)
        take((vc <= 0) & (d1 >= 0) & (d3 <= 0), a + (d1 / (d1 - d3))[:, None] * ab, 1)
        take((d6 >= 0) & (d5 <= d6), c, 6)
        take((vb <= 0) & (d2 >= 0) & (d6 <= 0), a + (d2 / (d2 - d6))[:, None] * ac, 3)
        along = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        take((va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0), b + along[:, None] * (c - b), 2)
        total = va + vb + vc
        take(np.ones(len(p), dtype=bool), a + (vb / total)[:, None] * ab + (vc / total)[:, None] * ac, 0)
    return q, feature


def _pseudonormals(tri: np.ndarray, tri_nodes: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Face normals, edge pseudonormals ``[t, 3, 3]`` (ab, bc, ca) and angle-weighted vertex
    pseudonormals ``[t, 3, 3]`` (Baerentzen and Aanaes 2005): signs are exact for a closed,
    consistently oriented surface."""
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    nodes_flat, inverse = np.unique(tri_nodes, return_inverse=True)
    inverse = inverse.reshape(-1, 3)
    vertex = np.zeros((len(nodes_flat), 3))
    for k in range(3):
        u, v = tri[:, (k + 1) % 3] - tri[:, k], tri[:, (k + 2) % 3] - tri[:, k]
        cosine = _dot(u, v) / (np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1))
        np.add.at(vertex, inverse[:, k], np.arccos(np.clip(cosine, -1.0, 1.0))[:, None] * normal)
    pairs = np.stack([tri_nodes[:, [0, 1]], tri_nodes[:, [1, 2]], tri_nodes[:, [2, 0]]], axis=1)  # [t, 3, 2]
    _, edge_id = np.unique(np.sort(pairs.reshape(-1, 2), axis=1), axis=0, return_inverse=True)
    edge_id = edge_id.reshape(-1, 3)
    edge = np.zeros((int(edge_id.max()) + 1, 3))
    np.add.at(edge, edge_id.ravel(), np.repeat(normal, 3, axis=0))
    return normal, edge[edge_id], vertex[inverse]


def check_penetration(deck: KeywordDeck, slave: dict, master: dict, tolerance: float = 0.0,
                      max_report: int = 200, *, budget=None) -> dict:
    """Initial penetrations of ``slave`` nodes into the ``master`` surface (read-only)."""
    if budget is not None:
        # Existing geometry helpers read the complete node table, including
        # unrelated nodes. Admit that allocation before calling them as well.
        node_rows = sum(len(deck.layout(block).rows) for block in deck.blocks("*NODE"))
        if node_rows > budget.limits["max_slave_nodes"] + 4 * budget.limits["max_master_triangles"]:
            raise GeometryBudgetError("whole-model node table exceeds conservative geometry allocation budget")
    node_ids, xyz = nodes(deck)
    if budget is not None:
        if not np.isfinite(xyz).all():
            raise FieldError("Non-finite contact coordinates")
        if (node_ids <= 0).any() or len(np.unique(node_ids)) != len(node_ids):
            raise FieldError("Geometry estimate requires unique positive model node IDs")
    lookup = _index(node_ids)
    faces, master_thickness, two_sided = _surface(deck, master, budget)
    slave_ids, slave_thickness = _slave(deck, slave, budget)
    report = {"slave_nodes": int(len(slave_ids)), "master_faces": int(len(faces)), "assumptions": ASSUMPTIONS}
    if not len(faces) or not len(slave_ids):
        if budget is not None:
            raise FieldError("Empty master surface or slave selection was not evaluated")
        return {**report, "penetrating": 0, "max_depth": 0.0, "nodes": []}
    if budget is not None:
        budget.claim("max_slave_nodes", len(slave_ids))
        budget.bound("max_master_triangles", 2 * len(faces))
        if not (np.isfinite(master_thickness).all() and np.isfinite(slave_thickness).all()):
            raise FieldError("Non-finite contact coordinates or thickness")
        if (master_thickness < 0).any() or (slave_thickness < 0).any():
            raise FieldError("Negative shell contact thickness")
        if np.isin(slave_ids, faces).any():
            raise FieldError("Shared-node/self contact is not evaluated by this geometry estimate")
    if (lookup[np.concatenate([faces.ravel(), slave_ids])] < 0).any():
        raise FieldError("Contact surfaces use undefined nodes")
    corners = xyz[lookup[faces]]  # [m, 4, 3]
    tri = np.concatenate([corners[:, [0, 1, 2]], corners[:, [0, 2, 3]]])
    tri_nodes = np.concatenate([faces[:, [0, 1, 2]], faces[:, [0, 2, 3]]])
    tri_face = np.concatenate([np.arange(len(faces)), np.arange(len(faces))])
    real = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1) > 0
    if budget is not None:
        if not np.all(np.bincount(tri_face[real], minlength=len(faces))):
            raise FieldError("Degenerate master faces are not evaluated")
        budget.claim("max_master_triangles", int(real.sum()))
    tri, tri_nodes, tri_face = tri[real], tri_nodes[real], tri_face[real]
    face_normal, edge_normal, vertex_normal = _pseudonormals(tri, tri_nodes)
    if budget is not None and not all(np.isfinite(value).all() for value in (face_normal, edge_normal, vertex_normal)):
        raise FieldError("Non-finite contact pseudonormals")
    reach = float(0.5 * (slave_thickness.max() + master_thickness.max()) + tolerance)
    extent = np.ptp(tri, axis=1).max(axis=1)
    search = reach + float(max(np.percentile(extent, 95), 1e-12))  # nodes up to one face size away
    size = float(np.percentile(extent, 95)) + 2 * search
    owner, face_keys = _cells(tri.min(axis=1) - search, tri.max(axis=1) + search, size, budget)
    points = xyz[lookup[slave_ids]]
    if budget is not None:
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            grid = np.floor(points / size)
        if not np.isfinite(grid).all() or (np.abs(grid) >= 2**60).any():
            raise GeometryBudgetError("slave coordinate grid range is not admitted")
    node_keys = np.floor(points / size).astype(np.int64)
    _, dense = np.unique(np.concatenate([face_keys, node_keys]), axis=0, return_inverse=True)
    dense = dense.ravel()
    face_cell, node_cell = dense[:len(face_keys)], dense[len(face_keys):]
    order = np.argsort(face_cell, kind="stable")
    low = np.searchsorted(face_cell[order], node_cell, "left")
    count = np.searchsorted(face_cell[order], node_cell, "right") - low
    if budget is not None:
        budget.claim("max_pairs", sum(int(value) for value in count))
    node_index = np.repeat(np.arange(len(slave_ids)), count)
    rank = np.arange(int(count.sum())) - np.repeat(np.cumsum(count) - count, count)
    tri_index = owner[order[low[node_index] + rank]]
    own = (faces[tri_face[tri_index]] == slave_ids[node_index][:, None]).any(axis=1)
    node_index, tri_index = node_index[~own], tri_index[~own]
    p = points[node_index]
    q, feature = _closest_points(p, tri[tri_index, 0], tri[tri_index, 1], tri[tri_index, 2])
    gap = np.linalg.norm(p - q, axis=1)
    nearest = np.lexsort((gap, node_index))  # per node: true closest point on the surface first
    first = np.ones(len(nearest), dtype=bool)
    first[1:] = node_index[nearest][1:] != node_index[nearest][:-1]
    pick = nearest[first]
    node_index, tri_index, feature, gap = node_index[pick], tri_index[pick], feature[pick], gap[pick]
    # Inside/outside from the angle-weighted pseudonormal of the closest feature (face, edge or vertex).
    normal = face_normal[tri_index].copy()
    on_edge, on_vertex = (feature >= 1) & (feature <= 3), feature >= 4
    normal[on_edge] = edge_normal[tri_index[on_edge], feature[on_edge] - 1]
    normal[on_vertex] = vertex_normal[tri_index[on_vertex], feature[on_vertex] - 4]
    side = np.einsum("ij,ij->i", p[pick] - q[pick], normal)
    signed = np.where(side < 0, -gap, gap)
    face = tri_face[tri_index]
    offset = 0.5 * (slave_thickness[node_index] + master_thickness[face])
    distance = np.where(two_sided[face], gap, signed)
    depth = offset - distance
    if budget is not None and not (np.isfinite(gap).all() and np.isfinite(side).all() and np.isfinite(depth).all()):
        raise FieldError("Non-finite nearest-feature geometry was not evaluated")
    hit = depth > tolerance
    found = sorted(zip(depth[hit].tolist(), slave_ids[node_index[hit]].tolist(), face[hit].tolist()), reverse=True)
    result = {**report, "penetrating": len(found), "max_depth": found[0][0] if found else 0.0,
              "nodes": [{"node": n, "depth": d, "master_face": faces[f].tolist()} for d, n, f in found[:max_report]]}
    if budget is not None:
        result["coverage"] = dict(slave_nodes=len(slave_ids), nearest_feature_evaluated=len(pick),
                                  unsearched_slave_nodes=len(slave_ids) - len(pick))
    return result


SURFACE_CODES = {0: "segment_set", 2: "part_set", 3: "parts", 4: "node_set", 6: "part_set"}


def _spec(code: int, ident: int, side: str) -> dict | None:
    kind = SURFACE_CODES.get(code)
    if kind is None or (kind == "node_set" and side == "b") or ident <= 0:
        return None
    return {kind: [ident] if kind == "parts" else ident}


def contact_checks(deck: KeywordDeck, tolerance: float = 0.0, max_report: int = 50, *, budget=None) -> list[dict]:
    """Penetration check of every *CONTACT block: SURFA (slave) into SURFB (master).

    Surface types 0 (segment set), 2/6 (part set), 3 (part) and 4 (node set, SURFA only) are
    checked; other types are listed as not checked with the reason.
    """
    results = []
    blocks = deck.blocks("*CONTACT_*")
    for index, block in enumerate(blocks):
        entry = {"keyword": block.name, "file": str(block.file.path), "line": block.line_number}
        if budget is not None:
            if index >= budget.limits["max_contacts"]:
                results.append({"checked": False, "reason": "max_contacts budget not admitted",
                                "omitted_contacts": len(blocks) - index})
                break
            if block.name not in SUPPORTED_CONTACTS or "SINGLE_SURFACE" in block.name:
                results.append({**entry, "checked": False, "reason": "unsupported or self/single-surface contact"})
                continue
        try:
            present = {info.name for info in deck.layout(block).fields}
            names = ("surfa", "surfb", "surfatyp", "surfbtyp") if "surfa" in present else ("ssid", "msid", "sstyp", "mstyp")
            if budget is None:
                a, b, a_type, b_type = (int(deck.get(block, name).value or 0) for name in names)
            else:
                from ._identity import exact_integer

                a, b, a_type, b_type = (exact_integer(deck.get(block, name).value or 0, name) for name in names)
        except (FieldError, KeyError, Unsupported) as error:
            results.append({**entry, "checked": False, "reason": f"fields not readable: {error}"})
            continue
        slave, master = _spec(a_type, a, "a"), _spec(b_type, b, "b")
        if slave is not None and b == 0 and b_type in (0, 2, 3):
            results.append({**entry, "checked": False, "reason": "single-surface contact: self-penetration "
                            "is not checked at keyword level"})
            continue
        if slave is None or master is None:
            results.append({**entry, "checked": False, "reason": f"surface types {a_type}/{b_type} are not "
                            "supported by the keyword-level check"})
            continue
        try:
            limit = max_report if budget is None else max(0, max_report - budget.reported)
            context = np.errstate(over="raise", invalid="raise", divide="raise") if budget else nullcontext()
            with context:
                found = check_penetration(deck, slave, master, tolerance, limit, budget=budget)
        except (FieldError, KeyError, Unsupported, FloatingPointError, OverflowError) as error:
            results.append({**entry, "checked": False, "reason": str(error)})
            continue
        if budget is not None:
            budget.reported += len(found["nodes"])
            if found["coverage"]["unsearched_slave_nodes"]:
                results.append({**entry, "checked": False, "reason": "near-field search coverage is incomplete",
                                "coverage": found["coverage"], "partial_candidates": found["nodes"],
                                "partial_penetrating": found["penetrating"]})
                continue
        results.append({**entry, "checked": True, "slave": slave, "master": master, **found})
    return results


__all__ = ["ASSUMPTIONS", "check_penetration", "contact_checks"]
