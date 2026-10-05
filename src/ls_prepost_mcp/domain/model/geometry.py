"""Mesh geometry from keyword decks: node/element arrays, selections and exterior segments.

Pure keyword-level (no LS-PrePost): nodes by box / sphere / plane / part, element faces
that belong to exactly one solid (exterior), oriented outward by geometry (the normal
points away from the owning element's centroid) and filtered by direction or region.
Triangles use the LS-DYNA segment form ``n1 n2 n3 n3``. Used to build node, part and
segment sets for loads and boundaries (tasks.yaml G03, P04).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from .fields import FieldError, parse_number
from .layouts import RowMap, Unsupported
from .parameters import field_expression, resolve_field

if TYPE_CHECKING:
    from .deck import KeywordDeck

# Faces as positions in the 8-node connectivity. Hexahedra, pentahedra (1 2 3 4 5 5 6 6) and
# pyramids (1 2 3 4 5 5 5 5) use the hexahedron table; collapsed faces are dropped afterwards.
HEX_FACES = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
# Tetrahedra (1 2 3 4 4 4 4 4): the hexahedron table would mix the apex into the base.
TET_FACES = ((0, 2, 1, 1), (0, 1, 3, 3), (1, 2, 3, 3), (0, 3, 2, 2))


def _number(text: str, lookup: dict) -> float:
    if field_expression(text) is not None:
        resolved = resolve_field(text, lookup)
        if not isinstance(resolved, (int, float)):
            raise FieldError(f"{text.strip()!r} is not numeric")
        return float(resolved)
    value = parse_number(text)
    return 0.0 if value is None else float(value)


def _fast_columns(block: object, rows: RowMap, names: list[str]) -> np.ndarray | None:
    """Columns as floats parsed by numpy when the block is plain fixed format (no commas, no &).

    Returns None when a cell needs the general parser (Fortran exponents, blanks, parameters).
    """
    if any("," in line or "&" in line for line in block.lines[1:]):
        return None
    spots = [rows.locate(name) for name in names]
    if any(spot is None for spot in spots):
        return None
    indices = [idx for _, idx in rows.lines()]
    columns = []
    for position, offset, width, _ in spots:
        texts = [block.lines[idx[position]][offset:offset + width] for idx in indices]
        try:
            columns.append(np.array(texts, dtype=float))
        except ValueError:
            return None
    return np.stack(columns, axis=1) if columns else np.empty((len(indices), 0))


def nodes(deck: KeywordDeck) -> tuple[np.ndarray, np.ndarray]:
    """``(ids, xyz)`` of every ``*NODE`` row in reading order."""
    ids: list[int] = []
    coords: list[tuple[float, ...]] = []
    for block in deck.blocks("*NODE"):
        layout = deck.layout(block)
        rows, lookup = layout.rows, deck.lookup(block)
        if not isinstance(rows, RowMap):
            raise Unsupported("*NODE without a row layout")
        fast = _fast_columns(block, rows, ["x", "y", "z"])
        if fast is not None:
            ids.extend(rows)
            coords.extend(map(tuple, fast))
            continue
        spots = [rows.locate(axis) for axis in ("x", "y", "z")]
        for key, indices in rows.lines():
            ids.append(key)
            coords.append(tuple(_number(rows.cell(indices, spot), lookup) for spot in spots))
    return np.asarray(ids, dtype=np.int64), np.asarray(coords, dtype=float).reshape(-1, 3)


def elements(deck: KeywordDeck, keyword: str, width: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(eids, pids, connectivity[n, width])`` for ``*ELEMENT_SOLID`` (8) or ``*ELEMENT_SHELL`` (4)."""
    eids, pids, conn = [], [], []
    columns = ["pid"] + [f"n{i}" for i in range(1, width + 1)]
    for block in deck.blocks(keyword):
        if block.name != keyword:
            continue  # option variants (_THICKNESS, ...) are not plain row tables
        layout = deck.layout(block)
        rows, lookup = layout.rows, deck.lookup(block)
        spots = [rows.locate(c) for c in columns] if isinstance(rows, RowMap) else []
        if not spots or any(s is None for s in spots):
            raise Unsupported(f"{keyword} rows are not available")
        fast = _fast_columns(block, rows, columns)
        if fast is not None:
            values = fast.astype(np.int64)
            eids.extend(rows)
            pids.extend(values[:, 0].tolist())
            conn.extend(values[:, 1:].tolist())
            continue
        for key, indices in rows.lines():
            values = [int(_number(rows.cell(indices, s), lookup)) for s in spots]
            eids.append(key)
            pids.append(values[0])
            conn.append(values[1:])
    return (np.asarray(eids, dtype=np.int64), np.asarray(pids, dtype=np.int64),
            np.asarray(conn, dtype=np.int64).reshape(-1, width))


