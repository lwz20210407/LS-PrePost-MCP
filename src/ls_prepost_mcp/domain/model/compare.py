"""Semantic comparison of two keyword decks (formatting, comments and file layout ignored).

Used to check that a deck re-saved by LS-PrePost (possibly re-formatted or flattened)
still describes the same model, and that each case of a parameter study differs from
its base only where intended. Entities with IDs are compared by ID; keywords without
IDs (``*CONTROL_*``, ``*DATABASE_*``, ...) by order of appearance.
"""
from __future__ import annotations

import math
from collections import defaultdict

from . import lists
from .deck import KeywordDeck
from .fields import FieldError
from .layouts import RowMap, Unsupported
from .references import DEFINITIONS, MESH_KINDS, NOT_DEFINITIONS, _ident, _rule

SKIP = ("*KEYWORD", "*END", "*TITLE", "*INCLUDE", "*PARAMETER", "*COMMENT")
MESH_COLUMNS = {"node": ("x", "y", "z"), "shell": ("pid",) + tuple(f"n{i}" for i in range(1, 9)),
                "solid": ("pid",) + tuple(f"n{i}" for i in range(1, 9)),
                "beam": ("pid", "n1", "n2", "n3")}
SAMPLE = 20


def _number(text: str) -> object:
    text = text.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            from .fields import parse_number
            return parse_number(text)
        except FieldError:
            return text


def _snapshot(deck: KeywordDeck, include_mesh: bool) -> dict:
    by_id: dict[str, dict[int, object]] = defaultdict(dict)
    by_keyword: dict[str, list[dict]] = defaultdict(list)
    unchecked: dict[str, int] = defaultdict(int)
    for block in deck.iter_blocks():
        if block.name.startswith(SKIP):
            continue
        base = lists.base_name(block.name)[0]
        rule = None if base.startswith(NOT_DEFINITIONS) else _rule(base, DEFINITIONS)
        if rule and rule[1] in MESH_KINDS and not include_mesh:
            continue
        try:
            layout = deck.layout(block)
        except Unsupported:
            unchecked[block.name] += 1
            continue
        lookup = deck.lookup(block)
        if rule and rule[1] in MESH_KINDS and isinstance(layout.rows, RowMap):
            spots = [layout.rows.locate(c) for c in MESH_COLUMNS[rule[1]]]
            for key, indices in layout.rows.lines():
                by_id[rule[1]][key] = tuple(_number(layout.rows.cell(indices, s)) if s else None for s in spots)
            continue
        groups = ([(None, layout.fields)] if layout.fields else []) + list(layout.rows.items())
        for row, infos in groups:
            record = {info.name: deck._value(block, info).value for info in infos}
            if lists.is_list_set(block.name) and base not in lists.RANGE_SETS:
                record["members"] = tuple(sorted(deck.members(block)))
            if lists.is_curve(block.name):
                record["points"] = tuple(deck.points(block))
            if rule and rule[0] in record:
                ident = _ident(str(record[rule[0]]), lookup) if record[rule[0]] is not None else None
                if ident is not None:
                    by_id[rule[1]][ident] = record
                    continue
            if row is None or layout.key == "row":
                by_keyword[block.name].append(record)
            else:
                by_keyword[block.name].append({"row": row, **record})
    parameters = {r.definition.name.lower(): r.definition.value for r in deck.parameters}
    return {"by_id": by_id, "by_keyword": by_keyword, "unchecked": dict(unchecked), "parameters": parameters}


def _same(a: object, b: object, rel: float, abs_tol: float) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=abs_tol)
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(_same(x, y, rel, abs_tol) for x, y in zip(a, b))
    if isinstance(a, str) and isinstance(b, str):
        return a.strip() == b.strip()
    return a == b


def _record_diff(a: dict, b: dict, rel: float, abs_tol: float) -> dict:
    keys = sorted(set(a) | set(b))
    return {k: {"a": a.get(k), "b": b.get(k)} for k in keys if not _same(a.get(k), b.get(k), rel, abs_tol)}


def compare_decks(path_a: str, path_b: str, include_mesh: bool = True, rel_tol: float = 1e-9,
                  abs_tol: float = 0.0, coordinate_tol: float = 0.0) -> dict:
    """Differences between two decks by entity ID and keyword order.

    ``coordinate_tol`` is the node displacement (model length units) below which a node
    counts as unchanged.
    """
    a = _snapshot(KeywordDeck.load(path_a), include_mesh)
    b = _snapshot(KeywordDeck.load(path_b), include_mesh)
    entities = {}
    for kind in sorted(set(a["by_id"]) | set(b["by_id"])):
        ra, rb = a["by_id"].get(kind, {}), b["by_id"].get(kind, {})
        added, removed = sorted(set(rb) - set(ra)), sorted(set(ra) - set(rb))
        common = set(ra) & set(rb)
        entry = {"count_a": len(ra), "count_b": len(rb), "added": added[:SAMPLE], "removed": removed[:SAMPLE],
                 "added_count": len(added), "removed_count": len(removed)}
        if kind == "node":
            moved = []
            for nid in common:
                pa, pb = ra[nid], rb[nid]
                if any(v is None or isinstance(v, str) for v in pa + pb):
                    continue
                distance = math.dist(pa, pb)
                if distance > coordinate_tol:
                    moved.append((distance, nid))
            moved.sort(reverse=True)
            entry.update(changed_count=len(moved), max_displacement=moved[0][0] if moved else 0.0,
                         changed=[{"id": nid, "displacement": d} for d, nid in moved[:SAMPLE]])
        elif kind in MESH_KINDS:
            changed = sorted(i for i in common if not _same(ra[i], rb[i], rel_tol, abs_tol))
            entry.update(changed_count=len(changed), changed=[
                {"id": i, "a": ra[i], "b": rb[i]} for i in changed[:SAMPLE]])
        else:
            diffs = {i: _record_diff(ra[i], rb[i], rel_tol, abs_tol) for i in sorted(common)}
            changed = {i: d for i, d in diffs.items() if d}
            entry.update(changed_count=len(changed), changed=[{"id": i, "fields": d}
                                                              for i, d in list(changed.items())[:SAMPLE]])
        entities[kind] = entry
    keywords = {}
    for name in sorted(set(a["by_keyword"]) | set(b["by_keyword"])):
        la, lb = a["by_keyword"].get(name, []), b["by_keyword"].get(name, [])
        diffs = [{"index": i, "fields": d} for i, (x, y) in enumerate(zip(la, lb))
                 if (d := _record_diff(x, y, rel_tol, abs_tol))]
        if diffs or len(la) != len(lb):
            keywords[name] = {"count_a": len(la), "count_b": len(lb), "changed": diffs[:SAMPLE]}
    parameters = _record_diff(a["parameters"], b["parameters"], rel_tol, abs_tol)
    identical = (not keywords and not parameters and all(
        not e["added_count"] and not e["removed_count"] and not e["changed_count"] for e in entities.values()))
    return {"identical": identical, "entities": entities, "keywords": keywords, "parameters": parameters,
            "unchecked": {"a": a["unchecked"], "b": b["unchecked"]}, "mesh_compared": include_mesh}
