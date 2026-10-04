"""Geometry and formulation checks for Segment-based loading."""

from collections import defaultdict

import numpy as np

from .entity_cards import fields
from .mesh_quality import element_metrics
from .segment_geometry import build_segments, canonical_cycle, element_rows, node_coordinates, topology_faces


def segment_normals(path, records):
    dimensions = {len(r["node_ids"]) == 2 for r in records}
    if not records or len(records) > 20000 or len(dimensions) != 1:
        raise ValueError("Use1..20000 uniformly2D edges or3D faces")
    coords = node_coordinates(path, {n for r in records for n in r["node_ids"]})
    audit = []
    for record in records:
        x = np.asarray([coords[n] for n in record["node_ids"]])
        if len(x) == 2:
            scale = float(np.linalg.norm(x[1]-x[0]))
            if scale <= 0 or np.max(np.abs(x[:, 2])) > max(scale, 1.0)*1e-8:
                raise ValueError("2D pressure segments require nondegenerate XY edges")
            delta = x[1]-x[0]
            normal, measure = np.array([delta[1], -delta[0], 0.0])/scale, scale
        else:
            quality = element_metrics("shell", x)
            if quality["area"] <= 0 or quality["warpage_degrees"] >= 90 or quality["min_edge"] <= 0:
                raise ValueError("Cannot load a folded/degenerate segment")
            vector = np.cross(x[1]-x[0], x[2]-x[0])
            if len(x) == 4:
                vector += np.cross(x[2]-x[0], x[3]-x[0])
            normal, measure = vector/np.linalg.norm(vector), quality["area"]
        audit.append(dict(node_ids=record["node_ids"], normal=normal.tolist(),
                          positive_pressure_direction=(-normal).tolist(), measure=measure))
    return 2 if True in dimensions else 3, audit


def part_shell_formulations(path):
    parts, sections = {}, {}
    keyword, waiting_title, consumed = None, False, False
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            if line.lstrip().startswith("$"):
                continue
            if line.startswith("*"):
                keyword = line.strip().upper()
                waiting_title = keyword in ("*PART", "*SECTION_SHELL_TITLE")
                consumed = False
                continue
            if waiting_title:
                waiting_title = False
                continue
            if not line.strip() or consumed:
                continue
            if keyword in ("*PART", "*SECTION_SHELL", "*SECTION_SHELL_TITLE"):
                row = fields(line)
                uid, ref = int(row[0]), int(row[1] or 2)
                target = parts if keyword == "*PART" else sections
                if uid in target:
                    raise ValueError("Duplicate native part/section identity")
                target[uid] = ref
                consumed = True
    return {pid: sections.get(sid) for pid, sid in parts.items()}


def validate_boundary(path, records, dimension, allowed_2d_forms=(13, 14, 15), require_ccw=True):
    kind, mode = ("solid", "solid_exterior") if dimension == 3 else ("shell", "shell_boundary_2d")
    wanted = {tuple(sorted(r["node_ids"])) for r in records}
    owners = defaultdict(list)
    for uid, pid, conn in element_rows(path, kind):
        for face in topology_faces(conn, mode):
            key = tuple(sorted(face))
            if key in wanted:
                owners[key].append((uid, pid))
    if owners.keys() != wanted or any(len(rows) != 1 for rows in owners.values()):
        raise ValueError("Every boundary segment must be a unique exterior face/edge of the matching model domain")
    if dimension == 2:
        forms = part_shell_formulations(path)
        if any(forms.get(rows[0][1]) not in allowed_2d_forms for rows in owners.values()):
            raise ValueError("2D boundary requires explicitly supported continuum SECTION_SHELL formulations")
    expected, _ = build_segments(path, mode, sorted({row[0][0] for row in owners.values()}), face_keys=wanted)
    reference = {tuple(sorted(r["node_ids"])): tuple(r["node_ids"]) for r in expected}
    reversed_count = 0
    for record in records:
        nodes = tuple(record["node_ids"])
        outward = reference[tuple(sorted(nodes))]
        if canonical_cycle(nodes) == outward:
            continue
        if (dimension == 3 or not require_ccw) and canonical_cycle(tuple(reversed(nodes))) == outward:
            reversed_count += 1  # 3D manual permits either winding
        else:
            raise ValueError("Boundary ordering is invalid;2D nonreflecting edges must be counterclockwise")
    return dict(unique_exterior_segments=len(records), dimension=dimension,
                reversed_segments=reversed_count, two_dimensional_order_verified=dimension == 2 and require_ccw,
                topology_scope="Conforming linear Hex8/Tet4 or XY Tri3/Quad4, not geometric contact/intersection checks")
