"""ID definitions and cross references between keyword blocks (dangling / duplicate / unused IDs).

Rules are declarative: which keyword fields define an ID of a kind, and which fields refer
to one. Two passes keep large meshes cheap: pass 1 collects defined IDs (row keys of node /
element / part tables are taken as a whole), pass 2 reads references and stores a location
only for dangling references or for explicitly tracked IDs. Blocks whose fields cannot be
read are counted as unchecked, never treated as clean.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import links, lists
from .blocks import Block
from .fields import FieldError, parse_number, read_text
from .layouts import Layout, RowMap, Unsupported
from .parameters import field_expression, resolve_field

if TYPE_CHECKING:
    from .deck import KeywordDeck

# (keyword prefix, id field, kind). Longest matching prefix wins.
DEFINITIONS: list[tuple[str, str, str]] = [
    ("*PART", "pid", "part"), ("*CESE_PART", "pid", "part"),  # CESE meshes refer to CESE parts
    ("*SECTION_", "secid", "section"), ("*MAT_", "mid", "material"),
    ("*MAT_THERMAL_", "tmid", "thermal_material"), ("*EOS_", "eosid", "eos"), ("*HOURGLASS", "hgid", "hourglass"),
    ("*DEFINE_CURVE", "lcid", "curve"), ("*DEFINE_TABLE", "tbid", "curve"),
    ("*DEFINE_FUNCTION", "fid", "curve"),  # LS-DYNA accepts a function ID where a curve ID is expected
    ("*DEFINE_COORDINATE_", "cid", "coordinate"), ("*DEFINE_VECTOR", "vid", "vector"),
    ("*DEFINE_BOX", "boxid", "box"), ("*DEFINE_TRANSFORMATION", "tranid", "transformation"),
    ("*SET_DISCRETE", "sid", "discrete_set"),
    ("*SET_NODE", "sid", "node_set"), ("*SET_PART", "sid", "part_set"), ("*SET_SHELL", "sid", "shell_set"),
    ("*SET_SOLID", "sid", "solid_set"), ("*SET_BEAM", "sid", "beam_set"), ("*SET_SEGMENT", "sid", "segment_set"),
    ("*NODE", "nid", "node"), ("*ELEMENT_SHELL", "eid", "shell"), ("*ELEMENT_SOLID", "eid", "solid"),
    ("*ELEMENT_BEAM", "eid", "beam"),
]
NOT_DEFINITIONS = ("*MAT_ADD_",)  # *MAT_ADD_EROSION etc. refer to an existing material
_NODES8 = tuple((f"n{i}", "node") for i in range(1, 9))
# (keyword prefix, ((field, target kind), ...)). Longest matching prefix wins.
REFERENCES: list[tuple[str, tuple[tuple[str, str], ...]]] = [
    ("*PART", (("secid", "section"), ("mid", "material"), ("eosid", "eos"), ("hgid", "hourglass"),
               ("tmid", "thermal_material"))),
    ("*ELEMENT_SHELL", (("pid", "part"),) + _NODES8),
    ("*ELEMENT_SOLID", (("pid", "part"),) + _NODES8),
    ("*ELEMENT_BEAM", (("pid", "part"), ("n1", "node"), ("n2", "node"), ("n3", "node"))),
    ("*MAT_ADD_", (("mid", "material"),)),
    ("*DEFINE_TABLE", (("lcid", "curve"),)),  # builtin rows: VALUE, LCID
    ("*MAT_PIECEWISE_LINEAR_PLASTICITY", (("lcss", "curve"), ("lcsr", "curve"))),
    ("*BOUNDARY_SPC_SET", (("nsid", "node_set"),)), ("*BOUNDARY_SPC_NODE", (("nid", "node"),)),
    ("*BOUNDARY_PRESCRIBED_MOTION_SET", (("nsid", "node_set"), ("lcid", "curve"))),
    ("*BOUNDARY_PRESCRIBED_MOTION_NODE", (("nid", "node"), ("lcid", "curve"))),
    ("*BOUNDARY_PRESCRIBED_MOTION_RIGID", (("pid", "part"), ("lcid", "curve"))),
    ("*BOUNDARY_NON_REFLECTING", (("ssid", "segment_set"),)),
    ("*LOAD_SEGMENT_SET", (("ssid", "segment_set"), ("lcid", "curve"))),
    ("*LOAD_NODE_POINT", (("nid", "node"), ("lcid", "curve"))), ("*LOAD_NODE_SET", (("nsid", "node_set"), ("lcid", "curve"))),
    ("*LOAD_BODY_", (("lcid", "curve"),)),
    ("*INITIAL_VELOCITY", (("nsid", "node_set"),)), ("*INITIAL_VELOCITY_NODE", (("nid", "node"),)),
    ("*CONSTRAINED_NODAL_RIGID_BODY", (("nsid", "node_set"),)),
    ("*DATABASE_HISTORY_NODE", tuple((f"id{i}", "node") for i in range(1, 9))),
]
LIST_MEMBERS = {"*SET_NODE_LIST": "node", "*SET_PART_LIST": "part", "*SET_SHELL_LIST": "shell",
                "*SET_NODE": "node", "*SET_PART": "part", "*SET_SHELL": "shell", "*SET_BEAM": "beam",
                "*SET_SOLID": "solid", "*SET_SOLID_LIST": "solid", "*SET_BEAM_LIST": "beam",
                "*SET_NODE_ADD": "node_set", "*SET_PART_ADD": "part_set", "*SET_SHELL_ADD": "shell_set",
                "*SET_SOLID_ADD": "solid_set", "*SET_BEAM_ADD": "beam_set", "*SET_SEGMENT_ADD": "segment_set"}
# LS-DYNA contact surface type codes -> referenced kind (5 = all, no reference).
CONTACT_TYPES = {0: "segment_set", 1: "shell_set", 2: "part_set", 3: "part", 4: "node_set", 6: "part_set"}
MESH_KINDS = {"node", "shell", "solid", "beam"}
MAX_SITES = 10000


@dataclass
class Site:
    keyword: str
    file: str
    line: int
    field: str
    row: int | None = None


@dataclass
class ReferenceReport:
    defined: dict[str, set[int]] = field(default_factory=lambda: defaultdict(set))
    definition_sites: dict[str, dict[int, list[Site]]] = field(default_factory=lambda: defaultdict(dict))
    referenced: dict[str, set[int]] = field(default_factory=lambda: defaultdict(set))
    dangling_sites: list[tuple[str, int, Site]] = field(default_factory=list)
    dangling_count: int = 0
    tracked: dict[tuple[str, int], list[Site]] = field(default_factory=lambda: defaultdict(list))
    unchecked: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    # Kinds with a definition block that could not be read: their missing IDs are not proof of an error.
    unverified_kinds: set[str] = field(default_factory=set)
    unverified_sites: list[tuple[str, int, Site]] = field(default_factory=list)
    unverified_count: int = 0

    def dangling(self) -> list[dict]:
        """Dangling references (locations capped at ``MAX_SITES``; see ``dangling_count``)."""
        return [{"kind": kind, "id": ident, **vars(site)} for kind, ident, site in self.dangling_sites]

    def unverified(self) -> list[dict]:
        """References to IDs that may be defined in a block that could not be read."""
        return [{"kind": kind, "id": ident, **vars(site)} for kind, ident, site in self.unverified_sites]

    def duplicates(self) -> list[dict]:
        return [{"kind": kind, "id": ident, "sites": [vars(s) for s in sites]}
                for kind, defs in self.definition_sites.items() for ident, sites in defs.items() if len(sites) > 1]

    def unused(self, kinds: tuple[str, ...] = ("section", "material", "eos", "hourglass", "curve")) -> dict:
        return {kind: sorted(self.defined.get(kind, set()) - self.referenced.get(kind, set())) for kind in kinds}

    def summary(self) -> dict:
        return {"defined": {k: len(v) for k, v in self.defined.items() if v},
                "dangling": self.dangling_count, "duplicates": len(self.duplicates()),
                "unverified_dangling": self.unverified_count, "unverified_kinds": sorted(self.unverified_kinds),
                "unchecked_blocks": dict(self.unchecked)}


def _rule(name: str, rules: list) -> object | None:
    best, best_len = None, -1
    for prefix, *rest in rules:
        hit = name == prefix or name.startswith(prefix + "_") or (prefix.endswith("_") and name.startswith(prefix))
        if hit and len(prefix) > best_len:
            best, best_len = rest, len(prefix)
    return best


def _ident(text: str, lookup: dict) -> int | None:
    text = text.strip()
    if not text:
        return None
    if field_expression(text) is not None:
        try:
            value = resolve_field(text, lookup)
        except FieldError:
            return None
    else:
        try:
            value = int(text)
        except ValueError:
            try:
                value = parse_number(text)
            except FieldError:
                return None
    # LS-DYNA IDs have at most 10 digits; larger values are data read through misaligned cards.
    return int(value) if isinstance(value, (int, float)) and float(value).is_integer() and 0 < value < 10**10 else None


@dataclass
class _Plan:
    block: Block
    layout: Layout
    definition: tuple[str, str] | None
    refs: list[tuple[str, str]]
    contact: bool
    members: str | None


def _plans(deck: KeywordDeck, include_mesh: bool, report: ReferenceReport) -> list[_Plan]:
    plans = []
    for block in deck.iter_blocks():
        base = lists.base_name(block.name)[0]
        definition = None if base.startswith(NOT_DEFINITIONS) else _rule(base, DEFINITIONS)
        refs = _references(block.name, base, include_mesh)
        contact = base.startswith("*CONTACT_")
        members = LIST_MEMBERS.get(base)
        mesh = (definition and definition[1] in MESH_KINDS) or base.startswith("*ELEMENT_")
        if not (definition or refs or contact or members) or (mesh and not include_mesh):
            continue
        try:
            layout = deck.layout(block)
        except (Unsupported, FieldError):
            report.unchecked[block.name] += 1
            if definition:
                report.unverified_kinds.add(definition[1])
            continue
        if members and not include_mesh and members in MESH_KINDS:
            members = None
        plans.append(_Plan(block, layout, tuple(definition) if definition else None,
                           _expand(refs, layout), contact, members))
    return plans


def _references(name: str, base: str, include_mesh: bool) -> list[tuple[str, str]]:
    """Hand rules first, then PyDYNA link fields; mesh targets only when the mesh is scanned."""
    hand = _rule(base, REFERENCES)
    pairs = list(hand[0]) if hand else []
    named = {field for field, _ in pairs}
    pairs += [(field, kind) for field, kind in links.link_fields(name) if field not in named]
    return [(field, kind) for field, kind in pairs if include_mesh or kind not in MESH_KINDS]


def _expand(pairs: list[tuple[str, str]], layout: Layout) -> list[tuple[str, str]]:
    """Add layout fields that repeat a linked name with a suffix (``lcid_2``)."""
    if not pairs:
        return []
    names = {info.name for info in layout.fields}
    if isinstance(layout.rows, RowMap):
        names |= {column.name for columns in layout.rows.template for column in columns}
    else:
        names |= {info.name for infos in layout.rows.values() for info in infos}
    kinds = dict(pairs)
    extra = [(name, kinds[name.rsplit("_", 1)[0]]) for name in sorted(names)
             if "_" in name and name.rsplit("_", 1)[1].isdigit() and name.rsplit("_", 1)[0] in kinds
             and name not in kinds]
    return list(pairs) + extra


def _site(plan: _Plan, line_index: int, name: str, row: int | None) -> Site:
    return Site(plan.block.name, str(plan.block.file.path), plan.block.line_number + line_index, name, row)


def _define(report: ReferenceReport, kind: str, ident: int, site: object, track: set) -> None:
    """Record a definition; ``site`` is a Site or a zero-argument factory (built only when needed)."""
    seen = ident in report.defined[kind]
    report.defined[kind].add(ident)
    if kind not in MESH_KINDS or seen or (kind, ident) in track:
        made = site() if callable(site) else site
        if kind not in MESH_KINDS or seen:
            sites = report.definition_sites[kind].setdefault(ident, [])
            if seen and kind in MESH_KINDS and not sites:
                sites.append(Site("?", "", 0, "first definition (mesh, location not kept)"))
            sites.append(made)
        if (kind, ident) in track:
            report.tracked[("def", kind, ident)].append(made)


def _refer(report: ReferenceReport, kind: str, ident: int, site: object, track: set) -> None:
    report.referenced[kind].add(ident)
    dangling = ident not in report.defined.get(kind, ())
    if dangling or (kind, ident) in track:
        made = site() if callable(site) else site
        if dangling and kind in report.unverified_kinds:
            report.unverified_count += 1
            if len(report.unverified_sites) < MAX_SITES:
                report.unverified_sites.append((kind, ident, made))
        elif dangling:
            report.dangling_count += 1
            if len(report.dangling_sites) < MAX_SITES:
                report.dangling_sites.append((kind, ident, made))
        if (kind, ident) in track:
            report.tracked[("ref", kind, ident)].append(made)


def collect(deck: KeywordDeck, include_mesh: bool = True, track: set[tuple[str, int]] | None = None) -> ReferenceReport:
    """Scan all blocks. ``include_mesh=False`` skips node/element tables; ``track`` keeps locations."""
    report, track = ReferenceReport(), track or set()
    plans = _plans(deck, include_mesh, report)
    for plan in plans:  # pass 1: definitions
        if not plan.definition:
            continue
        name, kind = plan.definition
        rows, lookup = plan.layout.rows, deck.lookup(plan.block)
        if isinstance(rows, RowMap) and plan.layout.key == name:
            located = rows.locate(name)
            for key, indices in rows.lines():
                _define(report, kind, key, lambda i=indices, k=key: _site(plan, i[located[0]], name, k), track)
            continue
        for row, infos in ([(None, plan.layout.fields)] if plan.layout.fields else []) + list(plan.layout.rows.items()):
            for info in infos:
                if info.name == name:
                    ident = _ident(read_text(plan.block.lines[info.slot.line], info.slot), lookup)
                    if ident is not None:
                        _define(report, kind, ident, _site(plan, info.slot.line, name, row), track)
    for plan in plans:  # pass 2: references
        lookup = deck.lookup(plan.block)
        layout = plan.layout
        header = {info.name: info for info in layout.fields}
        pairs = list(plan.refs)
        if plan.contact:
            for side in ("a", "b"):
                code_info = header.get(f"surf{side}typ")
                code = _ident(read_text(plan.block.lines[code_info.slot.line], code_info.slot), lookup) if code_info else None
                target = CONTACT_TYPES.get(code or 0)
                if target and f"surf{side}" in header:
                    pairs.append((f"surf{side}", target))
        for name, target in pairs:
            if name in header:
                info = header[name]
                ident = _ident(read_text(plan.block.lines[info.slot.line], info.slot), lookup)
                if ident is not None:
                    _refer(report, target, ident, _site(plan, info.slot.line, name, None), track)
        if isinstance(layout.rows, RowMap):
            located = {name: layout.rows.locate(name) for name, _ in pairs}
            for key, indices in layout.rows.lines():
                for name, target in pairs:
                    spot = located.get(name)
                    if spot is None:
                        continue
                    ident = _ident(layout.rows.cell(indices, spot), lookup)
                    if ident is not None:
                        _refer(report, target, ident,
                               lambda i=indices, s=spot, n=name, k=key: _site(plan, i[s[0]], n, k), track)
        else:
            for row, infos in layout.rows.items():
                by_name = {info.name: info for info in infos}
                for name, target in pairs:
                    if name in by_name:
                        info = by_name[name]
                        ident = _ident(read_text(plan.block.lines[info.slot.line], info.slot), lookup)
                        if ident is not None:
                            _refer(report, target, ident, _site(plan, info.slot.line, name, row), track)
        if plan.members:
            try:
                members = deck.members(plan.block)
            except (FieldError, Unsupported):
                report.unchecked[plan.block.name] += 1
                members = []
            for ident in members:
                _refer(report, plan.members, ident, lambda: _site(plan, 0, "members", None), track)
    return report


def defined_by(deck: KeywordDeck, block: Block) -> list[tuple[str, int]]:
    """``(kind, id)`` pairs that ``block`` defines (used before deleting it)."""
    base = lists.base_name(block.name)[0]
    definition = None if base.startswith(NOT_DEFINITIONS) else _rule(base, DEFINITIONS)
    if not definition:
        return []
    name, kind = definition
    try:
        layout = deck.layout(block)
    except Unsupported:
        return []
    if isinstance(layout.rows, RowMap) and layout.key == name:
        return [(kind, key) for key in layout.rows]
    lookup = deck.lookup(block)
    found = []
    for _, infos in ([(None, layout.fields)] if layout.fields else []) + list(layout.rows.items()):
        for info in infos:
            if info.name == name:
                ident = _ident(read_text(block.lines[info.slot.line], info.slot), lookup)
                if ident is not None:
                    found.append((kind, ident))
    return found


class ReferencedError(FieldError):
    """A block cannot be deleted because IDs it defines are still referenced."""


def check_delete(deck: KeywordDeck, block: Block) -> None:
    """Raise :class:`ReferencedError` if deleting ``block`` would leave dangling references."""
    owned = defined_by(deck, block)
    if not owned:
        return
    track = set(owned)
    report = collect(deck, include_mesh=any(kind in MESH_KINDS for kind, _ in owned), track=track)
    inside = range(block.line_number, block.line_number + len(block.lines))
    problems = []
    for kind, ident in owned:
        others = [s for s in report.tracked.get(("def", kind, ident), [])
                  if not (s.file == str(block.file.path) and s.line in inside)]
        if others:
            continue  # another definition of the same ID remains
        for site in report.tracked.get(("ref", kind, ident), []):
            problems.append(f"{kind} {ident} used by {site.keyword}.{site.field} at {site.file}:{site.line}")
    if problems:
        shown = "; ".join(problems[:20]) + (f"; ... {len(problems) - 20} more" if len(problems) > 20 else "")
        raise ReferencedError(f"Deleting {block.name} leaves dangling references: {shown}")
