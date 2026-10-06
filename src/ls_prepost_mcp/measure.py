"""Q11 geometric and physical measurements (LSPP F4 Measure tool).

Supported measurement types:
- distance: 2-node 3D Euclidean distance and components (dx, dy, dz);
- angle: 3-node vertex angle in degrees and radians;
- dihedral: 4-node plane-to-plane dihedral angle in degrees and radians;
- point_to_plane_distance: distance from a target node to plane defined by 3 nodes;
- area: total surface area of shells or solid faces;
- volume: total volume of solids or shells (area * thickness);
- mass: volume * density (explicit positive density and units required; rejected if missing);
- center_of_mass: 3D center of gravity coordinates;
- inertia: moments of inertia tensor (Ixx, Iyy, Izz, Ixy, Iyz, Izx) and principal moments;
- clearance: minimum spatial clearance distance between two parts/sets and closest node pair.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


class MeasurementError(ValueError):
    """Raised when measurement parameters or geometries are invalid or missing required data."""


def measure_distance(
    coord1: tuple[float, float, float] | np.ndarray,
    coord2: tuple[float, float, float] | np.ndarray,
    node_ids: list[int] | None = None,
    units: str = "mm",
) -> dict[str, Any]:
    """Measure 3D distance between two points."""
    p1 = np.asarray(coord1, dtype=float)
    p2 = np.asarray(coord2, dtype=float)
    if p1.shape != (3,) or p2.shape != (3,):
        raise MeasurementError("Distance requires two 3D coordinates")

    delta = p2 - p1
    dist = float(np.linalg.norm(delta))

    return {
        "measurement": "distance",
        "distance": dist,
        "dx": float(delta[0]),
        "dy": float(delta[1]),
        "dz": float(delta[2]),
        "node_ids": node_ids or [],
        "units": units,
    }


def measure_angle(
    coord1: tuple[float, float, float] | np.ndarray,
    coord_vertex: tuple[float, float, float] | np.ndarray,
    coord3: tuple[float, float, float] | np.ndarray,
    node_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Measure angle at vertex formed by ray (vertex -> 1) and ray (vertex -> 3)."""
    p1 = np.asarray(coord1, dtype=float)
    pv = np.asarray(coord_vertex, dtype=float)
    p3 = np.asarray(coord3, dtype=float)

    v1 = p1 - pv
    v2 = p3 - pv

    norm1 = float(np.linalg.norm(v1))
    norm2 = float(np.linalg.norm(v2))

    if norm1 == 0 or norm2 == 0:
        raise MeasurementError("Angle rays must have non-zero length")

    cos_val = np.dot(v1, v2) / (norm1 * norm2)
    cos_clamped = max(-1.0, min(1.0, float(cos_val)))
    angle_rad = math.acos(cos_clamped)
    angle_deg = math.degrees(angle_rad)

    return {
        "measurement": "angle",
        "angle_degrees": angle_deg,
        "angle_radians": angle_rad,
        "node_ids": node_ids or [],
        "units": "degrees",
    }


