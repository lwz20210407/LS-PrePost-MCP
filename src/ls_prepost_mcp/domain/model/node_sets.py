"""Node-set definitions resolved through the existing AST, never a second text parser.

R11 Vol I 39-22: plain GENERATE takes defined nodes inside its limits, including
numbering gaps. Increment ranges with holes remain unverified and fail explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from . import lists
from .fields import FieldError, format_value, single_line
from .layouts import Unsupported

if TYPE_CHECKING:
    from .blocks import Block
    from .deck import KeywordDeck

LIST = {"*SET_NODE", "*SET_NODE_LIST"}
GENERATE = "*SET_NODE_LIST_GENERATE"
INCREMENT = "*SET_NODE_LIST_GENERATE_INCREMENT"
ADD = "*SET_NODE_ADD"
SUPPORTED = LIST | {GENERATE, INCREMENT, ADD}


def integer(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise FieldError(f"{name} must be an integer")
    value = int(value)
    if positive and value <= 0:
        raise FieldError(f"{name} must be positive")
    return value


def is_node_set(name):
    return name == "*SET_NODE" or name.startswith("*SET_NODE_")


@dataclass(frozen=True)
class Definition:
    sid: int
    kind: str
    block: Block
    operands: tuple[int, ...] = ()
    ranges: tuple[tuple[int, int, int], ...] = ()


def range_rows(deck: KeywordDeck, block: Block):
    base, _ = lists.base_name(block.name)
    if base == GENERATE:
        pairs = lists.ranges(block, deck._long(block))
        triples = [(first, last, 1) for first, last in pairs]
    elif base == INCREMENT:
        triples = [tuple(deck.get(block, name, row=row).value for name in ("bbeg", "bend", "incr"))
                   for row in deck.layout(block).rows]
    else:
        raise Unsupported(f"{block.name} is not a supported node generation definition")
    result = []
    for first, last, step in triples:
        first, last, step = (integer(value, name) for value, name in (
            (first, "range begin"), (last, "range end"), (step, "range increment")))
        if step <= 0:
            raise FieldError("Node generation increment must be positive; reverse/zero increments are not supported")
        if first > last:
            raise Unsupported("Descending node generation ranges have not been verified")
        result.append((first, last, step))
    return tuple(result)


class NodeSets:
    """One transaction/request index; no cache survives a deck edit."""

    def __init__(self, deck: KeywordDeck, *, max_work=10_000_000, max_definitions=100_000,
                 allow_collect_lists=False):
        self.deck = deck
        self.max_work = max_work
        self.max_definitions = max_definitions
        self.allow_collect_lists = allow_collect_lists
        self.blocks = {}
        self.unknown = []
        self.definitions = {}
        self._ids = None
        for block in deck.iter_blocks():
            if not is_node_set(block.name):
                continue
            try:
                sid = integer(deck.get(block, "sid").value, "Node set SID", positive=True)
            except (FieldError, Unsupported, KeyError, ValueError) as error:
                self.unknown.append((block.name, str(error)))
                continue
            self.blocks.setdefault(sid, []).append(block)
            if len(self.blocks) > max_definitions:
                raise FieldError("Node-set definition budget exceeded")

    @property
    def ids(self):
        if self._ids is None:
            if any(block.name in {"*INCLUDE_TRANSFORM", "*INCLUDE_AUTO_OFFSET"} for block in self.deck.iter_blocks()):
                raise Unsupported("Node-set ID resolution for transformed/offset Includes has not been verified")
            values = []
            for block in self.deck.blocks("*NODE"):
                layout = self.deck.layout(block)
                if layout.key != "nid":
                    raise Unsupported(f"{block.name} does not expose a shared node-ID row map")
                values.extend(layout.rows)
            values = np.asarray(values, dtype=np.int64)
            if values.size != np.unique(values).size or np.any(values <= 0):
                raise FieldError("Node-set resolution requires unique positive model node IDs")
            self._ids = np.sort(values)
        return self._ids

    def definition(self, sid):
        sid = integer(sid, "Node set SID", positive=True)
        if self.unknown:
            raise Unsupported("An unreadable node-set SID prevents unambiguous resolution")
        if sid in self.definitions:
            return self.definitions[sid]
        found = self.blocks.get(sid, [])
        if not found:
            raise FieldError(f"Node set {sid} is not defined")
        collected_lists = self.allow_collect_lists and all(
            lists.collected(block.name) and lists.base_name(block.name)[0] in LIST for block in found)
        if collected_lists:
            operands = tuple(integer(value, "Node-list member", positive=True)
                             for block in found for value in self.deck.members(block))
            result = Definition(sid, "list", found[0], operands=operands)
            self.definitions[sid] = result
            return result
        if len(found) != 1:
            raise FieldError(f"Node set {sid} has duplicate/multiple definitions that are not all _COLLECT list blocks")
        block = found[0]
        base, _ = lists.base_name(block.name)
        if lists.collected(block.name) or base not in SUPPORTED:
            raise Unsupported(f"{block.name} is not supported by the node-set resolver")
        if base in {GENERATE, INCREMENT}:
            result = Definition(sid, base, block, ranges=range_rows(self.deck, block))
        else:
            operands = tuple(integer(value, "Node-set operand", positive=True) for value in self.deck.members(block))
            result = Definition(sid, "list" if base in LIST else ADD, block, operands=operands)
        self.definitions[sid] = result
        return result

    def leaves(self, sid):
        """Iterative DFS: detect cycles and visit each shared leaf once, without ID expansion."""
        pending, state, path, positions, leaves = [(sid, False)], {}, [], {}, []
        edges = 0
        while pending:
            current, leaving = pending.pop()
            if leaving:
                state[current] = 2
                positions.pop(current, None)
                path.pop()
                continue
            if state.get(current) == 2:
                continue
            if state.get(current) == 1:
                cycle = path[positions[current]:] + [current]
                raise FieldError("Node-set ADD cycle: " + " -> ".join(map(str, cycle[:30])))
            definition = self.definition(current)
            state[current] = 1
            positions[current] = len(path)
            path.append(current)
            pending.append((current, True))
            if definition.kind == ADD:
                edges += len(definition.operands)
                if edges > self.max_definitions:
                    raise FieldError("Node-set ADD edge budget exceeded")
                pending.extend((child, False) for child in reversed(definition.operands))
            else:
                leaves.append(definition)
        return leaves

    def add_cycles(self):
        """Only ADD edges are known here; GENERAL/COLLECT semantics are not inferred."""
        if self.unknown:
            raise Unsupported("Unreadable node-set IDs prevent complete ADD graph validation")
        graph = {}
        for sid, blocks in self.blocks.items():
            if len(blocks) == 1 and lists.base_name(blocks[0].name)[0] == ADD and not lists.collected(blocks[0].name):
                graph[sid] = tuple(integer(value, "Child node-set SID", positive=True)
                                   for value in self.deck.members(blocks[0]))
        if sum(map(len, graph.values())) > self.max_definitions:
            raise FieldError("Node-set ADD edge budget exceeded")
        state, cycles = {}, []
        for root in graph:
            if state.get(root) == 2:
                continue
            pending, path, positions = [(root, False)], [], {}
            while pending:
                sid, leaving = pending.pop()
                if leaving:
                    state[sid] = 2
                    positions.pop(sid, None)
                    path.pop()
                    continue
                if state.get(sid) == 2:
                    continue
                if state.get(sid) == 1:
                    cycles.append(path[positions[sid]:] + [sid])
                    continue
                state[sid] = 1
                positions[sid] = len(path)
                path.append(sid)
                pending.append((sid, True))
                pending.extend((child, False) for child in reversed(graph.get(sid, ())))
        return cycles

    def resolve(self, sid, *, check_nodes=True):
        """First-seen unique order; Selector performs its existing sorted-unique projection."""
        selected, seen, work = [], set(), 0
        leaves = self.leaves(sid)
        universe = None
        for definition in leaves:
            if definition.kind == "list":
                values = np.asarray(definition.operands, dtype=np.int64)
                if check_nodes and values.size:
                    universe = self.ids
                    missing = values[~np.isin(values, universe)]
                    if missing.size:
                        raise FieldError(f"Node set {definition.sid} references missing nodes {missing[:10].tolist()}")
                groups = [values]
            else:
                universe = self.ids
                groups = []
                for first, last, step in definition.ranges:
                    low = np.searchsorted(universe, first, side="left")
                    high = np.searchsorted(universe, last, side="right")
                    values = universe[low:high]
                    work += values.size
                    if work > self.max_work:
                        raise FieldError("Node-set membership work budget exceeded")
                    values = values[(values - first) % step == 0]
                    if definition.kind == INCREMENT and values.size != (last-first)//step+1:
                        raise Unsupported("Sparse GENERATE_INCREMENT semantics need an independent native check")
                    groups.append(values)
            for group in groups:
                work += len(group)
                if work > self.max_work:
                    raise FieldError("Node-set membership work budget exceeded")
                for value in group:
                    value = int(value)
                    if value not in seen:
                        seen.add(value)
                        selected.append(value)
        return selected


def resolve_many(deck, sids):
    resolver = NodeSets(deck)
    return {sid: resolver.resolve(sid) for sid in sids}


def allocate_sid(deck, requested=None):
    index = NodeSets(deck)
    if index.unknown:
        raise Unsupported("Unreadable node-set SIDs prevent collision-safe creation")
    sid = max(index.blocks, default=0) + 1 if requested is None else integer(requested, "Node set SID", positive=True)
    if sid in index.blocks:
        raise FieldError(f"node_set {sid} already exists")
    return sid


def create_compact(deck, representation, *, ranges=None, set_ids=None, sid=None, title=None, file=None):
    """Insert one supported compact definition, then verify through the same AST interface."""
    if representation not in ("generate", "generate_increment", "add"):
        raise FieldError("Unknown node-set representation")
    sid = allocate_sid(deck, sid)
    target = file or deck.main
    if deck.format == "i10":
        raise Unsupported("Named compact-set creation in i10 format is not verified")
    width = 20 if deck.format == "long" else 10
    rows, expected = [], None
    if representation == "add":
        if ranges is not None or not isinstance(set_ids, list) or not set_ids:
            raise FieldError("ADD needs a nonempty set_ids list, not node IDs or ranges")
        expected = tuple(integer(value, "Child node-set SID", positive=True) for value in set_ids)
        if len(set(expected)) != len(expected):
            raise FieldError("ADD child node-set SIDs must be unique")
        existing = NodeSets(deck)
        for child in expected:
            existing.leaves(child)
        keyword = ADD
        rows = [expected[n:n+8] for n in range(0, len(expected), 8)]
    else:
        if set_ids is not None or not isinstance(ranges, list) or not ranges:
            raise FieldError("Generated node sets need nonempty ranges, not set_ids")
        parsed = []
        for item in ranges:
            if representation == "generate":
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    raise FieldError("GENERATE ranges must be [begin,end] pairs")
                first, last = (integer(value, "Range limit") for value in item)
                step = 1
            else:
                if not isinstance(item, dict) or set(item) != {"begin", "end", "increment"}:
                    raise FieldError("Increment ranges need begin, end and increment")
                first, last, step = (integer(item[key], key) for key in ("begin", "end", "increment"))
            if first > last:
                raise Unsupported("Descending node-generation ranges are not verified")
            if step <= 0:
                raise FieldError("Node generation increment must be positive")
            parsed.append((first, last, step))
        expected = tuple(parsed)
        keyword = GENERATE if representation == "generate" else INCREMENT
        if representation == "generate":
            values = [value for first, last, _ in parsed for value in (first, last)]
            rows = [values[n:n+8] for n in range(0, len(values), 8)]
        else:
            rows = parsed
    def line(values):
        return "".join(format_value(value, width, "int")[0].rjust(width) for value in values)
    heading = [keyword + ("_TITLE" if title else "")]
    if title:
        heading.append(single_line(target.to_text(title), "Set title"))
    text = "\n".join([*heading, line([sid]), *[line(values) for values in rows]]) + "\n"
    blocks = deck.insert(text, file=target)
    try:
        index = NodeSets(deck)
        definition = index.definition(sid)
        observed = definition.operands if representation == "add" else definition.ranges
        if observed != expected:
            raise FieldError("New node-set definition failed AST read-back verification")
        members = index.resolve(sid)
        if not members:
            raise FieldError("The definition selects no model nodes; no set created")
    except (FieldError, Unsupported, KeyError, ValueError):
        deck.delete(blocks[0], force=True)
        raise
    return sid, blocks, len(members)
