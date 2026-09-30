"""Explicit geometric quality metrics for linear triangles/quads/tets/hexes."""

import itertools
import math

import numpy as np

HEX_SIGNS = np.array(
    [[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1], [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]],
    dtype=float,
)
HEX_EDGES = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]


def element_metrics(kind, coordinates):
    x = np.asarray(coordinates, dtype=float)
    if not np.isfinite(x).all():
        raise ValueError("Nonfinite mesh coordinates")
    result = {}
    if kind == "shell" and len(x) in (3, 4):
        edges = [float(np.linalg.norm(x[(i + 1) % len(x)] - x[i])) for i in range(len(x))]
        normal = np.cross(x[1] - x[0], x[2] - x[0])
        area = np.linalg.norm(normal) / 2
        warp = 0.0
        if len(x) == 4:
            other = np.cross(x[2] - x[0], x[3] - x[0])
            area += np.linalg.norm(other) / 2
            denominator = np.linalg.norm(normal) * np.linalg.norm(other)
            warp = (
                math.degrees(math.acos(float(np.clip(np.dot(normal, other) / denominator, -1, 1))))
                if denominator
                else 180.0
            )
        angles = []
        for i in range(len(x)):
            a, b = x[(i - 1) % len(x)] - x[i], x[(i + 1) % len(x)] - x[i]
            denominator = np.linalg.norm(a) * np.linalg.norm(b)
            angles.append(
                math.degrees(math.acos(float(np.clip(np.dot(a, b) / denominator, -1, 1))))
                if denominator
                else 0.0
            )
        result.update(area=float(area), warpage_degrees=warp, min_angle=min(angles), max_angle=max(angles))
    elif kind == "solid" and len(x) == 4:
        edges = [float(np.linalg.norm(x[a] - x[b])) for a, b in itertools.combinations(range(4), 2)]
        volume = float(np.linalg.det(np.column_stack([x[1] - x[0], x[2] - x[0], x[3] - x[0]])) / 6)
        result.update(signed_volume=volume)
    elif kind == "solid" and len(x) == 8:
        edges = [float(np.linalg.norm(x[a] - x[b])) for a, b in HEX_EDGES]
        determinants = []
        scaled = []
        for q in itertools.product((-1 / math.sqrt(3), 1 / math.sqrt(3)), repeat=3):
            q = np.asarray(q)
            derivative = np.empty((8, 3))
            for axis in range(3):
                others = [i for i in range(3) if i != axis]
                derivative[:, axis] = (
                    HEX_SIGNS[:, axis] * np.prod(1 + HEX_SIGNS[:, others] * q[others], axis=1) / 8
                )
            jacobian = x.T @ derivative
            det = float(np.linalg.det(jacobian))
            determinants.append(det)
            denominator = float(np.prod(np.linalg.norm(jacobian, axis=0)))
            scaled.append(det / denominator if denominator else 0.0)
        result.update(
            signed_volume=sum(determinants), minimum_jacobian=min(determinants), scaled_jacobian=min(scaled)
        )
    elif kind == "beam" and len(x) == 2:
        edges = [float(np.linalg.norm(x[1] - x[0]))]
        result["length"] = edges[0]
    else:
        return {
            "supported": False,
            "reason": "Only linear tri/quad shell, tet/hex solid and two-node beam geometry is evaluated",
        }
    result.update(
        supported=True,
        min_edge=min(edges),
        max_edge=max(edges),
        edge_aspect_ratio=max(edges) / min(edges) if min(edges) > 0 else None,
    )
    return result


