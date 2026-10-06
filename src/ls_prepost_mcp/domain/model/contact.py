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

from typing import TYPE_CHECKING

import numpy as np

from .fields import FieldError
from .geometry import _index, elements, exterior_segments, nodes
from .layouts import Unsupported

if TYPE_CHECKING:
    from .deck import KeywordDeck

ASSUMPTIONS = ["shell contact thickness = section T1 (element thickness cards and SST/MST/SFST not applied)",
               "segment sets are one-sided with their written orientation and zero thickness",
               "penetrations deeper than about one master face size are not searched"]


def _set_members(deck: KeywordDeck, prefix: str, sid: int) -> list[int]:
    for block in deck.blocks(prefix + "*"):
        try:
            if deck.get(block, "sid").value == sid:
                return deck.members(block)
        except (FieldError, KeyError):
            continue
    raise FieldError(f"{prefix} {sid} not found")


def _shell_thickness(deck: KeywordDeck, part: int) -> float:
    hits = deck.find("*PART", pid=part)
    if not hits:
        raise FieldError(f"Part {part} not found")
    block, row = hits[0]
    secid = deck.get(block, "secid", row=row).value
    for section, _ in deck.find("*SECTION_SHELL", secid=secid):
        return float(deck.get(section, "t1").value or 0.0)
    raise FieldError(f"*SECTION_SHELL {secid} of part {part} not found")


def _surface(deck: KeywordDeck, spec: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(faces[m, 4], thickness[m], two_sided[m])``; triangles as ``a b c c``."""
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


def _slave(deck: KeywordDeck, spec: dict) -> tuple[np.ndarray, np.ndarray]:
    """Slave node IDs and their contact thickness."""
    if "node_set" in spec:
        ids = np.unique(np.asarray(_set_members(deck, "*SET_NODE", int(spec["node_set"])), dtype=np.int64))
        return ids, np.zeros(len(ids))
    faces, thickness, _ = _surface(deck, spec)
    ids = np.unique(faces)
    per_node = np.zeros(len(ids))
    np.maximum.at(per_node, np.searchsorted(ids, faces.ravel()), np.repeat(thickness, 4))
    return ids, per_node


def _cells(points_min: np.ndarray, points_max: np.ndarray, size: float) -> tuple[np.ndarray, np.ndarray]:
    """``(owner, cell keys)`` for every grid cell overlapped by each box."""
    low = np.floor(points_min / size).astype(np.int64)
    high = np.floor(points_max / size).astype(np.int64)
    span = high - low + 1
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
                      max_report: int = 200) -> dict:
    """Initial penetrations of ``slave`` nodes into the ``master`` surface (read-only)."""
    node_ids, xyz = nodes(deck)
    lookup = _index(node_ids)
    faces, master_thickness, two_sided = _surface(deck, master)
    slave_ids, slave_thickness = _slave(deck, slave)
    report = {"slave_nodes": int(len(slave_ids)), "master_faces": int(len(faces)), "assumptions": ASSUMPTIONS}
    if not len(faces) or not len(slave_ids):
        return {**report, "penetrating": 0, "max_depth": 0.0, "nodes": []}
    if (lookup[np.concatenate([faces.ravel(), slave_ids])] < 0).any():
        raise FieldError("Contact surfaces use undefined nodes")
    corners = xyz[lookup[faces]]  # [m, 4, 3]
    tri = np.concatenate([corners[:, [0, 1, 2]], corners[:, [0, 2, 3]]])
    tri_nodes = np.concatenate([faces[:, [0, 1, 2]], faces[:, [0, 2, 3]]])
    tri_face = np.concatenate([np.arange(len(faces)), np.arange(len(faces))])
    real = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1) > 0
    tri, tri_nodes, tri_face = tri[real], tri_nodes[real], tri_face[real]
    face_normal, edge_normal, vertex_normal = _pseudonormals(tri, tri_nodes)
    reach = float(0.5 * (slave_thickness.max() + master_thickness.max()) + tolerance)
    extent = np.ptp(tri, axis=1).max(axis=1)
    search = reach + float(max(np.percentile(extent, 95), 1e-12))  # nodes up to one face size away
    size = float(np.percentile(extent, 95)) + 2 * search
    owner, face_keys = _cells(tri.min(axis=1) - search, tri.max(axis=1) + search, size)
    points = xyz[lookup[slave_ids]]
    node_keys = np.floor(points / size).astype(np.int64)
    _, dense = np.unique(np.concatenate([face_keys, node_keys]), axis=0, return_inverse=True)
    dense = dense.ravel()
    face_cell, node_cell = dense[:len(face_keys)], dense[len(face_keys):]
    order = np.argsort(face_cell, kind="stable")
    low = np.searchsorted(face_cell[order], node_cell, "left")
    count = np.searchsorted(face_cell[order], node_cell, "right") - low
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
    hit = depth > tolerance
    found = sorted(zip(depth[hit].tolist(), slave_ids[node_index[hit]].tolist(), face[hit].tolist()), reverse=True)
    return {**report, "penetrating": len(found), "max_depth": found[0][0] if found else 0.0,
            "nodes": [{"node": n, "depth": d, "master_face": faces[f].tolist()} for d, n, f in found[:max_report]]}


SURFACE_CODES = {0: "segment_set", 2: "part_set", 3: "parts", 4: "node_set", 6: "part_set"}


def _spec(code: int, ident: int, side: str) -> dict | None:
    kind = SURFACE_CODES.get(code)
    if kind is None or (kind == "node_set" and side == "b") or ident <= 0:
        return None
    return {kind: [ident] if kind == "parts" else ident}


def contact_checks(deck: KeywordDeck, tolerance: float = 0.0, max_report: int = 50) -> list[dict]:
    """Penetration check of every *CONTACT block: SURFA (slave) into SURFB (master).

    Surface types 0 (segment set), 2/6 (part set), 3 (part) and 4 (node set, SURFA only) are
    checked; other types are listed as not checked with the reason.
    """
    results = []
    for block in deck.blocks("*CONTACT_*"):
        entry = {"keyword": block.name, "file": str(block.file.path), "line": block.line_number}
        try:
            present = {info.name for info in deck.layout(block).fields}
            names = ("surfa", "surfb", "surfatyp", "surfbtyp") if "surfa" in present else ("ssid", "msid", "sstyp", "mstyp")
            a, b, a_type, b_type = (int(deck.get(block, name).value or 0) for name in names)
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
            found = check_penetration(deck, slave, master, tolerance, max_report)
        except (FieldError, KeyError, Unsupported) as error:
            results.append({**entry, "checked": False, "reason": str(error)})
            continue
        results.append({**entry, "checked": True, "slave": slave, "master": master, **found})
    return results


__all__ = ["ASSUMPTIONS", "check_penetration", "contact_checks"]
