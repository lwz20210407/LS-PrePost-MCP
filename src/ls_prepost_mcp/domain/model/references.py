"""ID definitions and cross references between keyword blocks (dangling / duplicate / unused IDs).

Rules are declarative: which keyword fields define an ID of a kind, and which fields
refer to one. Blocks whose fields cannot be read (no layout) are counted as unchecked,
never silently treated as clean.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import lists
from .blocks import Block
from .fields import FieldError, parse_number, read_text
from .schema import Layout, Unsupported

if TYPE_CHECKING:
    from .deck import KeywordDeck

# (keyword prefix, id field, kind). Longest matching prefix wins.
DEFINITIONS: list[tuple[str, str, str]] = [
    ("*PART", "pid", "part"), ("*SECTION_", "secid", "section"), ("*MAT_", "mid", "material"),
    ("*MAT_THERMAL_", "tmid", "thermal_material"), ("*EOS_", "eosid", "eos"), ("*HOURGLASS", "hgid", "hourglass"),
    ("*DEFINE_CURVE", "lcid", "curve"), ("*DEFINE_TABLE", "tbid", "curve"),
    ("*DEFINE_COORDINATE_", "cid", "coordinate"), ("*DEFINE_VECTOR", "vid", "vector"),
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
                "*SET_SOLID": "solid", "*SET_SOLID_LIST": "solid", "*SET_BEAM_LIST": "beam"}
# LS-DYNA contact surface type codes -> referenced kind (5 = all, no reference).
CONTACT_TYPES = {0: "segment_set", 1: "shell_set", 2: "part_set", 3: "part", 4: "node_set", 6: "part_set"}
MESH_KINDS = {"node", "shell", "solid", "beam"}


@dataclass
class Site:
    keyword: str
    file: str
    line: int
    field: str
    row: int | None = None


@dataclass
class ReferenceReport:
    definitions: dict[str, dict[int, list[Site]]] = field(default_factory=lambda: defaultdict(dict))
    references: dict[str, dict[int, list[Site]]] = field(default_factory=lambda: defaultdict(dict))
    unchecked: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def dangling(self) -> list[dict]:
        return [{"kind": kind, "id": ident, **vars(site)}
                for kind, refs in self.references.items() for ident, sites in refs.items()
                if ident not in self.definitions.get(kind, {}) for site in sites]

    def duplicates(self) -> list[dict]:
        return [{"kind": kind, "id": ident, "sites": [vars(s) for s in sites]}
                for kind, defs in self.definitions.items() for ident, sites in defs.items() if len(sites) > 1]

    def unused(self, kinds: tuple[str, ...] = ("section", "material", "eos", "hourglass", "curve")) -> dict:
        return {kind: sorted(set(self.definitions.get(kind, {})) - set(self.references.get(kind, {})))
                for kind in kinds}

    def summary(self) -> dict:
        return {"defined": {k: len(v) for k, v in self.definitions.items()},
                "dangling": len(self.dangling()), "duplicates": len(self.duplicates()),
                "unchecked_blocks": dict(self.unchecked)}


def _rule(name: str, rules: list) -> object | None:
    best, best_len = None, -1
    for prefix, *rest in rules:
        hit = name == prefix or name.startswith(prefix + "_") or (prefix.endswith("_") and name.startswith(prefix))
        if hit and len(prefix) > best_len:
            best, best_len = rest, len(prefix)
    return best


def _int(block: Block, info: object, lookup: dict) -> int | None:
    text = read_text(block.lines[info.slot.line], info.slot).strip()
    if text.startswith("&") or text.startswith("-&"):
        value = lookup.get(text.lstrip("-&").lower())
    else:
        try:
            value = parse_number(text)
        except FieldError:
            return None
    return int(value) if isinstance(value, (int, float)) and float(value).is_integer() and value > 0 else None


def _site(block: Block, info: object, row: int | None) -> Site:
    return Site(block.name, str(block.file.path), block.line_number + info.slot.line, info.name, row)


def collect(deck: KeywordDeck, include_mesh: bool = True) -> ReferenceReport:
    """Scan all blocks in reading order. ``include_mesh=False`` skips node/element tables."""
    report = ReferenceReport()
    for block in deck.iter_blocks():
        base = lists.base_name(block.name)[0]
        definition = None if base.startswith(NOT_DEFINITIONS) else _rule(base, DEFINITIONS)
        refs = _rule(base, REFERENCES)
        contact = base.startswith("*CONTACT_")
        members_kind = LIST_MEMBERS.get(base)
        mesh = (definition and definition[1] in MESH_KINDS) or base.startswith("*ELEMENT_")
        if not (definition or refs or contact or members_kind) or (mesh and not include_mesh):
            continue
        try:
            layout: Layout = deck.layout(block)
        except Unsupported:
            report.unchecked[block.name] += 1
            continue
        lookup = deck.lookup(block)
        groups = ([(None, layout.fields)] if layout.fields else []) + list(layout.rows.items())
        for row, infos in groups:
            by_name = {info.name: info for info in infos}
            if definition and definition[0] in by_name:
                ident = _int(block, by_name[definition[0]], lookup)
                if ident is not None:
                    report.definitions[definition[1]].setdefault(ident, []).append(_site(block, by_name[definition[0]], row))
            pairs = list(refs[0]) if refs else []
            if contact:
                for side in ("a", "b"):
                    kind_info = by_name.get(f"surf{side}typ")
                    code = _int(block, kind_info, lookup) if kind_info else None
                    target = CONTACT_TYPES.get(code or 0)
                    if target and f"surf{side}" in by_name:
                        pairs.append((f"surf{side}", target))
            for name, target in pairs:
                if name in by_name:
                    ident = _int(block, by_name[name], lookup)
                    if ident is not None:
                        report.references[target].setdefault(ident, []).append(_site(block, by_name[name], row))
        if members_kind and (include_mesh or members_kind == "part"):
            for ident in deck.members(block):
                site = Site(block.name, str(block.file.path), block.line_number, "members")
                report.references[members_kind].setdefault(ident, []).append(site)
    return report


def defined_by(deck: KeywordDeck, block: Block) -> list[tuple[str, int]]:
    """``(kind, id)`` pairs that ``block`` defines (used before deleting it)."""
    base = lists.base_name(block.name)[0]
    definition = None if base.startswith(NOT_DEFINITIONS) else _rule(base, DEFINITIONS)
    if not definition:
        return []
    try:
        layout = deck.layout(block)
    except Unsupported:
        return []
    lookup = deck.lookup(block)
    found = []
    for _, infos in ([(None, layout.fields)] if layout.fields else []) + list(layout.rows.items()):
        for info in infos:
            if info.name == definition[0]:
                ident = _int(block, info, lookup)
                if ident is not None:
                    found.append((definition[1], ident))
    return found


class ReferencedError(FieldError):
    """A block cannot be deleted because IDs it defines are still referenced."""


def check_delete(deck: KeywordDeck, block: Block) -> None:
    """Raise :class:`ReferencedError` if deleting ``block`` would leave dangling references."""
    owned = defined_by(deck, block)
    if not owned:
        return
    report = collect(deck, include_mesh=any(kind in MESH_KINDS for kind, _ in owned))
    problems = []
    for kind, ident in owned:
        others = [s for s in report.definitions.get(kind, {}).get(ident, [])
                  if not (s.file == str(block.file.path) and s.keyword == block.name
                          and block.line_number <= s.line < block.line_number + len(block.lines))]
        if others:
            continue  # another definition of the same ID remains
        for site in report.references.get(kind, {}).get(ident, []):
            problems.append(f"{kind} {ident} used by {site.keyword}.{site.field} at {site.file}:{site.line}")
    if problems:
        shown = "; ".join(problems[:20]) + (f"; ... {len(problems) - 20} more" if len(problems) > 20 else "")
        raise ReferencedError(f"Deleting {block.name} leaves dangling references: {shown}")