def quality(nodes, elements, max_aspect=10.0, max_warpage=15.0, min_scaled_jacobian=0.2):
    lookup = {int(row[0]): np.asarray(row[1:4], dtype=float) for row in nodes}
    if len(lookup) != len(nodes):
        raise ValueError("Duplicate user node IDs")
    if not all(np.isfinite(x).all() for x in lookup.values()):
        raise ValueError("Nonfinite mesh coordinates")
    used = set()
    rows = []
    unsupported = []
    for element in elements:
        raw = element["nodes"]
        ids = list(raw)
        if element["type"] == "shell" and len(raw) == 4 and raw[3] in (0, raw[2]):
            ids = raw[:3]
        if (
            element["type"] == "solid"
            and len(raw) == 8
            and len(set(raw[:4])) == 4
            and all(n in (0, raw[3]) for n in raw[4:])
        ):
            ids = raw[:4]
        if not all(ids) or len(set(ids)) != len(ids):
            unsupported.append(
                dict(
                    type=element["type"],
                    element_id=element["id"],
                    reason="Unsupported repeated-node topology",
                )
            )
            used.update(n for n in raw if n in lookup)
            continue
        missing = set(ids) - lookup.keys()
        if missing:
            rows.append(
                dict(
                    type=element["type"],
                    element_id=element["id"],
                    issues=["missing_node_reference"],
                    missing_nodes=sorted(missing),
                )
            )
            continue
        used.update(ids)
        metric = element_metrics(element["type"], [lookup[uid] for uid in ids])
        if not metric["supported"]:
            unsupported.append(dict(type=element["type"], element_id=element["id"], reason=metric["reason"]))
            continue
        issues = []
        if metric["min_edge"] == 0 or metric.get("area", 1) <= 0:
            issues.append("degenerate")
        if metric["edge_aspect_ratio"] is None or metric["edge_aspect_ratio"] > max_aspect:
            issues.append("edge_aspect_ratio")
        if metric.get("warpage_degrees", 0) > max_warpage:
            issues.append("warpage")
        if metric.get("signed_volume", 1) <= 0:
            issues.append("nonpositive_volume")
        if metric.get("minimum_jacobian", 1) <= 0:
            issues.append("nonpositive_jacobian")
        if metric.get("scaled_jacobian", 1) < min_scaled_jacobian:
            issues.append("scaled_jacobian")
        rows.append(dict(type=element["type"], element_id=element["id"], metrics=metric, issues=issues))
    return dict(
        node_count=len(nodes),
        element_count=len(elements),
        checked_count=len(rows),
        failed_count=sum(bool(r["issues"]) for r in rows),
        unsupported_count=len(unsupported),
        valid_within_scope=bool(rows) and not unsupported and all(not r["issues"] for r in rows),
        orphan_nodes=sorted(lookup.keys() - used),
        elements=rows,
        unsupported=unsupported,
        definitions={
            "edge_aspect_ratio": "max physical edge / min physical edge",
            "warpage": "angle between triangles (1,2,3) and (1,3,4)",
            "hex_jacobian": "2x2x2 Gauss points; scaled by column norm product",
            "scope": "Geometry only; not contact, material, hourglass, timestep or solver validity",
        },
    )


def from_deck(deck):
    from .deck_backend import api
    from .model_deck import table

    _, kw = api()
    for card in deck.keywords:
        if isinstance(card, str):
            raise ValueError("Raw keyword blocks prevent complete mesh quality assessment")
        if card.keyword in ("NODE", "ELEMENT") and type(card) not in (
            kw.Node,
            kw.ElementShell,
            kw.ElementSolid,
            kw.ElementBeam,
        ):
            raise ValueError("Unsupported structural keyword: " + type(card).__name__)
    nodes = table(deck, kw.Node, "nodes")
    if nodes.empty:
        raise ValueError("No standard nodes")
    elements = []
    for cls, kind, count in [
        (kw.ElementShell, "shell", 4),
        (kw.ElementSolid, "solid", 8),
        (kw.ElementBeam, "beam", 2),
    ]:
        frame = table(deck, cls, "elements")
        for _, row in frame.iterrows():
            elements.append(
                dict(
                    type=kind,
                    id=int(row["eid"]),
                    part_id=int(row["pid"]),
                    nodes=[int(row["n" + str(i)]) for i in range(1, count + 1)],
                )
            )
    return [[int(r.nid), float(r.x), float(r.y), float(r.z)] for r in nodes.itertuples()], elements
