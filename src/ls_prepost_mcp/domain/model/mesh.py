"""Keyword-level mesh editing (tasks.yaml P08): node transforms, element orientation, shell normals.

Only the selected rows change, in place and in the deck's own column layout; nothing is
written to disk until ``save_as`` / ``save_in_place``. Every operation plans all edits first
and applies them only when the whole plan is valid. Coordinates that are parameter
references are refused, never overwritten. Values that do not fit a field exactly are
rounded to the field width and the largest rounding is reported.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING

import numpy as np

from .fields import FieldError, FieldSlot, format_value, is_free_format, read_text, write_text
from .geometry import SAME_CONNECTIVITY, _node_block, _where, elements, nodes
from .layouts import RowMap, Unsupported
from .parameters import field_expression

if TYPE_CHECKING:
    from .blocks import Block
    from .deck import KeywordDeck

WIDTHS = {"*ELEMENT_SOLID": 8, "*ELEMENT_SHELL": 4}


def _plan_rows(deck: KeywordDeck, block: Block, rows: RowMap, updates: dict[int, dict[str, object]],
               kind: str) -> tuple[dict[int, str], float]:
    """New lines for ``updates`` (row key -> field -> value) and the largest rounding."""
    names = {name for values in updates.values() for name in values}
    spots = {name: rows.locate(name) for name in names}
    edits: dict[int, str] = {}
    worst = 0.0
    for key, values in updates.items():
        indices = rows.line_indices(key)
        for name, value in values.items():
            position, offset, width, token = spots[name]
            index = indices[position]
            line = edits.get(index, block.lines[index])
            slot = FieldSlot(0, offset, width, token if is_free_format(line) else None)
            if field_expression(read_text(line, slot)) is not None:
                raise FieldError(f"{_where(block)} row {key}: {name} is a parameter expression; not changed")
            text, exact = format_value(value, width, kind)
            if not exact:
                worst = max(worst, abs(float(text) - float(value)))
            edits[index] = write_text(line, slot, text)
    return edits, worst


def _apply(deck: KeywordDeck, plans: list[tuple[Block, dict[int, str]]], description: str) -> None:
    for block, edits in plans:
        if edits:
            deck.apply_lines(block, edits, description)


def transform_nodes(deck: KeywordDeck, node_ids: Iterable[int], matrix: object = None,
                    offset: object = None, description: str = "transform nodes") -> dict:
    """``x' = matrix @ x + offset`` for the given node IDs (all must exist)."""
    wanted = np.unique(np.asarray(list(node_ids), dtype=np.int64))
    matrix = np.eye(3) if matrix is None else np.asarray(matrix, dtype=float).reshape(3, 3)
    offset = np.zeros(3) if offset is None else np.asarray(offset, dtype=float).reshape(3)
    plans, found, worst = [], set(), 0.0
    for block in deck.blocks("*NODE"):
        keys, xyz = _node_block(deck, block)
        keys = np.asarray(keys, dtype=np.int64)
        mask = np.isin(keys, wanted)
        if not mask.any():
            continue
        moved = xyz[mask] @ matrix.T + offset
        updates = {int(k): {"x": float(p[0]), "y": float(p[1]), "z": float(p[2])} for k, p in zip(keys[mask], moved)}
        edits, rounding = _plan_rows(deck, block, deck.layout(block).rows, updates, "float")
        plans.append((block, edits))
        found.update(updates)
        worst = max(worst, rounding)
    missing = sorted(set(wanted.tolist()) - found)
    if missing:
        raise FieldError(f"{len(missing)} node IDs not found, e.g. {missing[:10]}")
    _apply(deck, plans, description)
    return {"nodes": len(found), "max_rounding": worst}


def translate_nodes(deck: KeywordDeck, node_ids: Iterable[int], vector: object) -> dict:
    return transform_nodes(deck, node_ids, offset=vector, description="translate nodes")


def rotation_matrix(axis: object, angle_deg: float) -> np.ndarray:
    """Right-handed rotation about ``axis`` by ``angle_deg`` (Rodrigues)."""
    unit = np.asarray(axis, dtype=float) / np.linalg.norm(axis)
    k = np.array([[0, -unit[2], unit[1]], [unit[2], 0, -unit[0]], [-unit[1], unit[0], 0]])
    angle = np.radians(angle_deg)
    return np.eye(3) + np.sin(angle) * k + (1 - np.cos(angle)) * k @ k


