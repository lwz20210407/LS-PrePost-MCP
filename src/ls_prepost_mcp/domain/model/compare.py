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
from .matching import scalar_equal
from .references import DEFINITIONS, MESH_KINDS, NOT_DEFINITIONS, _ident, _rule

SKIP = ("*KEYWORD", "*END", "*TITLE", "*INCLUDE", "*PARAMETER", "*COMMENT")
MESH_COLUMNS = {"node": ("x", "y", "z"), "shell": ("pid",) + tuple(f"n{i}" for i in range(1, 9)),
                "solid": ("pid",) + tuple(f"n{i}" for i in range(1, 9)),
                "beam": ("pid", "n1", "n2", "n3")}
SAMPLE = 20


class _Record(dict):
    """Private type sidecar; JSON/diff values retain their existing plain shape."""

    def __init__(self, values, kinds):
        super().__init__(values)
        self.kinds = kinds


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
    kind_cache, mesh_kinds = {}, {}

    def typed(values, kinds):
        # Large repeated tables share one small field-type map per schema.
        descriptor = tuple(sorted(kinds.items()))
        return _Record(values, kind_cache.setdefault(descriptor, kinds))
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
            columns = MESH_COLUMNS[rule[1]]
            spots = [layout.rows.locate(c) for c in columns]
            declared = {c.name: c.kind for card in layout.rows.template for c in card}
            mesh_kinds[rule[1]] = tuple(declared.get(c) for c in columns)
            for key, indices in layout.rows.lines():
                values = []
                infos = None
                for name, spot in zip(columns, spots):
                    value = _number(layout.rows.cell(indices, spot)) if spot else None
                    if isinstance(value, str):
                        # Parameters use the existing AST decoder only when a
                        # cell needs it; ordinary numeric rows keep the fast path.
                        if infos is None:
                            infos = {info.name: info for info in layout.rows[key]}
                        value = deck._value(block, infos[name]).value
                    values.append(value)
                by_id[rule[1]][key] = tuple(values)
            continue
        groups = ([(None, layout.fields)] if layout.fields else []) + list(layout.rows.items())
        for row, infos in groups:
            record = {info.name: deck._value(block, info).value for info in infos}
            kinds = {info.name: info.kind for info in infos}
            if base == "*SET_NODE_LIST_GENERATE" and row is None:
                from .node_sets import range_rows

                record["node_ranges"] = range_rows(deck, block)
                kinds["node_ranges"] = "int"
            if base == "*SET_NODE_ADD" and row is None:
                record["node_set_operands"] = tuple(deck.members(block))
                kinds["node_set_operands"] = "int"
            if lists.is_list_set(block.name) and base not in lists.RANGE_SETS:
                record["members"] = tuple(sorted(deck.members(block)))
                kinds["members"] = "int"
            if lists.is_curve(block.name):
                record["points"] = tuple(deck.points(block))
                kinds["points"] = "float"
            if rule and rule[0] in record:
                ident = _ident(str(record[rule[0]]), lookup) if record[rule[0]] is not None else None
                if ident is not None:
                    if lists.collected(block.name):
                        record["collect"] = True
                    record = typed(record, kinds)
                    earlier = by_id[rule[1]].get(ident)
                    by_id[rule[1]][ident] = record if earlier is None else _merge_definitions(earlier, record)
                    continue
            if row is None or layout.key == "row":
                by_keyword[block.name].append(typed(record, kinds))
            else:
                by_keyword[block.name].append(typed({"row": row, **record}, {"row": "int", **kinds}))
    parameters = typed({r.definition.name.lower(): r.definition.value for r in deck.parameters},
                       {r.definition.name.lower(): {"integer": "int", "real": "float", "character": "str"}.get(r.definition.type)
                        for r in deck.parameters})
    return {"by_id": by_id, "by_keyword": by_keyword, "unchecked": dict(unchecked), "parameters": parameters,
            "mesh_kinds": mesh_kinds}


def _merge_definitions(earlier: dict, record: dict) -> dict:
    """Several blocks define one ID: ``_COLLECT`` sets merge their members, anything else is a
    duplicate. Every block's own fields are kept, so no difference between decks is hidden."""
    def own(r: dict) -> tuple:
        return tuple(sorted((k, v) for k, v in r.items() if k not in ("members", "collect")))

    merged = {"collect": bool(earlier.get("collect")) and bool(record.get("collect")),
              "blocks": earlier.get("blocks", (own(earlier),)) + (own(record),)}
    def own_kinds(r):
        return {k: v for k, v in r.kinds.items() if k not in ("members", "collect")}

    kinds = {"blocks": earlier.kinds.get("blocks", (own_kinds(earlier),)) + (own_kinds(record),)}
    if "members" in earlier or "members" in record:
        merged["members"] = tuple(sorted(earlier.get("members", ()) + record.get("members", ())))
        kinds["members"] = "int"
    return _Record(merged, kinds)


def _same(a: object, b: object, rel: float, abs_tol: float, kind_a=None, kind_b=None) -> bool:
    if isinstance(kind_a, dict) and isinstance(kind_b, dict):
        return not _record_diff(_Record(dict(a), kind_a), _Record(dict(b), kind_b), rel, abs_tol)
    if isinstance(a, tuple) and isinstance(b, tuple):
        if len(a) != len(b):
            return False
        ka = kind_a if isinstance(kind_a, tuple) else (kind_a,) * len(a)
        kb = kind_b if isinstance(kind_b, tuple) else (kind_b,) * len(b)
        return len(ka) == len(kb) == len(a) and all(
            _same(x, y, rel, abs_tol, kx, ky) for x, y, kx, ky in zip(a, b, ka, kb))
    if kind_a is not None and kind_b is not None and kind_a != kind_b:
        return False
    return scalar_equal(a, b, kind_a or kind_b, rel_tol=rel, abs_tol=abs_tol)


def _record_diff(a: dict, b: dict, rel: float, abs_tol: float) -> dict:
    keys = sorted(set(a) | set(b))
    ka, kb = getattr(a, "kinds", {}), getattr(b, "kinds", {})
    return {k: {"a": a.get(k), "b": b.get(k)} for k in keys
            if not _same(a.get(k), b.get(k), rel, abs_tol, ka.get(k), kb.get(k))}


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
            changed = sorted(i for i in common if not _same(ra[i], rb[i], rel_tol, abs_tol,
                                                          a["mesh_kinds"].get(kind), b["mesh_kinds"].get(kind)))
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