def _normalize(faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Collapsed quads of degenerate solids: first-appearance order, triangles padded (a b c c)."""
    ordered = np.empty_like(faces)
    keep = np.zeros(len(faces), dtype=bool)
    for row, face in enumerate(faces):
        unique = list(dict.fromkeys(face.tolist()))
        keep[row] = len(unique) >= 3
        ordered[row] = (unique + [unique[-1]] * 4)[:4]
    return ordered[keep], keep


def _faces(conn: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Non-degenerate faces ``[m, 4]`` (triangles as ``a b c c``) and the owning element index."""
    distinct = (np.diff(np.sort(conn, axis=1), axis=1) != 0).sum(axis=1) + 1
    tet = (distinct == 4) & (conn[:, 4:] == conn[:, [3]]).all(axis=1)
    if ((distinct == 4) & ~tet).any() or (distinct < 4).any():
        raise Unsupported("Unrecognized degenerate solid connectivity")
    hexa = distinct == 8
    groups = []
    for mask, table, collapse in ((hexa, HEX_FACES, False), (tet, TET_FACES, False),
                                  (~hexa & ~tet, HEX_FACES, True)):  # pyramids, pentahedra
        index = np.nonzero(mask)[0]
        if not index.size:
            continue
        faces = conn[index][:, np.asarray(table)].reshape(-1, 4)
        owner = np.repeat(index, len(table))
        if collapse:
            faces, keep = _normalize(faces)
            owner = owner[keep]
        groups.append((faces, owner))
    if not groups:
        return np.empty((0, 4), dtype=np.int64), np.empty(0, dtype=np.int64)
    return np.concatenate([g[0] for g in groups]), np.concatenate([g[1] for g in groups])


def _normals(xyz: np.ndarray, faces: np.ndarray, lookup: np.ndarray) -> np.ndarray:
    p = xyz[lookup[faces]]
    normal = np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 1])  # diagonals; equals (b-a)x(c-a) for a b c c
    length = np.linalg.norm(normal, axis=1, keepdims=True)
    return np.divide(normal, length, out=np.zeros_like(normal), where=length > 0)


def _index(ids: np.ndarray) -> np.ndarray:
    lookup = np.full(int(ids.max()) + 1 if ids.size else 1, -1, dtype=np.int64)
    lookup[ids] = np.arange(ids.size)
    return lookup