def rotate_nodes(deck: KeywordDeck, node_ids: Iterable[int], axis: object, angle_deg: float,
                 center: object = (0.0, 0.0, 0.0)) -> dict:
    matrix = rotation_matrix(axis, angle_deg)
    center = np.asarray(center, dtype=float)
    return transform_nodes(deck, node_ids, matrix, center - matrix @ center, description="rotate nodes")


def reflect_nodes(deck: KeywordDeck, node_ids: Iterable[int], normal: object, point: object = (0.0, 0.0, 0.0),
                  fix_orientation: bool = True) -> dict:
    """Mirror nodes in the plane through ``point`` with ``normal``.

    Mirroring turns elements inside out. With ``fix_orientation`` every shell and solid whose
    nodes are all mirrored gets its connectivity reordered back to positive orientation;
    elements only partly selected are left as they are and counted.
    """
    matrix, offset = reflection(normal, point)
    wanted = np.unique(np.asarray(list(node_ids), dtype=np.int64))
    flips: dict[str, list[int]] = {}
    partial = 0
    if fix_orientation:
        for keyword, width in WIDTHS.items():
            eids, _, conn = elements(deck, keyword, width)
            inside = np.isin(conn, wanted) | (conn == 0)  # N4 = 0 marks a triangle
            flips[keyword] = eids[inside.all(axis=1)].tolist()
            partial += int((inside.any(axis=1) & ~inside.all(axis=1)).sum())
    plans = [plan for keyword, ids in flips.items() if ids for plan in _flip_plans(deck, keyword, ids)]
    result = transform_nodes(deck, wanted.tolist(), matrix, offset, description="reflect nodes")
    _apply(deck, plans, "reorder mirrored elements")
    return {**result, "reoriented": {k: len(v) for k, v in flips.items()}, "partially_mirrored_elements": partial}


def flipped(conn: np.ndarray, solid: bool) -> np.ndarray:
    """Connectivity with reversed orientation; degenerate patterns (tet, wedge, triangle) are kept."""
    if solid:
        out = conn[:, [1, 0, 3, 2, 5, 4, 7, 6]]
        tet = (conn[:, 4:] == conn[:, [3]]).all(axis=1)
        out[tet] = conn[tet][:, [1, 0, 2, 3, 4, 5, 6, 7]]
        return out
    out = conn[:, [1, 0, 3, 2]]
    zero = conn[:, 3] == 0  # triangle written with N4 = 0
    out[zero] = conn[zero][:, [1, 0, 2, 3]]
    return out


def _element_rows(deck: KeywordDeck, keyword: str) -> Iterable[tuple[Block, RowMap]]:
    for block in deck.iter_blocks():
        name = block.name
        if name != keyword and not name.startswith(keyword + "_"):
            continue
        options = set(name[len(keyword) + 1:].split("_")) if name != keyword else set()
        layout = deck.layout(block) if options <= SAME_CONNECTIVITY[keyword] else None
        if layout is None or not isinstance(layout.rows, RowMap) or layout.key != "eid":
            raise Unsupported(f"{_where(block)}: element rows cannot be rewritten")
        yield block, layout.rows


def _flip_plans(deck: KeywordDeck, keyword: str, element_ids: Iterable[int]) -> list[tuple[Block, dict[int, str]]]:
    wanted = set(int(e) for e in element_ids)
    width = WIDTHS[keyword]
    names = [f"n{i}" for i in range(1, width + 1)]
    eids, _, conn = elements(deck, keyword, width)
    index = {int(e): i for i, e in enumerate(eids)}
    missing = sorted(wanted - index.keys())
    if missing:
        raise FieldError(f"{len(missing)} {keyword} IDs not found, e.g. {missing[:10]}")
    plans = []
    for block, rows in _element_rows(deck, keyword):
        here = [key for key in rows if key in wanted]
        if not here:
            continue
        mid = rows.locate("n5") if keyword == "*ELEMENT_SHELL" else None
        if mid is not None and any(rows.cell(rows.line_indices(key), mid).strip() not in ("", "0") for key in here):
            raise Unsupported(f"{_where(block)}: 8-node shells (N5-N8 set) are not reordered")
        new = flipped(conn[[index[key] for key in here]], keyword == "*ELEMENT_SOLID")
        updates = {key: dict(zip(names, map(int, values))) for key, values in zip(here, new)}
        plans.append((block, _plan_rows(deck, block, rows, updates, "int")[0]))
    return plans


