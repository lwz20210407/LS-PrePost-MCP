"""Element generation (tasks.yaml P08): arrays of copies and offset shell layers.

Same rules as :func:`mesh.copy_elements`: plain *ELEMENT_SHELL / *ELEMENT_SOLID rows of
standard-format decks, new IDs after the largest existing ones, nothing written to disk until
``save_as`` / ``save_in_place`` (``edit_deck`` applies a batch atomically).
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING

import numpy as np

from .fields import FieldError
from .geometry import elements, nodes
from .mesh import copy_elements, move_nodes, next_ids, source_elements, write_mesh

if TYPE_CHECKING:
    from .deck import KeywordDeck

MAX_COPIES = 1000


def array_elements(deck: KeywordDeck, keyword: str, element_ids: Iterable[int], count: int, *,
                   matrix: object = None, offset: object = None, part_id: int | None = None) -> dict:
    """``count`` copies; copy k is the selection transformed k times by ``x' = matrix @ x + offset``.

    A translation gives a linear array, a rotation about an axis a polar one. Copies are not
    merged with each other or with the original; run merge_duplicate_nodes where they touch.
    """
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MAX_COPIES:
        raise FieldError(f"count must be an integer in 1..{MAX_COPIES}")
    step = np.eye(3) if matrix is None else np.asarray(matrix, dtype=float).reshape(3, 3)
    shift = np.zeros(3) if offset is None else np.asarray(offset, dtype=float).reshape(3)
    if np.allclose(step, np.eye(3)) and not shift.any():
        raise FieldError("The step transform is the identity; the copies would coincide")
    ids = sorted({int(e) for e in element_ids})
    total, moved, copies = np.eye(3), np.zeros(3), []
    for _ in range(count):
        total, moved = step @ total, step @ moved + shift
        copies.append(copy_elements(deck, keyword, ids, matrix=total, offset=moved, part_id=part_id))
    return {"copies": count, "nodes": sum(c["nodes"] for c in copies), "elements": sum(c["elements"] for c in copies),
            "first_node": copies[0]["first_node"], "first_element": copies[0]["first_element"],
            "mirrored_copies": sum(c["mirrored"] for c in copies)}


def _distinct(corners: np.ndarray) -> np.ndarray:
    """Mask of corners that repeat no earlier corner of the same element (triangles: N4 = N3)."""
    mask = np.ones(corners.shape, dtype=bool)
    for k in range(1, corners.shape[1]):
        mask[:, k] = (corners[:, [k]] != corners[:, :k]).all(axis=1)
    return mask


def shell_nodal_normals(deck: KeywordDeck, conn: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """``(node IDs, unit nodal normals, diagnostics)`` of a set of shells.

    Nodal normal = area-weighted sum of the adjacent shells' normals (N1-N4 order), normalised.
    Refused when two shells sharing an edge are oriented against each other or a nodal normal
    vanishes (shells folded back onto each other).
    """
    corners = np.where(conn == 0, conn[:, [2]], conn)
    sense: dict[tuple[int, int], list[bool]] = defaultdict(list)
    for quad in corners.tolist():
        ring = list(dict.fromkeys(quad))
        for a, b in zip(ring, ring[1:] + ring[:1]):
            sense[(min(a, b), max(a, b))].append(a < b)
    against = sum(1 for s in sense.values() if len(s) == 2 and s[0] == s[1])
    if against:
        raise FieldError(f"Shell normals disagree across {against} shared edges; run unify_shell_normals first")
    ids, xyz = nodes(deck)
    order = np.argsort(ids)
    points = xyz[order[np.searchsorted(ids[order], corners)]]
    normals = np.cross(points[:, 2] - points[:, 0], points[:, 3] - points[:, 1])  # twice the area
    used, inverse = np.unique(corners, return_inverse=True)
    inverse = inverse.reshape(corners.shape)
    distinct = _distinct(corners)
    total = np.zeros((used.size, 3))
    for k in range(corners.shape[1]):
        np.add.at(total, inverse[distinct[:, k], k], normals[distinct[:, k]])
    length = np.linalg.norm(total, axis=1)
    flat = length <= 1e-12 * max(float(length.max()), 1e-300)
    if flat.any():
        raise FieldError(f"Nodal normal vanishes at {int(flat.sum())} nodes, e.g. {used[flat][:10].tolist()}")
    unit = total / length[:, None]
    own = normals / np.linalg.norm(normals, axis=1)[:, None]
    cosine = np.einsum("ekc,ec->ek", unit[inverse], own)
    spread = float(np.degrees(np.arccos(np.clip(cosine[distinct].min(), -1.0, 1.0))))
    branched = sum(1 for s in sense.values() if len(s) > 2)
    return used, unit, {"max_normal_spread_deg": spread, "edges_shared_by_more_than_two": branched}


def offset_shells(deck: KeywordDeck, element_ids: Iterable[int], distance: float, *, copy: bool = True,
                  part_id: int | None = None) -> dict:
    """Offset shells by ``distance`` along their nodal normals (positive = shell normal side).

    ``copy=True`` adds a new layer (new nodes and shells, same connectivity order, part kept
    unless ``part_id``); ``copy=False`` moves the shells' own nodes and is refused when a node
    is shared with an unselected shell or solid. On curved patches the layer is exactly
    ``distance`` away only along the nodal normals; ``max_normal_spread_deg`` (largest angle
    between a nodal normal and an adjacent shell normal) shows how far that is from flat.
    """
    distance = float(distance)
    if not np.isfinite(distance) or distance == 0.0:
        raise FieldError("distance must be finite and non-zero")
    block, wanted, pids, conn = source_elements(deck, "*ELEMENT_SHELL", element_ids, part_id)
    used, unit, diagnostics = shell_nodal_normals(deck, conn)
    result = {"shells": int(wanted.size), "nodes": int(used.size), "distance": distance, **diagnostics}
    if not copy:
        shared = _shared_nodes(deck, wanted, used)
        if shared.size:
            raise FieldError(f"{shared.size} nodes are shared with unselected shells or solids, "
                             f"e.g. {shared[:10].tolist()}; select those too or offset a copy")
        moved = move_nodes(deck, used, lambda keys, xyz: xyz + distance * unit[np.searchsorted(used, keys)],
                           "offset shells")
        return {**result, "copied": False, "max_rounding": moved["max_rounding"]}
    ids, xyz = nodes(deck)
    order = np.argsort(ids)
    points = xyz[order[np.searchsorted(ids[order], used)]] + distance * unit
    first_node, first_element = next_ids(deck, "*ELEMENT_SHELL")
    new_conn = np.where(conn > 0, first_node + np.searchsorted(used, conn), 0)
    if part_id is not None:
        pids = np.full(wanted.size, part_id)
    write_mesh(deck, "*ELEMENT_SHELL", block, first_node + np.arange(used.size), points,
               first_element + np.arange(wanted.size), pids, new_conn)
    return {**result, "copied": True, "first_node": first_node, "first_element": first_element}


def _shared_nodes(deck: KeywordDeck, selected: np.ndarray, used: np.ndarray) -> np.ndarray:
    eids, _, conn = elements(deck, "*ELEMENT_SHELL", 4)
    others = [conn[~np.isin(eids, selected)].ravel(), elements(deck, "*ELEMENT_SOLID", 8)[2].ravel()]
    return np.intersect1d(used, np.concatenate(others))


__all__ = ["MAX_COPIES", "array_elements", "offset_shells", "shell_nodal_normals"]
