"""Bounded surface construction from a fresh LS-PrePost native keyword export."""

from collections import Counter

import numpy as np

from .mesh_quality import element_metrics

HEX_FACES = ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
TET_FACES = ((0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0))


def canonical_cycle(nodes):
    nodes = tuple(nodes)
    if len(nodes) == 2:
        return nodes
    return min(nodes[i:] + nodes[:i] for i in range(len(nodes)))


def element_rows(path, kind):
    key = "*ELEMENT_" + kind.upper()
    current = None
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            if not line.strip() or line.lstrip().startswith("$"):
                continue
            if line.startswith("*"):
                current = line.strip().upper()
                if current.startswith(key) and current != key:
                    raise ValueError("Unsupported native element keyword variant: " + current)
                continue
            if current != key:
                continue
            fields = line.strip().split(",") if "," in line else [line[i:i+8].strip() for i in range(0, len(line.rstrip()), 8)]
            values = [int(v) if v else 0 for v in fields]
            count = 8 if kind == "solid" else 4
            if len(values) < count+2 or any(values[count+2:]):
                raise ValueError("Only native short-format linear element rows are supported")
            uid, pid, *conn = values[:count+2]
            if kind == "solid" and len(set(conn[:4])) == 4 and all(v in (0, conn[3]) for v in conn[4:]):
                conn = conn[:4]
            if kind == "shell" and conn[3] in (0, conn[2]):
                conn = conn[:3]
            if min(uid, pid, *conn) <= 0 or len(conn) != len(set(conn)):
                raise ValueError("Unsupported collapsed/nonlinear topology in surface domain")
            yield uid, pid, conn


def node_coordinates(path, wanted):
    result, current = {}, None
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            if not line.strip() or line.lstrip().startswith("$"):
                continue
            if line.startswith("*"):
                current = line.strip().upper()
                continue
            if current != "*NODE":
                continue
            fields = line.strip().split(",") if "," in line else [line[:8], line[8:24], line[24:40], line[40:56]]
            uid = int(fields[0])
            if uid in wanted:
                if uid in result:
                    raise ValueError("Duplicate requested native node ID")
                result[uid] = np.asarray([float(v.replace("D", "E").replace("d", "e")) for v in fields[1:4]])
                if result[uid].shape != (3,) or not np.isfinite(result[uid]).all():
                    raise ValueError("Invalid native coordinate data")
    if result.keys() != wanted:
        raise ValueError("Surface connectivity refers to missing native nodes")
    return result


def topology_faces(conn, mode):
    if mode == "solid_exterior":
        return [[conn[i] for i in face] for face in (TET_FACES if len(conn) == 4 else HEX_FACES)]
    if mode == "shell_faces":
        return [list(conn)]
    return [[conn[i], conn[(i+1) % len(conn)]] for i in range(len(conn))]


def build_segments(path, mode, element_ids, normal_direction=None, cosine_min=0.99,
                   reverse=False, max_warpage=15.0, face_keys=None):
    """Remove shared topological faces/edges against the entire matching domain.

    Conforming linear Hex8/Tet4 or Tri3/Quad4 only; this is not geometric
    intersection detection for coincident disconnected or nonconforming meshes.
    """
    kind = "solid" if mode == "solid_exterior" else "shell"
    wanted = set(element_ids)
    cells = {}
    for uid, pid, conn in element_rows(path, kind):
        if uid in wanted:
            if uid in cells:
                raise ValueError("Duplicate selected element ID")
            cells[uid] = (pid, conn)
    if cells.keys() != wanted:
        raise ValueError("Missing selected elements in native export")
    coords = node_coordinates(path, {n for _, conn in cells.values() for n in conn})
    candidates = {}
    for eid, (pid, conn) in cells.items():
        metric = element_metrics(kind, [coords[n] for n in conn])
        if (metric["min_edge"] <= 0 or metric.get("signed_volume", 1) <= 0
                or metric.get("minimum_jacobian", 1) <= 0 or metric.get("area", 1) <= 0
                or metric.get("warpage_degrees", 0) > max_warpage):
            raise ValueError("Cannot build boundary from a degenerate/inverted cell")
        for face in topology_faces(conn, mode):
            key = tuple(sorted(face))
            if face_keys is None or key in face_keys:
                candidates.setdefault(key, (eid, pid, conn, face))
    owners = Counter()
    for _, _, conn in element_rows(path, kind):
        for face in topology_faces(conn, mode):
            key = tuple(sorted(face))
            if key in candidates:
                owners[key] += 1
    if any(count > 2 for count in owners.values()) or (mode == "shell_faces" and any(v != 1 for v in owners.values())):
        raise ValueError("Duplicate/nonmanifold faces in selected surface domain")
    direction = None
    if normal_direction is not None:
        direction = np.asarray(normal_direction, dtype=float)
        direction = direction / np.linalg.norm(direction)
    audit, records = [], []
    for key, (eid, pid, conn, face) in sorted(candidates.items()):
        if mode != "shell_faces" and owners[key] != 1:
            continue
        x = np.asarray([coords[n] for n in face])
        cell = np.asarray([coords[n] for n in conn])
        scale = float(np.max(np.ptp(cell, axis=0)))
        if len(face) == 2:
            if np.max(np.abs(cell[:, 2])) > max(scale, 1.0) * 1e-8:
                raise ValueError("2D boundary requires a model in the XY plane")
            delta = x[1] - x[0]
            measure = float(np.linalg.norm(delta))
            normal = np.array([delta[1], -delta[0], 0.0]) / measure
        else:
            metric = element_metrics("shell", x)
            if metric["area"] <= 0 or metric["warpage_degrees"] > max_warpage:
                raise ValueError("Degenerate/folded or excessively warped segment")
            measure = metric["area"]
            normal = np.cross(x[1]-x[0], x[2]-x[0])
            if len(face) == 4:
                normal += np.cross(x[2]-x[0], x[3]-x[0])
            normal /= np.linalg.norm(normal)
        if mode != "shell_faces":
            sign = float(np.dot(normal, x.mean(axis=0)-cell.mean(axis=0)))
            if abs(sign) <= scale * 1e-12:
                raise ValueError("Ambiguous outward boundary orientation")
            if sign < 0:
                face, normal = list(reversed(face)), -normal
            others = np.asarray([coords[n] for n in conn if n not in face])
            if np.any((others - x.mean(axis=0)) @ normal > scale * 1e-8):
                raise ValueError("Nonconvex boundary cell needs native mesh repair before surface creation")
        if direction is not None and float(np.dot(normal, direction)) < cosine_min:
            continue
        if reverse:
            face, normal = list(reversed(face)), -normal
        nodes = list(canonical_cycle(face))
        records.append(dict(node_ids=nodes, attributes=[0.0]*4))
        audit.append(dict(owner_element_id=eid, part_id=pid, node_ids=nodes,
                          normal=normal.tolist(), measure=measure))
    if not records or len(records) > 20000:
        raise ValueError("Surface must contain1..20000 selected segments; narrow the element/normal scope")
    order = sorted(range(len(records)), key=lambda i: records[i]["node_ids"])
    return [records[i] for i in order], [audit[i] for i in order]
