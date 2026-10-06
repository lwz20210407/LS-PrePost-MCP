"""``core.contracts.Selector`` resolved to IDs of a keyword deck (I02 Selector adapter for M3).

A keyword deck has reference coordinates only, so ``configuration="deformed"``, a state and a
validity other than ``all`` are refused (they belong to results). Entity types: ``node``,
``shell``, ``solid`` and ``part``; the others are result-side domains and are refused.

Predicates:

* ``all`` / ``none``; ``ids`` (every ID must exist); ``parts`` (entities of those parts);
* ``sets``: list sets of the declared ``set_type`` (node / shell / solid / part / segment; a
  segment set gives its nodes); ``*_ADD`` / ``*_GENERATE`` sets are refused;
* ``box`` / ``sphere``: nodes by position, elements by centroid;
* ``plane``: signed distance to the plane through ``origin`` along ``normal``; ``on`` keeps
  |d| <= tolerance, ``positive`` d > tolerance, ``negative`` d < -tolerance;
* ``surface``: nodes of the exterior faces of the solid elements of ``part_ids`` (a feature
  angle is not supported and is refused);
* ``boolean``: union / intersection / difference of resolved operands.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ...core import contracts as c
from .fields import FieldError
from .geometry import _index, elements, exterior_segments, nodes

if TYPE_CHECKING:
    from .deck import KeywordDeck

ELEMENTS = {"shell": ("*ELEMENT_SHELL", 4), "solid": ("*ELEMENT_SOLID", 8)}
SET_PREFIX = {"node": "*SET_NODE", "shell": "*SET_SHELL", "solid": "*SET_SOLID", "part": "*SET_PART",
              "segment": "*SET_SEGMENT"}


def selector(value: c.Selector | dict) -> c.Selector:
    """Validate a Selector given as the contract object or its JSON form."""
    return value if isinstance(value, c.Selector) else c.Selector.model_validate(value, strict=False)


def resolve(deck: KeywordDeck, value: c.Selector | dict) -> np.ndarray:
    """Sorted unique IDs selected by ``value``."""
    chosen = selector(value)
    if chosen.configuration != "reference" or chosen.validity != "all":
        raise FieldError("A keyword deck has reference coordinates only; deformed states and element validity "
                         "are result selections")
    if chosen.entity_type not in ("node", "shell", "solid", "part"):
        raise FieldError(f"Selector entity type {chosen.entity_type!r} is not a keyword-deck entity "
                         "(use node, shell, solid or part)")
    return np.unique(_predicate(deck, chosen.entity_type, chosen.predicate)).astype(np.int64)


def _universe(deck: KeywordDeck, entity: str) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
    """(IDs, positions, part IDs) of every entity of the type; positions are element centroids."""
    if entity == "node":
        ids, xyz = nodes(deck)
        return ids, xyz, None
    if entity == "part":
        return np.asarray(sorted(deck.references(False).defined.get("part", set())), dtype=np.int64), None, None
    keyword, width = ELEMENTS[entity]
    eids, pids, conn = elements(deck, keyword, width)
    node_ids, xyz = nodes(deck)
    lookup = _index(node_ids)
    if conn.size and (conn.max() >= lookup.size or (lookup[conn] < 0).any()):
        raise FieldError(f"{keyword} rows reference undefined nodes")
    centroid = xyz[lookup[conn]].mean(axis=1) if conn.size else np.empty((0, 3))
    return eids, centroid, pids


def _set_members(deck: KeywordDeck, set_type: str, sids: tuple[int, ...]) -> dict[int, list]:
    prefix = SET_PREFIX[set_type]
    found: dict[int, list] = {}
    for block in deck.iter_blocks():
        name = block.name
        if not (name == prefix or name.startswith(prefix + "_")):
            continue
        if any(part in name for part in ("_ADD", "_GENERATE", "_GENERAL", "_COLLECT")):
            raise FieldError(f"{name} sets are not resolved by the Selector adapter; use list sets")
        sid = int(deck.get(block, "sid").value)
        if sid not in sids:
            continue
        if set_type == "segment":
            rows = deck.layout(block).rows
            found[sid] = [int(v.value) for key in rows for v in (deck.get(block, n, row=key) for n in
                                                                  ("n1", "n2", "n3", "n4")) if v.value]
        else:
            found[sid] = [int(m) for m in deck.members(block)]
    missing = sorted(set(sids) - set(found))
    if missing:
        raise FieldError(f"{prefix} sets not defined: {missing[:10]}")
    return found


def _nodes_of_elements(deck: KeywordDeck, entity: str, eids: np.ndarray) -> np.ndarray:
    keyword, width = ELEMENTS[entity]
    all_eids, _, conn = elements(deck, keyword, width)
    used = conn[np.isin(all_eids, eids)]
    return np.unique(used[used > 0])


def _nodes_of_parts(deck: KeywordDeck, parts: np.ndarray) -> np.ndarray:
    used = [np.empty(0, dtype=np.int64)]
    for entity in ELEMENTS:
        keyword, width = ELEMENTS[entity]
        _, pids, conn = elements(deck, keyword, width)
        chosen = conn[np.isin(pids, parts)]
        used.append(chosen[chosen > 0])
    return np.unique(np.concatenate(used))


def _predicate(deck: KeywordDeck, entity: str, predicate: object) -> np.ndarray:
    kind = predicate.kind
    if kind == "boolean":
        parts = [_predicate(deck, entity, operand) for operand in predicate.operands]
        if predicate.operator == "union":
            return np.unique(np.concatenate(parts))
        if predicate.operator == "intersection":
            result = parts[0]
            for other in parts[1:]:
                result = np.intersect1d(result, other)
            return result
        return np.setdiff1d(parts[0], parts[1])
    ids, positions, pids = _universe(deck, entity)
    if kind == "all":
        return ids
    if kind == "none":
        return np.empty(0, dtype=np.int64)
    if kind == "ids":
        wanted = np.asarray(predicate.ids, dtype=np.int64)
        missing = np.setdiff1d(wanted, ids)
        if missing.size:
            raise FieldError(f"{missing.size} {entity} IDs are not defined, e.g. {missing[:10].tolist()}")
        return wanted
    if kind == "parts":
        parts = np.asarray(predicate.ids, dtype=np.int64)
        if entity == "node":
            return _nodes_of_parts(deck, parts)
        if entity == "part":
            return _predicate_ids(ids, parts, "part")
        return ids[np.isin(pids, parts)]
    if kind == "sets":
        members = np.asarray([m for group in _set_members(deck, predicate.set_type, predicate.ids).values()
                              for m in group], dtype=np.int64)
        if predicate.set_type == entity or (predicate.set_type == "segment" and entity == "node"):
            return members
        if entity == "node" and predicate.set_type in ELEMENTS:
            return _nodes_of_elements(deck, predicate.set_type, members)
        if entity == "node" and predicate.set_type == "part":
            return _nodes_of_parts(deck, members)
        if entity in ELEMENTS and predicate.set_type == "part":
            return ids[np.isin(pids, members)]
        raise FieldError(f"A {predicate.set_type} set does not select {entity} entities")
    if kind == "surface":
        if predicate.feature_angle_degrees is not None:
            raise FieldError("Surface selection by feature angle is not supported for keyword decks")
        if entity != "node":
            raise FieldError("Surface selection resolves to nodes (entity_type node)")
        faces = exterior_segments(deck, parts=list(predicate.part_ids))
        return np.unique(faces[faces > 0])
    if positions is None:
        raise FieldError(f"A {kind} predicate needs positions; {entity} entities have none")
    if kind == "box":
        low, high = np.asarray(predicate.minimum), np.asarray(predicate.maximum)
        return ids[((positions >= low) & (positions <= high)).all(axis=1)]
    if kind == "sphere":
        return ids[np.linalg.norm(positions - np.asarray(predicate.center), axis=1) <= predicate.radius]
    if kind == "plane":
        normal = np.asarray(predicate.normal, dtype=float)
        distance = (positions - np.asarray(predicate.origin)) @ (normal / np.linalg.norm(normal))
        keep = {"on": np.abs(distance) <= predicate.tolerance, "positive": distance > predicate.tolerance,
                "negative": distance < -predicate.tolerance}[predicate.side]
        return ids[keep]
    raise FieldError(f"Unsupported selection predicate {kind!r}")


def _predicate_ids(ids: np.ndarray, wanted: np.ndarray, kind: str) -> np.ndarray:
    missing = np.setdiff1d(wanted, ids)
    if missing.size:
        raise FieldError(f"{missing.size} {kind} IDs are not defined, e.g. {missing[:10].tolist()}")
    return wanted


__all__ = ["resolve", "selector"]