def measure_dihedral(
    coord1: tuple[float, float, float] | np.ndarray,
    coord2: tuple[float, float, float] | np.ndarray,
    coord3: tuple[float, float, float] | np.ndarray,
    coord4: tuple[float, float, float] | np.ndarray,
    node_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Measure dihedral angle between plane (1, 2, 3) and plane (2, 3, 4)."""
    p1 = np.asarray(coord1, dtype=float)
    p2 = np.asarray(coord2, dtype=float)
    p3 = np.asarray(coord3, dtype=float)
    p4 = np.asarray(coord4, dtype=float)

    n1 = np.cross(p2 - p1, p3 - p2)
    n2 = np.cross(p3 - p2, p4 - p3)

    len1 = float(np.linalg.norm(n1))
    len2 = float(np.linalg.norm(n2))

    if len1 == 0 or len2 == 0:
        raise MeasurementError("Collinear points cannot define planes for dihedral measurement")

    cos_val = np.dot(n1, n2) / (len1 * len2)
    cos_clamped = max(-1.0, min(1.0, float(cos_val)))
    angle_rad = math.acos(cos_clamped)
    angle_deg = math.degrees(angle_rad)

    return {
        "measurement": "dihedral",
        "angle_degrees": angle_deg,
        "angle_radians": angle_rad,
        "node_ids": node_ids or [],
        "units": "degrees",
    }


def measure_point_to_plane_distance(
    target_coord: tuple[float, float, float] | np.ndarray,
    plane_p1: tuple[float, float, float] | np.ndarray,
    plane_p2: tuple[float, float, float] | np.ndarray,
    plane_p3: tuple[float, float, float] | np.ndarray,
    units: str = "mm",
) -> dict[str, Any]:
    """Measure perpendicular distance from a target point to the plane through 3 points."""
    pt = np.asarray(target_coord, dtype=float)
    a = np.asarray(plane_p1, dtype=float)
    b = np.asarray(plane_p2, dtype=float)
    c = np.asarray(plane_p3, dtype=float)

    normal = np.cross(b - a, c - a)
    n_len = float(np.linalg.norm(normal))
    if n_len == 0:
        raise MeasurementError("Collinear points cannot define a plane")
    n_unit = normal / n_len

    dist = float(abs(np.dot(pt - a, n_unit)))
    projected = pt - np.dot(pt - a, n_unit) * n_unit

    return {
        "measurement": "point_to_plane_distance",
        "distance": dist,
        "projected_point": [float(x) for x in projected],
        "units": units,
    }


def calculate_element_areas(
    nodes: dict[int, np.ndarray],
    elements: list[list[int]],
) -> tuple[float, list[float]]:
    """Calculate area of triangular or quadrilateral surface elements."""
    areas = []
    for elem in elements:
        pts = [nodes[nid] for nid in elem]
        if len(pts) == 3:
            # Triangle
            v1 = pts[1] - pts[0]
            v2 = pts[2] - pts[0]
            a = 0.5 * float(np.linalg.norm(np.cross(v1, v2)))
        elif len(pts) == 4:
            # Quad split into 2 triangles
            v1 = pts[1] - pts[0]
            v2 = pts[2] - pts[0]
            v3 = pts[3] - pts[0]
            a = 0.5 * float(np.linalg.norm(np.cross(v1, v2))) + 0.5 * float(np.linalg.norm(np.cross(v2, v3)))
        else:
            raise MeasurementError(f"Unsupported element topology with {len(pts)} nodes for area calculation")
        areas.append(a)

    return float(sum(areas)), areas


def calculate_solid_volume(
    nodes: dict[int, np.ndarray],
    elements: list[list[int]],
) -> tuple[float, list[float]]:
    """Calculate volume of 4-node tetrahedral or 8-node hexahedral elements."""
    vols = []
    for elem in elements:
        pts = [nodes[nid] for nid in elem]
        if len(pts) == 4:
            # Tetrahedron
            v = abs(float(np.dot(pts[1] - pts[0], np.cross(pts[2] - pts[0], pts[3] - pts[0])))) / 6.0
        elif len(pts) == 8:
            # Hexahedron decomposed into 5 tetrahedrons
            p = pts
            tets = [
                (0, 1, 3, 4),
                (1, 2, 3, 6),
                (1, 4, 5, 6),
                (3, 4, 6, 7),
                (1, 3, 4, 6),
            ]
            v = 0.0
            for t in tets:
                v += abs(float(np.dot(p[t[1]] - p[t[0]], np.cross(p[t[2]] - p[t[0]], p[t[3]] - p[t[0]])))) / 6.0
        else:
            raise MeasurementError(f"Unsupported solid element with {len(pts)} nodes")
        vols.append(v)

    return float(sum(vols)), vols


def measure_part_geometry_and_physics(
    nodes: dict[int, np.ndarray],
    elements: list[list[int]],
    measurement: str,
    density: float | None = None,
    thickness: float | None = None,
    units: str = "",
    density_units: str = "",
    part_id: int | None = None,
) -> dict[str, Any]:
    """Measure area, volume, mass, center of mass, and inertia of an FE component."""
    if measurement in ("mass", "inertia", "center_of_mass"):
        # Explicit acceptance check: "质量类测量缺少密度或单位时拒绝"
        if density is None or not math.isfinite(density) or density <= 0:
            raise MeasurementError("Mass and inertia measurements require explicit positive density")
        if not units or not density_units:
            raise MeasurementError("Mass and inertia measurements require explicit units and density_units")

    # Determine if solid or shell based on element node counts
    node_counts = {len(e) for e in elements}
    is_solid = 8 in node_counts or (4 in node_counts and thickness is None)

    if is_solid:
        total_vol, elem_vols = calculate_solid_volume(nodes, elements)
        total_area = None
    else:
        total_area, elem_areas = calculate_element_areas(nodes, elements)
        thk = float(thickness) if thickness is not None else 1.0
        total_vol = total_area * thk
        elem_vols = [a * thk for a in elem_areas]

    if measurement == "area":
        if total_area is None:
            raise MeasurementError("Area calculation requested for solid-only mesh without defined surface faces")
        return {
            "measurement": "area",
            "part_id": part_id,
            "total_area": total_area,
            "element_count": len(elements),
            "units": units or "mm^2",
        }

    if measurement == "volume":
        return {
            "measurement": "volume",
            "part_id": part_id,
            "total_volume": total_vol,
            "element_count": len(elements),
            "units": units or "mm^3",
        }

    # Center of mass calculation
    elem_centroids = []
    for elem in elements:
        c = np.mean([nodes[nid] for nid in elem], axis=0)
        elem_centroids.append(c)

    elem_centroids_arr = np.asarray(elem_centroids)
    elem_vols_arr = np.asarray(elem_vols)

    if total_vol > 0:
        com = np.sum(elem_centroids_arr * elem_vols_arr[:, None], axis=0) / total_vol
    else:
        com = np.zeros(3)

    total_mass = total_vol * float(density) if density is not None else 0.0

    if measurement == "mass":
        return {
            "measurement": "mass",
            "part_id": part_id,
            "total_mass": total_mass,
            "total_volume": total_vol,
            "density": float(density) if density is not None else None,
            "units": units,
            "density_units": density_units,
        }

    if measurement == "center_of_mass":
        return {
            "measurement": "center_of_mass",
            "part_id": part_id,
            "center_of_mass": [float(x) for x in com],
            "total_mass": total_mass,
            "units": units,
        }

    if measurement == "inertia":
        # Compute inertia tensor about center of mass
        dens = float(density) if density is not None else 1.0
        elem_masses = elem_vols_arr * dens

        rel_pos = elem_centroids_arr - com
        x = rel_pos[:, 0]
        y = rel_pos[:, 1]
        z = rel_pos[:, 2]

        ixx = float(np.sum(elem_masses * (y**2 + z**2)))
        iyy = float(np.sum(elem_masses * (x**2 + z**2)))
        izz = float(np.sum(elem_masses * (x**2 + y**2)))
        ixy = float(-np.sum(elem_masses * x * y))
        iyz = float(-np.sum(elem_masses * y * z))
        izx = float(-np.sum(elem_masses * z * x))

        tensor = np.array([[ixx, ixy, izx], [ixy, iyy, iyz], [izx, iyz, izz]])
        eigvals = np.linalg.eigvalsh(tensor)

        return {
            "measurement": "inertia",
            "part_id": part_id,
            "center_of_mass": [float(c) for c in com],
            "total_mass": total_mass,
            "inertia_tensor": {
                "ixx": ixx,
                "iyy": iyy,
                "izz": izz,
                "ixy": ixy,
                "iyz": iyz,
                "izx": izx,
            },
            "principal_moments": [float(p) for p in sorted(eigvals)],
            "units": units,
            "density_units": density_units,
        }

    raise MeasurementError(f"Unsupported part measurement: '{measurement}'")


def measure_clearance(
    set1_coords: np.ndarray,
    set2_coords: np.ndarray,
    set1_ids: list[int] | None = None,
    set2_ids: list[int] | None = None,
    units: str = "mm",
) -> dict[str, Any]:
    """Measure minimum Euclidean distance (clearance) between two sets of nodes."""
    p1 = np.asarray(set1_coords, dtype=float)
    p2 = np.asarray(set2_coords, dtype=float)

    if len(p1) == 0 or len(p2) == 0:
        raise MeasurementError("Clearance requires two non-empty sets of points")

    # Pairwise distance matrix
    # (N, 1, 3) - (1, M, 3)
    diff = p1[:, None, :] - p2[None, :, :]
    dist_sq = np.sum(diff**2, axis=-1)
    min_idx = np.unravel_index(np.argmin(dist_sq), dist_sq.shape)

    min_dist = float(math.sqrt(dist_sq[min_idx]))
    idx1, idx2 = min_idx

    closest_pt1 = [float(x) for x in p1[idx1]]
    closest_pt2 = [float(x) for x in p2[idx2]]

    id1 = set1_ids[idx1] if set1_ids and idx1 < len(set1_ids) else None
    id2 = set2_ids[idx2] if set2_ids and idx2 < len(set2_ids) else None

    return {
        "measurement": "clearance",
        "minimum_clearance": min_dist,
        "closest_point_set1": closest_pt1,
        "closest_point_set2": closest_pt2,
        "closest_node_id_set1": id1,
        "closest_node_id_set2": id2,
        "units": units,
    }