def exterior_segments(deck: KeywordDeck, parts: list[int] | None = None, direction: list[float] | None = None,
                      angle: float = 30.0, box: list[float] | None = None) -> np.ndarray:
    """Outward exterior faces ``[m, 4]`` (node IDs) of solid elements, optionally filtered.

    ``direction``: keep faces whose outward normal is within ``angle`` degrees of it.
    ``box``: keep faces whose centroid lies in ``[xmin, ymin, zmin, xmax, ymax, zmax]``.
    """
    node_ids, xyz = nodes(deck)
    _, pids, conn = elements(deck, "*ELEMENT_SOLID", 8)
    if parts is not None:
        conn = conn[np.isin(pids, np.asarray(parts))]
    if not conn.size:
        return np.empty((0, 4), dtype=np.int64)
    lookup = _index(node_ids)
    if conn.max() >= lookup.size or (lookup[conn] < 0).any():
        raise FieldError("Solid elements reference nodes that are not defined")
    faces, owner = _faces(conn)
    triangle = faces[:, 2] == faces[:, 3]
    key = faces.copy()
    key[triangle, 3] = faces[triangle, :3].max(axis=1)
    _, inverse, counts = np.unique(np.sort(key, axis=1), axis=0, return_inverse=True, return_counts=True)
    outer = counts[inverse.ravel()] == 1
    faces, owner, triangle = faces[outer], owner[outer], triangle[outer]
    normal = _normals(xyz, faces, lookup)
    face_mid = np.stack([xyz[lookup[faces[:, i]]] for i in range(4)], axis=1).mean(axis=1)
    centroid = xyz[lookup[conn[owner]]].mean(axis=1)
    flip = np.einsum("ij,ij->i", normal, face_mid - centroid) < 0
    faces[flip & ~triangle] = faces[flip & ~triangle][:, [0, 3, 2, 1]]
    faces[flip & triangle] = faces[flip & triangle][:, [0, 2, 1, 1]]
    normal[flip] *= -1
    keep = np.ones(len(faces), dtype=bool)
    if direction is not None:
        d = np.asarray(direction, dtype=float)
        keep &= normal @ (d / np.linalg.norm(d)) >= np.cos(np.radians(angle))
    if box is not None:
        keep &= ((face_mid >= np.asarray(box[:3])) & (face_mid <= np.asarray(box[3:]))).all(axis=1)
    return faces[keep]


def select_nodes(deck: KeywordDeck, *, box: list[float] | None = None, sphere: list[float] | None = None,
                 plane: dict | None = None, parts: list[int] | None = None) -> np.ndarray:
    """Node IDs satisfying every given criterion (intersection)."""
    ids, xyz = nodes(deck)
    keep = np.ones(ids.size, dtype=bool)
    if box is not None:
        keep &= ((xyz >= np.asarray(box[:3])) & (xyz <= np.asarray(box[3:]))).all(axis=1)
    if sphere is not None:
        keep &= np.linalg.norm(xyz - np.asarray(sphere[:3]), axis=1) <= sphere[3]
    if plane is not None:
        normal = np.asarray(plane["normal"], dtype=float)
        normal /= np.linalg.norm(normal)
        keep &= np.abs((xyz - np.asarray(plane["point"])) @ normal) <= float(plane.get("tolerance", 1e-6))
    if parts is not None:
        used: set[int] = set()
        for keyword, width in (("*ELEMENT_SOLID", 8), ("*ELEMENT_SHELL", 4)):
            _, pids, conn = elements(deck, keyword, width)
            used.update(np.unique(conn[np.isin(pids, np.asarray(parts))]).tolist())
        keep &= np.isin(ids, np.asarray(sorted(used), dtype=np.int64))
    return ids[keep]


def select_elements(deck: KeywordDeck, keyword: str, *, parts: list[int] | None = None,
                    box: list[float] | None = None) -> np.ndarray:
    """Element IDs of ``*ELEMENT_SOLID`` / ``*ELEMENT_SHELL`` by part and/or centroid inside ``box``."""
    width = 8 if keyword == "*ELEMENT_SOLID" else 4
    eids, pids, conn = elements(deck, keyword, width)
    keep = np.ones(eids.size, dtype=bool)
    if parts is not None:
        keep &= np.isin(pids, np.asarray(parts))
    if box is not None and eids.size:
        node_ids, xyz = nodes(deck)
        lookup = _index(node_ids)
        centroid = xyz[lookup[conn]].mean(axis=1)
        keep &= ((centroid >= np.asarray(box[:3])) & (centroid <= np.asarray(box[3:]))).all(axis=1)
    return eids[keep]
