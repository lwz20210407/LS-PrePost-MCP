"""Keyword-level ID renumbering, duplicate-node merging and element deletion (tasks.yaml P08).

An ID changes in its defining row and in every field that refers to it: the hand rules and
PyDYNA link fields of :mod:`references` / :mod:`links`, set member lists and contact
surfaces of the matching type. The operation is refused, with nothing changed, when it
cannot be complete or exact:

* a block that may refer to the kind cannot be read;
* a ``*SET_*_GENERATE`` range contains an affected ID;
* an affected reference is written as a parameter expression;
* a new ID collides with a kept ID or does not fit its field.

After applying, the references are collected again and must not show new dangling IDs.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

import numpy as np

from . import lists, references
from .fields import FieldError, FieldSlot, format_value, is_free_format, read_text, write_text
from .geometry import _where, elements, nodes
from .layouts import RowMap, Unsupported
from .parameters import field_expression
from .quality import coincident_nodes
from .references import DEFINITIONS, MESH_KINDS, ReferenceReport, _ident, _rule, coded_pairs

if TYPE_CHECKING:
    from .blocks import Block
    from .deck import KeywordDeck

ELEMENT_KINDS = {"*ELEMENT_SHELL": "shell", "*ELEMENT_SOLID": "solid", "*ELEMENT_BEAM": "beam"}


def _may_refer(name: str, kind: str) -> bool:
    """Whether an unreadable block could hold IDs of ``kind`` (conservative)."""
    base = lists.base_name(name)[0]
    if base.startswith(("*SET_", "*CONTACT_")):
        return True
    definition = _rule(base, DEFINITIONS)
    return bool((definition and definition[1] == kind)
                or any(target == kind for _, target in references._references(name, base, True)))


ID_LIKE = re.compile(r"(?:id|sid)(?:_\d+)?$|^lc")
SELF_IDS = {"wid", "jid", "coupid", "did"}  # a keyword's own ID, not a reference


def _unruled(deck: KeywordDeck, block: Block, layout: object, covered: set[str], mapping: dict[int, int],
             kind: str, problems: list[str]) -> None:
    """Refuse when an ID-like integer field that no rule covers holds an affected ID.

    Without a rule the field cannot be rewritten, and leaving it could silently point at a
    different object after renumbering (found by edit-then-solve regression runs).
    """
    def suspicious(info: object) -> bool:
        return (info.kind == "int" and info.name not in covered and info.name not in SELF_IDS
                and info.card not in ("id", "title") and bool(ID_LIKE.search(info.name)))

    lookup = deck.lookup(block)
    groups = [list(layout.fields)]
    rows = layout.rows
    if isinstance(rows, RowMap):
        columns = [(position, column) for position, template in enumerate(rows.template) for column in template
                   if column.kind == "int" and column.name not in covered and column.name not in SELF_IDS
                   and ID_LIKE.search(column.name)]
        for key, indices in rows.lines():
            for position, column in columns:
                if position < len(indices):
                    text = rows.cell(indices, (position, column.offset, column.width, None))
                    if _ident(text, lookup) in mapping:
                        problems.append(f"{_where(block)} row {key} {column.name}={text.strip()} may be a {kind} "
                                        "ID but no rule covers this field")
    else:
        groups += [list(infos) for infos in rows.values()]
    for infos in groups:
        for info in infos:
            if suspicious(info):
                value = _ident(read_text(block.lines[info.slot.line], info.slot), lookup)
                if value in mapping:
                    problems.append(f"{_where(block)} {info.name}={value} may be a {kind} ID but no rule covers "
                                    "this field")


def _cell(block: Block, line: str, offset: int, width: int, token: int | None, mapping: dict[int, int],
          lookup: dict, problems: list[str], where: Callable[[], str]) -> str | None:
    """New line when the cell holds a mapped ID, else None."""
    slot = FieldSlot(0, offset, width, token if is_free_format(line) else None)
    text = read_text(line, slot)
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.isdigit():
        ident = int(stripped)
    else:
        ident = _ident(text, lookup)
        if ident in mapping and field_expression(text) is not None:
            problems.append(f"{where()}: ID {ident} is a parameter expression")
            return None
    if ident not in mapping:
        return None
    new, _ = format_value(mapping[ident], width, "int")
    return write_text(line, slot, new)


def _plan(deck: KeywordDeck, kind: str, mapping: dict[int, int], definitions: bool) -> tuple[list, list, int]:
    """Line edits and member-list rewrites for ``mapping`` (refuses when incomplete)."""
    report = ReferenceReport()
    plans = references._plans(deck, True, report)  # elements refer to parts, so always scan the mesh
    problems = [f"{name} x{count} cannot be read" for name, count in report.unchecked.items() if _may_refer(name, kind)]
    line_plans, member_plans, cells = [], [], 0
    for plan in plans:
        block, layout = plan.block, plan.layout
        names = [name for name, target in plan.refs if target == kind]
        if definitions and plan.definition and plan.definition[1] == kind:
            names.append(plan.definition[0])
        lookup = deck.lookup(block)
        names += [name for name, target in coded_pairs(plan.coded, {i.name: i for i in layout.fields}, block, lookup)
                  if target == kind]
        edits: dict[int, str] = {}
        if names or plan.coded:
            for info in layout.fields:
                if info.name in names:
                    line = edits.get(info.slot.line, block.lines[info.slot.line])
                    new = _cell(block, line, info.slot.offset, info.slot.width, info.slot.token, mapping, lookup,
                                problems, lambda i=info: f"{_where(block)} {i.name}")
                    if new is not None:
                        edits[info.slot.line], cells = new, cells + 1
            rows = layout.rows
            if isinstance(rows, RowMap):
                spots = [rows.locate(name) for name in names]
                for key, indices in rows.lines():
                    for name, spot in zip(names, spots):
                        if spot is None:
                            continue
                        index = indices[spot[0]] if spot[0] < len(indices) else None
                        if index is None:
                            continue
                        line = edits.get(index, block.lines[index])
                        new = _cell(block, line, spot[1], spot[2], spot[3], mapping, lookup, problems,
                                    lambda k=key, n=name: f"{_where(block)} row {k} {n}")
                        if new is not None:
                            edits[index], cells = new, cells + 1
            else:
                for key, infos in rows.items():
                    row_names = names + [name for name, target in
                                         coded_pairs(plan.coded, {i.name: i for i in infos}, block, lookup)
                                         if target == kind]
                    for info in infos:
                        if info.name in row_names:
                            line = edits.get(info.slot.line, block.lines[info.slot.line])
                            new = _cell(block, line, info.slot.offset, info.slot.width, info.slot.token, mapping,
                                        lookup, problems, lambda k=key, i=info: f"{_where(block)} row {k} {i.name}")
                            if new is not None:
                                edits[info.slot.line], cells = new, cells + 1
        if edits:
            line_plans.append((block, edits))
        if plan.members == kind:
            old = deck.members(block)
            new_members = [mapping.get(ident, ident) for ident in old]
            if new_members != old:
                member_plans.append((block, new_members))
                cells += sum(a != b for a, b in zip(old, new_members))
    by_block = {id(plan.block): plan for plan in plans}
    for block in deck.iter_blocks():
        plan = by_block.get(id(block))
        try:
            layout = plan.layout if plan else deck.layout(block)
        except (Unsupported, FieldError):
            layout = None
        if layout is not None:
            covered = set()
            if plan:
                covered = {name for name, _ in plan.refs} | {field for rule in plan.coded for field in rule[:2]}
                if plan.definition:
                    covered.add(plan.definition[0])
            _unruled(deck, block, layout, covered, mapping, kind, problems)
        base = lists.base_name(block.name)[0]
        if lists.RANGE_KINDS.get(base) == kind:
            for first, last in lists.ranges(block, deck._long(block)):
                if any(first <= ident <= last for ident in mapping):
                    problems.append(f"{_where(block)}: range {first}-{last} contains an affected ID")
    if problems:
        shown = "; ".join(problems[:20]) + (f"; ... {len(problems) - 20} more" if len(problems) > 20 else "")
        raise FieldError(f"Cannot change {kind} IDs completely: {shown}")
    return line_plans, member_plans, cells


def _apply(deck: KeywordDeck, line_plans: list, member_plans: list, description: str) -> None:
    for block, edits in line_plans:
        deck.apply_lines(block, edits, description)
    for block, members in member_plans:
        deck.set_members(block, members)


def renumber(deck: KeywordDeck, kind: str, mapping: dict[int, int]) -> dict:
    """Give IDs of ``kind`` (``node``, ``shell``, ``part``, ``material``, ...) new values everywhere."""
    mapping = {int(a): int(b) for a, b in mapping.items() if int(a) != int(b)}
    if any(b <= 0 for b in mapping.values()) or len(set(mapping.values())) != len(mapping):
        raise FieldError("New IDs must be positive and distinct")
    before = deck.references(True)
    defined = before.defined.get(kind, set())
    missing = sorted(set(mapping) - defined)
    if missing:
        raise FieldError(f"{len(missing)} {kind} IDs are not defined, e.g. {missing[:10]}")
    clash = sorted(set(mapping.values()) & (defined - set(mapping)))
    if clash:
        raise FieldError(f"New {kind} IDs already in use, e.g. {clash[:10]}")
    line_plans, member_plans, cells = _plan(deck, kind, mapping, definitions=True)
    _apply(deck, line_plans, member_plans, f"renumber {kind}")
    after = deck.references(True)
    expected = (defined - set(mapping)) | set(mapping.values())
    missing_after = after.dangling_count + after.unverified_count
    if after.defined.get(kind, set()) != expected or missing_after > before.dangling_count + before.unverified_count:
        raise FieldError("Renumbering failed verification; reload the deck before saving")
    return {"kind": kind, "renumbered": len(mapping), "cells_changed": cells,
            "blocks_changed": len(line_plans) + len(member_plans)}


def renumber_range(deck: KeywordDeck, kind: str, first: int, last: int, start: int) -> dict:
    """Renumber the defined IDs in ``[first, last]`` consecutively from ``start`` (order kept)."""
    defined = sorted(i for i in deck.references(kind in MESH_KINDS).defined.get(kind, set()) if first <= i <= last)
    return renumber(deck, kind, {old: start + n for n, old in enumerate(defined)})


def _node_rows(deck: KeywordDeck) -> list[tuple[Block, RowMap]]:
    return [(block, deck.layout(block).rows) for block in deck.blocks("*NODE")]


def merge_duplicate_nodes(deck: KeywordDeck, tolerance: float, node_ids: Iterable[int] | None = None) -> dict:
    """Merge nodes closer than ``tolerance``: the lowest ID of each group stays where it is, the
    others disappear and every reference to them points to the kept node."""
    ids, xyz = nodes(deck)
    if node_ids is not None:
        keep = np.isin(ids, np.asarray(list(node_ids), dtype=np.int64))
        ids, xyz = ids[keep], xyz[keep]
    parent: dict[int, int] = {}

    def root(a: int) -> int:
        while parent.get(a, a) != a:
            a = parent[a]
        return a

    pairs = coincident_nodes(ids, xyz, tolerance)
    for a, b, _ in pairs:
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    mapping = {a: root(a) for a in list(parent) if root(a) != a}
    if not mapping:
        return {"merged": 0, "groups": 0, "max_distance": 0.0}
    line_plans, member_plans, cells = _plan(deck, "node", mapping, definitions=False)
    removals = []
    for block, rows in _node_rows(deck):
        drop = [i for key, indices in rows.lines() if key in mapping for i in indices]
        if drop:
            removals.append((block, drop))
    _apply(deck, line_plans, member_plans, "merge duplicate nodes")
    for block, drop in removals:
        deck.remove_lines(block, drop, "merge duplicate nodes")
    collapsed = 0
    for keyword, width in (("*ELEMENT_SOLID", 8), ("*ELEMENT_SHELL", 4)):
        _, _, conn = elements(deck, keyword, width)
        conn = np.where(conn == 0, conn[:, [2]], conn)  # triangle written with N4 = 0
        distinct = (np.diff(np.sort(conn, axis=1), axis=1) != 0).sum(axis=1) + 1
        collapsed += int((distinct < (4 if width == 8 else 3)).sum())
    return {"merged": len(mapping), "groups": len(set(mapping.values())), "references_changed": cells,
            "max_distance": max((d for _, _, d in pairs), default=0.0), "collapsed_elements": collapsed}


def delete_elements(deck: KeywordDeck, keyword: str, element_ids: Iterable[int], *,
                    delete_orphan_nodes: bool = False) -> dict:
    """Delete element rows. Refused while sets or other keywords still refer to the elements.

    With ``delete_orphan_nodes`` the nodes used only by the deleted elements, and referred to by
    nothing else, are deleted too.
    """
    kind = ELEMENT_KINDS[keyword]
    wanted = {int(e) for e in element_ids}
    width = 8 if keyword == "*ELEMENT_SOLID" else 4
    eids, _, conn = elements(deck, keyword, width)
    missing = sorted(wanted - set(eids.tolist()))
    if missing:
        raise FieldError(f"{len(missing)} {keyword} IDs not found, e.g. {missing[:10]}")
    report = references.collect(deck, True, track={(kind, e) for e in wanted})
    used = [site for (role, _, _), sites in report.tracked.items() if role == "ref" for site in sites]
    if used:
        shown = "; ".join(f"{s.keyword}.{s.field} at {s.file}:{s.line}" for s in used[:20])
        raise FieldError(f"{len(used)} references to the elements remain: {shown}")
    removals = []
    for block in deck.iter_blocks():
        if block.name != keyword and not block.name.startswith(keyword + "_"):
            continue
        rows = deck.layout(block).rows
        drop = [i for key, indices in rows.lines() if key in wanted for i in indices]
        if drop:
            removals.append((block, drop))
    orphans: list[int] = []
    if delete_orphan_nodes:
        gone = np.isin(eids, list(wanted))
        candidates = set(np.unique(conn[gone]).tolist()) - set(np.unique(conn[~gone]).tolist()) - {0}
        for other, other_width in (("*ELEMENT_SOLID", 8), ("*ELEMENT_SHELL", 4)):
            if other != keyword:
                candidates -= set(np.unique(elements(deck, other, other_width)[2]).tolist())
        node_report = references.collect(deck, True, track={("node", n) for n in candidates})
        referenced = {ident for (role, k, ident), sites in node_report.tracked.items()
                      if role == "ref" and k == "node" and any(not s.keyword.startswith(keyword) for s in sites)}
        orphans = sorted(candidates - referenced)
    for block, drop in removals:
        deck.remove_lines(block, drop, f"delete {keyword}")
    if orphans:
        orphan_set = set(orphans)
        for block, rows in _node_rows(deck):
            drop = [i for key, indices in rows.lines() if key in orphan_set for i in indices]
            if drop:
                deck.remove_lines(block, drop, "delete orphan nodes")
    return {"deleted": len(wanted), "orphan_nodes_deleted": len(orphans)}


__all__ = ["delete_elements", "merge_duplicate_nodes", "renumber", "renumber_range"]