def reverse_elements(deck: KeywordDeck, keyword: str, element_ids: Iterable[int]) -> dict:
    """Reverse orientation (shell normals, solid handedness) of the given elements."""
    ids = sorted({int(e) for e in element_ids})
    _apply(deck, _flip_plans(deck, keyword, ids), "reverse elements")
    return {"elements": len(ids)}


def unify_shell_normals(deck: KeywordDeck, element_ids: Iterable[int] | None = None,
                        direction: object = None) -> dict:
    """Make shell normals consistent across shared edges, per connected patch.

    Each patch keeps the orientation of its lowest element ID, or, with ``direction``, the
    orientation whose area-weighted mean normal points along ``direction``. Edges shared by
    more than two shells and patches that cannot be oriented (Moebius-like) are reported.
    """
    eids, _, conn = elements(deck, "*ELEMENT_SHELL", 4)
    keep = np.ones(eids.size, dtype=bool) if element_ids is None else np.isin(eids, list(element_ids))
    eids, conn = eids[keep], conn[keep]
    corners = np.where(conn == 0, conn[:, [2]], conn)
    edges = defaultdict(list)
    for row, quad in enumerate(corners.tolist()):
        ring = list(dict.fromkeys(quad))
        for a, b in zip(ring, ring[1:] + ring[:1]):
            edges[(min(a, b), max(a, b))].append((row, 1 if a < b else -1))
    neighbours = defaultdict(list)
    branched = 0
    for pairs in edges.values():
        branched += len(pairs) > 2
        for i, (row, sense) in enumerate(pairs):
            for other, other_sense in pairs[:i] + pairs[i + 1:]:
                neighbours[row].append((other, sense == other_sense))  # same sense -> must differ
    flip = np.zeros(eids.size, dtype=bool)
    seen = np.zeros(eids.size, dtype=bool)
    conflicts = patches = 0
    order = np.argsort(eids)
    ids, xyz = nodes(deck)
    lookup = {int(n): i for i, n in enumerate(ids)}
    for seed in order:
        if seen[seed]:
            continue
        patches += 1
        stack, members = [seed], [seed]
        seen[seed] = True
        while stack:
            row = stack.pop()
            for other, opposite in neighbours[row]:
                want = flip[row] != opposite
                if not seen[other]:
                    seen[other], flip[other] = True, want
                    stack.append(other)
                    members.append(other)
                elif flip[other] != want:
                    conflicts += 1
        if direction is not None:
            try:
                points = xyz[[[lookup[n] for n in quad] for quad in corners[members].tolist()]]
            except KeyError as error:
                raise FieldError(f"Shell patch uses undefined node {error.args[0]}") from error
            normals = np.cross(points[:, 2] - points[:, 0], points[:, 3] - points[:, 1])
            signs = np.where(flip[members], -1.0, 1.0)
            if float((normals * signs[:, None]).sum(axis=0) @ np.asarray(direction, dtype=float)) < 0:
                flip[members] = ~flip[members]
    reversed_ids = eids[flip].tolist()
    if reversed_ids:
        _apply(deck, _flip_plans(deck, "*ELEMENT_SHELL", reversed_ids), "unify shell normals")
    return {"shells": int(eids.size), "patches": patches, "reversed": len(reversed_ids),
            "edges_shared_by_more_than_two": branched, "orientation_conflicts": conflicts // 2}


def reflection(normal: object, point: object = (0.0, 0.0, 0.0)) -> tuple[np.ndarray, np.ndarray]:
    """``(matrix, offset)`` of the mirror in the plane through ``point`` with ``normal``."""
    unit = np.asarray(normal, dtype=float) / np.linalg.norm(normal)
    return np.eye(3) - 2 * np.outer(unit, unit), 2 * float(np.dot(np.asarray(point, dtype=float), unit)) * unit


def _rows_text(rows: list[list[str]], widths: list[int], newline: str) -> str:
    return "".join("".join(cell.rjust(width) for cell, width in zip(row, widths)) + newline for row in rows)


def copy_elements(deck: KeywordDeck, keyword: str, element_ids: Iterable[int], *, matrix: object = None,
                  offset: object = None, part_id: int | None = None) -> dict:
    """Copy elements and their nodes, transformed by ``x' = matrix @ x + offset``.

    New node and element IDs continue after the largest existing ones; a mirroring transform
    (negative determinant) reorders the copies to positive orientation. The copies keep their
    part unless ``part_id`` names an existing part. Elements of option variants (_THICKNESS,
    ...) and long / i10 decks are refused, because their extra cards would not be copied.
    """
    if deck.format != "standard":
        raise Unsupported(f"Copying elements in {deck.format} format decks is not supported")
    width = WIDTHS[keyword]
    wanted = sorted({int(e) for e in element_ids})
    plain = [b for b in deck.iter_blocks() if b.name == keyword]
    variants = [b for b in deck.iter_blocks() if b.name.startswith(keyword + "_")]
    eids, pids, conn = elements(deck, keyword, width)
    rows = {int(e): i for i, e in enumerate(eids)}
    missing = [e for e in wanted if e not in rows]
    if missing:
        raise FieldError(f"{len(missing)} {keyword} IDs not found, e.g. {missing[:10]}")
    if variants:
        in_variants = {int(e) for b in variants for e in deck.layout(b).rows}
        if in_variants & set(wanted):
            raise Unsupported(f"{keyword} option variants carry extra cards; copy them as plain elements first")
    if not plain:
        raise FieldError(f"No plain {keyword} block to copy from")
    report = deck.references(False)
    if part_id is not None and part_id not in report.defined.get("part", set()):
        raise FieldError(f"Part {part_id} is not defined")
    picked = np.asarray([rows[e] for e in wanted])
    old_conn, old_pids = conn[picked], pids[picked]
    ids, xyz = nodes(deck)
    used = np.unique(old_conn[old_conn > 0])
    lookup = {int(n): i for i, n in enumerate(ids)}
    absent = [int(n) for n in used if int(n) not in lookup]
    if absent:
        raise FieldError(f"Elements use undefined nodes, e.g. {absent[:10]}")
    matrix = np.eye(3) if matrix is None else np.asarray(matrix, dtype=float).reshape(3, 3)
    offset = np.zeros(3) if offset is None else np.asarray(offset, dtype=float).reshape(3)
    moved = xyz[[lookup[int(n)] for n in used]] @ matrix.T + offset
    first_node = int(ids.max()) + 1 if ids.size else 1
    first_element = int(eids.max()) + 1 if eids.size else 1
    renamed = {int(n): first_node + k for k, n in enumerate(used)}
    new_conn = np.vectorize(lambda n: renamed.get(int(n), 0))(old_conn)
    mirrored = bool(np.linalg.det(matrix) < 0)
    if mirrored:
        new_conn = flipped(new_conn, keyword == "*ELEMENT_SOLID")
    last = max(first_node + len(used), first_element + len(wanted))
    if len(str(last)) > 8:
        raise FieldError("New IDs need more than 8 digits; use a long-format deck")
    newline = plain[0].file.newline()
    node_rows = []
    for (old, new), point in zip(renamed.items(), moved):
        cells = [str(new)]
        for value in point:
            text_value, _ = format_value(float(value), 16, "float")
            cells.append(text_value)
        node_rows.append(cells)
    element_rows = [[str(first_element + k), str(part_id if part_id is not None else int(pid))]
                    + [str(int(n)) for n in row] for k, (pid, row) in enumerate(zip(old_pids, new_conn))]
    text = ("*NODE" + newline + _rows_text(node_rows, [8, 16, 16, 16], newline)
            + keyword + newline + _rows_text(element_rows, [8] * (2 + width), newline))
    deck.insert(text, file=plain[0].file)
    return {"nodes": len(used), "elements": len(wanted), "first_node": first_node,
            "first_element": first_element, "mirrored": mirrored}


__all__ = ["copy_elements", "flipped", "reflect_nodes", "reflection", "reverse_elements", "rotate_nodes",
           "rotation_matrix", "transform_nodes", "translate_nodes", "unify_shell_normals"]
