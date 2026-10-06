"""Rigid bodies and *CONSTRAINED_JOINT consistency checks (tasks.yaml P12, part of P09).

Rigid bodies come from four sources: the elements of rigid parts (*MAT_RIGID / *MAT_020),
*CONSTRAINED_EXTRA_NODES_SET / _NODE, *CONSTRAINED_NODAL_RIGID_BODY node sets (the "spider" that
attaches joint nodes to a deformable part) and *CONSTRAINED_RIGID_BODIES merges. A block that cannot
be read makes the ownership it would have defined unverified; it never turns into an error.

Joint rules (R17 Vol I *CONSTRAINED_JOINT and Figures 10-16 to 10-24): odd nodes on rigid body A,
even nodes on rigid body B; node pairs (1,2), (3,4), (5,6) coincide initially (universal: 1-3 and
2-4 perpendicular instead of 3 = 4). The solver warns beyond 1e-4 x |N1N3|; here that is a warning
and 1e-2 x |N1N3| an error (the joint would snap the bodies together at the first step).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from .deck import KeywordDeck
from .fields import FieldError, parse_number
from .geometry import _number, nodes
from .layouts import RowMap, Unsupported
from .text import body as line_text
from .text import is_comment

Body = tuple[str, int]  # ("part", pid) or ("cnrb", pid)

# kind -> (required nodes, coincident pairs, constrained relative DOF or None for drivers)
RULES: dict[str, tuple[tuple[int, ...], tuple[tuple[int, int], ...], int | None]] = {
    "SPHERICAL": ((1, 2), ((1, 2),), 3),
    "REVOLUTE": ((1, 2, 3, 4), ((1, 2), (3, 4)), 5),
    "CYLINDRICAL": ((1, 2, 3, 4), ((1, 2), (3, 4)), 4),
    "PLANAR": ((1, 2, 3, 4), ((1, 2), (3, 4)), 3),
    "UNIVERSAL": ((1, 2, 3, 4), ((1, 2),), 4),
    "TRANSLATIONAL": ((1, 2, 3, 4, 5, 6), ((1, 2), (3, 4), (5, 6)), 5),
    "LOCKING": ((1, 2, 3, 4, 5, 6), ((1, 2), (3, 4), (5, 6)), 6),
    "ROTATIONAL_MOTOR": ((1, 2, 3, 4, 5, 6), ((1, 2), (3, 4), (5, 6)), None),
    "TRANSLATIONAL_MOTOR": ((1, 2, 3), ((1, 2),), None),
}
FREE = {
    "SPHERICAL": ("rotation about x", "rotation about y", "rotation about z"),
    "REVOLUTE": ("rotation about the N1-N3 axis",),
    "CYLINDRICAL": ("rotation about the N1-N3 axis", "translation along it"),
    "PLANAR": ("translation in the plane normal to N1-N3 (2)", "rotation about N1-N3"),
    "UNIVERSAL": ("rotation about N1-N3", "rotation about N2-N4"),
    "TRANSLATIONAL": ("translation along the N1-N3 axis",),
    "LOCKING": (),
    "ROTATIONAL_MOTOR": ("drives rotation about N1-N3 (use with a revolute or cylindrical joint)",),
    "TRANSLATIONAL_MOTOR": ("drives N1 - N2 along N2-N3 (use with a translational or cylindrical joint)",),
}
NOT_JOINTS = ("STIFFNESS", "COOR", "USER_FORCE")
# *PART_* keywords that are not part definitions (no PID / MID pair to read)
PART_WITHOUT_MID = ("*PART_ANNEAL", "*PART_MOVE", "*PART_SENSOR", "*PART_ADAPTIVE_FAILURE", "*PART_DUPLICATE",
                    "*PART_MODES", "*PART_STACKED_ELEMENTS")
UNIVERSAL_WARN, UNIVERSAL_ERROR = 1e-3, 5e-2  # |cos| of the angle between N1-N3 and N2-N4
OPTIONS = {"ID", "FAILURE", "LOCAL"}
WARN, ERROR = 1e-4, 1e-2


def joint_kind(name: str) -> str | None:
    """``REVOLUTE`` for ``*CONSTRAINED_JOINT_REVOLUTE_ID_FAILURE``; None for stiffness and other blocks."""
    if not name.startswith("*CONSTRAINED_JOINT_"):
        return None
    rest = name[len("*CONSTRAINED_JOINT_"):]
    if rest.startswith(NOT_JOINTS):
        return None
    tokens = rest.split("_")
    while tokens and tokens[-1] in OPTIONS:
        tokens.pop()
    return "_".join(tokens)


@dataclass
class RigidBodies:
    owner: dict[int, set[Body]] = field(default_factory=dict)
    rigid_parts: set[int] = field(default_factory=set)
    parts: set[int] = field(default_factory=set)  # every part defined in the deck
    element_parts: set[int] = field(default_factory=set)  # every part an element refers to
    merged: set[int] = field(default_factory=set)  # parts merged into another by *CONSTRAINED_RIGID_BODIES
    unverified: list[str] = field(default_factory=list)

    def of(self, node: int) -> set[Body]:
        return self.owner.get(node, set())


def _rows(deck: KeywordDeck, block: object) -> list[dict]:
    layout = deck.layout(block)
    keys = list(layout.rows) if layout.key else [None]
    return [{f.name: f.value for f in deck.fields(block, key)} for key in keys]


def _set_members(deck: KeywordDeck, sets: dict[int, object], sid: int) -> list[int]:
    block = sets.get(int(sid))
    if block is None:
        raise FieldError(f"node set {sid} is not defined as a list set")
    return deck.members(block)


def _element_nodes(deck: KeywordDeck, parts: set[int], found: RigidBodies) -> dict[int, set[int]]:
    """Node IDs of the elements of ``parts`` from every *ELEMENT_* table that can be read."""
    result: dict[int, set[int]] = {pid: set() for pid in parts}
    for block in deck.iter_blocks():
        if not block.name.startswith("*ELEMENT_"):
            continue
        try:
            rows = deck.layout(block).rows
            if not isinstance(rows, RowMap):
                continue
            names = [c.name for columns in rows.template for c in columns]
            columns = [n for n in names if re.fullmatch(r"n\d+", n)]
            if "pid" not in names or not columns:
                continue
            spots = [rows.locate("pid")] + [rows.locate(n) for n in columns]
            lookup = deck.lookup(block)
            for _, indices in rows.lines():
                values = [int(_number(rows.cell(indices, s), lookup)) for s in spots]
                found.element_parts.add(values[0])
                if values[0] in result:
                    result[values[0]].update(n for n in values[1:] if n > 0)
        except (Unsupported, FieldError, KeyError, ValueError) as error:
            found.unverified.append(f"{block.name} ({block.file.path.name}:{block.line_number}): {error}")
    return result


def node_set_blocks(deck: KeywordDeck, unread: list[str] | None = None) -> dict[int, object]:
    """sid -> block of every *SET_NODE list set (_ADD / _GENERATE / _INTERSECT / _GENERAL are not lists)."""
    found, merged = {}, set()
    for block in deck.iter_blocks():
        if block.name.startswith("*SET_NODE") and not any(
                t in block.name for t in ("_ADD", "_GENERATE", "_INTERSECT", "_GENERAL")):
            try:
                sid = int(deck.get(block, "sid").value)
            except (Unsupported, FieldError, KeyError, ValueError):
                if unread is not None:
                    unread.append(f"{block.name} ({block.file.path.name}:{block.line_number})")
                continue
            if sid in found or sid in merged:  # _COLLECT: one set spread over several blocks
                found.pop(sid, None)
                if sid not in merged and unread is not None:
                    unread.append(f"*SET_NODE {sid}: defined by several blocks (_COLLECT or a duplicate SID); "
                                  "members not merged")
                merged.add(sid)
            else:
                found[sid] = block
        elif block.name.startswith("*SET_NODE") and unread is not None:
            unread.append(f"{block.name} ({block.file.path.name}:{block.line_number}): not a member list")
    return found


def rigid_bodies(deck: KeywordDeck) -> RigidBodies:
    found = RigidBodies()
    sets = node_set_blocks(deck, found.unverified)
    rigid_mids = set()
    for block in deck.iter_blocks():
        if block.name.startswith(("*MAT_RIGID", "*MAT_020")) and not block.name.startswith("*MAT_RIGID_DISCRETE"):
            try:
                rigid_mids.add(int(deck.get(block, "mid").value))
            except (Unsupported, FieldError, KeyError, ValueError):
                found.unverified.append(f"{block.name} ({block.file.path.name}:{block.line_number})")
    for block in deck.iter_blocks():  # *PART, *PART_INERTIA, *PART_CONTACT, ... (all carry PID and MID)
        if not block.name.startswith("*PART") or block.name.startswith(PART_WITHOUT_MID):
            continue
        try:
            for row in _rows(deck, block):
                if row.get("pid") is not None:
                    found.parts.add(int(row["pid"]))
                if row.get("mid") is not None and int(row["mid"]) in rigid_mids:
                    found.rigid_parts.add(int(row["pid"]))
        except (Unsupported, FieldError, KeyError, ValueError):
            found.unverified.append(f"{block.name} ({block.file.path.name}:{block.line_number})")
    members: dict[Body, set[int]] = {("part", p): n for p, n in _element_nodes(deck, found.rigid_parts, found).items()}
    undefined = sorted(found.element_parts - found.parts)
    if undefined:  # an include fragment: the parts (and whether they are rigid) are defined elsewhere
        found.unverified.append(f"elements refer to parts not defined in this deck: {undefined[:10]}")
    leader: dict[Body, Body] = {}
    for block in deck.iter_blocks():
        name = block.name
        try:
            if name.startswith("*CONSTRAINED_NODAL_RIGID_BODY"):
                for row in _rows(deck, block):
                    members[("cnrb", int(row["pid"]))] = set(_set_members(deck, sets, row["nsid"]))
            elif name.startswith("*CONSTRAINED_EXTRA_NODES_SET"):
                for row in _rows(deck, block):
                    members.setdefault(("part", int(row["pid"])), set()).update(_set_members(deck, sets, row["nsid"]))
            elif name.startswith("*CONSTRAINED_EXTRA_NODES_NODE"):
                for row in _rows(deck, block):
                    members.setdefault(("part", int(row["pid"])), set()).add(int(row["nid"]))
            elif name.startswith("*CONSTRAINED_RIGID_BODIES"):
                for row in _rows(deck, block):
                    if row.get("pidc") and row.get("pidl"):  # blank rows pad the table
                        leader[("part", int(row["pidc"]))] = ("part", int(row["pidl"]))
                        found.merged.add(int(row["pidc"]))
        except (Unsupported, FieldError, KeyError, ValueError, TypeError) as error:
            found.unverified.append(f"{name} ({block.file.path.name}:{block.line_number}): {error}")

    def lead(body: Body) -> Body:
        seen = set()
        while body in leader and body not in seen:
            seen.add(body)
            body = leader[body]
        return body

    for body, ids in members.items():
        for node in ids:
            found.owner.setdefault(int(node), set()).add(lead(body))
    return found


def _int(text: str) -> int:
    value = parse_number(text)
    return int(value) if value else 0


def _instances(deck: KeywordDeck, block: object) -> list[tuple[dict, dict]]:
    """(site, {n1..n6}) per joint in ``block``; one keyword may hold several joints (repeated cards)."""
    site = {"keyword": block.name, "file": str(block.file.path), "line": block.line_number}
    try:
        n = {i: int(deck.get(block, f"n{i}").value or 0) for i in range(1, 7)}
        if "_ID" in block.name:
            site["jid"] = deck.get(block, "jid").value
        return [(site, n)]
    except (Unsupported, FieldError, KeyError, ValueError):
        pass
    data = [(index, line_text(line)) for index, line in enumerate(block.lines[1:], 1)
            if line_text(line).strip() and not is_comment(line)]
    per = 1 + ("_ID" in block.name) + block.name.endswith("MOTOR") + ("_LOCAL" in block.name) \
        + 2 * ("_FAILURE" in block.name)
    if not data or len(data) % per:
        raise FieldError(f"{len(data)} data lines do not split into joints of {per} cards")
    found = []
    for start in range(0, len(data), per):
        chunk = data[start:start + per]
        card = chunk[1 if "_ID" in block.name else 0][1]
        fields = card.split(",") if "," in card else [card[k:k + 10] for k in range(0, 60, 10)]
        n = {i: _int(fields[i - 1]) if i - 1 < len(fields) else 0 for i in range(1, 7)}
        here = {**site, "line": block.line_number + chunk[0][0]}
        if "_ID" in block.name:
            here["jid"] = _int(chunk[0][1][:10])
        found.append((here, n))
    return found


def check_joints(deck: KeywordDeck) -> dict:
    """Findings for every node-based *CONSTRAINED_JOINT: errors, warnings, unverified and a summary."""
    bodies = rigid_bodies(deck)
    skipped: list[str] = []  # unreadable *NODE blocks: their nodes count as undefined (joints unverified)
    ids, xyz = nodes(deck, skipped)
    position = dict(zip(ids.tolist(), xyz))
    size = float(np.linalg.norm(xyz.max(axis=0) - xyz.min(axis=0))) if len(xyz) else 1.0
    out: dict = {"joints": [], "errors": [], "warnings": [], "unverified": [{"reason": f"node block not read: {s}"}
                                                                            for s in skipped], "not_checked": []}
    pairs: dict[frozenset, list[tuple[str, np.ndarray | None, dict]]] = {}
    lagrange = uses_lagrange(deck)
    for block in deck.iter_blocks():
        kind = joint_kind(block.name)
        if kind is None:
            continue
        if kind not in RULES:
            out["not_checked"].append({"keyword": block.name, "file": str(block.file.path), "line": block.line_number,
                                       "reason": f"{kind} joints are not checked geometrically"})
            continue
        try:
            instances = _instances(deck, block)
        except (Unsupported, FieldError, KeyError, ValueError) as error:
            out["unverified"].append({"keyword": block.name, "file": str(block.file.path), "line": block.line_number,
                                      "reason": str(error)})
            continue
        for site, n in instances:
            _check_one(kind, site, n, bodies, position, size, out, pairs)
            if kind == "ROTATIONAL_MOTOR" and not lagrange:
                out["warnings"].append({**site, "kind": "motor_penalty_lag", "message": MOTOR_LAG})
    out["warnings"] += _overconstrained(pairs, position)
    out["unverified"] += [{"reason": f"rigid-body ownership not read: {item}"} for item in bodies.unverified[:20]]
    return out


# R11 2026-10-06 (P12 validation, revolute + rotational motor at 2 pi rad/s from rest, 0.5 s):
# default penalty RPS=1 turned 1.73 rad of pi, RPS=100 3.00 rad, *CONTROL_RIGID LMF=1 3.14147 rad.
MOTOR_LAG = ("rotational motor with the penalty formulation (*CONTROL_RIGID LMF=0): it lags the prescribed motion "
             "(R11 test: 45% short after 0.5 s at RPS=1, 5% at RPS=100); LMF=1 followed it within 1e-4")


def uses_lagrange(deck: KeywordDeck) -> bool:
    for block in deck.iter_blocks():
        if block.name == "*CONTROL_RIGID":
            try:
                return int(deck.get(block, "lmf").value or 0) == 1
            except (Unsupported, FieldError, KeyError, ValueError):
                return False
    return False


def _check_one(kind: str, site: dict, n: dict, bodies: RigidBodies, position: dict, size: float, out: dict,
               pairs: dict) -> None:
    required, coincident, dof = RULES[kind]
    if kind == "CYLINDRICAL" and n[3] == 0:  # node 1 may sit on a deformable body (R17 remark)
        required, coincident = (1, 2, 4), ()
    problems = _geometry(kind, n, required, coincident, position, size, site)
    for level, finding in problems:
        out[level].append(finding)
    if any(level in ("errors", "unverified") for level, _ in problems):
        return
    a_nodes = [n[i] for i in required if i % 2 == 1 and not (kind == "TRANSLATIONAL_MOTOR" and i == 3)]
    b_nodes = [n[i] for i in required if i % 2 == 0]
    if kind == "CYLINDRICAL" and n[3] == 0:
        a_nodes = []
    a, b, finding = _sides(bodies, a_nodes, b_nodes, site)
    if finding:
        out[finding[0]].append(finding[1])
        if finding[0] != "warnings" or a is None or b is None:
            return
    summary = {**site, "kind": kind, "nodes": {f"n{i}": n[i] for i in required}, "body_a": a, "body_b": b,
               "constrained_dof": dof, "free": list(FREE[kind])}
    out["joints"].append(summary)
    if dof is not None and a != b:
        axis = position[n[3]] - position[n[1]] if 3 in required and n[3] else None
        pairs.setdefault(frozenset((str(a), str(b))), []).append((kind, axis, position[n[1]], site))


def _geometry(kind: str, n: dict, required: tuple, coincident: tuple, position: dict, size: float,
              site: dict) -> list[tuple[str, dict]]:
    found = []
    missing = [f"n{i}" for i in required if not n[i]]
    if missing:
        return [("errors", {**site, "kind": "joint_nodes_missing", "message": f"required nodes {missing} are blank"})]
    undefined = [n[i] for i in required if n[i] not in position]
    if undefined:  # the reference check reports dangling node IDs; nothing to measure here
        return [("unverified", {**site, "reason": f"nodes {undefined} are not defined in this deck"})]
    p = {i: position[n[i]] for i in required}
    scale = float(np.linalg.norm(p[3] - p[1])) if 3 in p else size
    if 3 in p and scale <= 1e-12 * max(size, 1.0):
        return [("errors", {**site, "kind": "joint_zero_axis", "message": "N1 and N3 coincide; the axis is undefined"})]
    for i, j in coincident:
        gap = float(np.linalg.norm(p[i] - p[j]))
        if gap > ERROR * scale:
            found.append(("errors", {**site, "kind": "joint_nodes_not_coincident", "pair": [n[i], n[j]], "gap": gap,
                                     "message": f"N{i} and N{j} are {gap:.4g} apart (axis length {scale:.4g})"}))
        elif gap > WARN * scale:
            found.append(("warnings", {**site, "kind": "joint_nodes_not_coincident", "pair": [n[i], n[j]], "gap": gap,
                                       "message": f"N{i} and N{j} are {gap:.4g} apart; the solver warns beyond "
                                                  f"1e-4 x |N1N3| = {WARN * scale:.4g}"}))
    if kind == "UNIVERSAL":
        u, v = p[3] - p[1], p[4] - p[2]
        cos = abs(float(u @ v)) / max(float(np.linalg.norm(u) * np.linalg.norm(v)), 1e-300)
        # validated vehicle models (NCAC Econoline) carry |cos| up to 0.005: small deviations are warnings
        if np.linalg.norm(v) == 0 or cos > UNIVERSAL_ERROR:
            found.append(("errors", {**site, "kind": "universal_axes_not_perpendicular", "cos": cos,
                                     "message": f"N1-N3 and N2-N4 must be perpendicular (|cos| = {cos:.3g})"}))
        elif cos > UNIVERSAL_WARN:
            found.append(("warnings", {**site, "kind": "universal_axes_not_perpendicular", "cos": cos,
                                       "message": f"N1-N3 and N2-N4 deviate from perpendicular (|cos| = {cos:.3g})"}))
    if 5 in p and kind in ("TRANSLATIONAL", "LOCKING", "ROTATIONAL_MOTOR"):
        u, w = p[3] - p[1], p[5] - p[1]
        if np.linalg.norm(np.cross(u, w)) <= 1e-6 * np.linalg.norm(u) * max(float(np.linalg.norm(w)), 1e-300):
            found.append(("errors", {**site, "kind": "joint_collinear_nodes",
                                     "message": "N1, N3 and N5 are collinear; the rotation about N1-N3 is not fixed"}))
    return found


def _sides(bodies: RigidBodies, a_nodes: list[int], b_nodes: list[int], site: dict):
    """(body A, body B, finding) from the bodies shared by the odd and by the even nodes."""
    def common(group: list[int]) -> tuple[set[Body], list[int]]:
        free = [node for node in group if not bodies.of(node)]
        sets = [bodies.of(node) for node in group if bodies.of(node)]
        return (set.intersection(*sets) if sets else set()), free

    a, free_a = common(a_nodes)
    b, free_b = common(b_nodes)
    free = free_a + free_b
    if free:
        level = "unverified" if bodies.unverified else "errors"
        return None, None, (level, {**site, "kind": "joint_node_not_on_rigid_body", "nodes": free,
                                    "message": f"nodes {free} belong to no rigid part, extra-node set or nodal "
                                               "rigid body"})
    if not a or not b:
        side, group = ("odd (A)", a_nodes) if not a else ("even (B)", b_nodes)
        owners = {node: sorted(bodies.of(node)) for node in group}
        return None, None, ("errors", {**site, "kind": "joint_side_split", "nodes": group, "owners": owners,
                                       "message": f"the {side} nodes are not on one common rigid body: {owners} "
                                                  "(R11 Warning 30485; the joint then holds only N1's body)"})
    pick = lambda group: sorted(group)[0] if len(group) == 1 else sorted(group)  # noqa: E731
    if a & b:
        same = sorted(a & b)[0]
        merged = bool(bodies.merged) and same[0] == "part"
        return pick(a), pick(b), ("warnings", {
            **site, "kind": "joint_same_body", "body": same,
            "message": "both sides belong to the same rigid body" + (" (parts merged by *CONSTRAINED_RIGID_BODIES)"
                                                                     if merged else "") + "; the joint has no effect"})
    return pick(a), pick(b), None


def _on_one_line(joints: list) -> bool:
    """Revolute / cylindrical axes on one line and spherical points on it: redundant but compatible (a hinge
    with a pin on each side, common in vehicle models), so not reported."""
    lines = [(point, axis / np.linalg.norm(axis)) for kind, axis, point, _ in joints
             if kind in ("REVOLUTE", "CYLINDRICAL") and axis is not None and np.linalg.norm(axis) > 0]
    if not lines or any(kind not in ("REVOLUTE", "CYLINDRICAL", "SPHERICAL") for kind, _, _, _ in joints):
        return False
    origin, direction = lines[0]
    scale = max(float(np.linalg.norm(p - origin)) for p in [point for _, _, point, _ in joints] + [origin]) or 1.0

    def off(point: np.ndarray) -> float:
        d = point - origin
        return float(np.linalg.norm(d - (d @ direction) * direction))

    return all(np.linalg.norm(np.cross(direction, u)) <= 1e-3 and off(p) <= 1e-3 * scale for p, u in lines[1:]) and \
        all(off(point) <= 1e-3 * scale for kind, _, point, _ in joints if kind == "SPHERICAL")


def _overconstrained(pairs: dict, position: dict) -> list[dict]:
    found = []
    for bodies, joints in pairs.items():
        if len(joints) < 2 or _on_one_line(joints):
            continue
        total = sum(RULES[kind][2] for kind, _, _, _ in joints)
        axes = [axis / np.linalg.norm(axis) for kind, axis, _, _ in joints
                if kind in ("REVOLUTE", "CYLINDRICAL") and axis is not None and np.linalg.norm(axis) > 0]
        skew = any(np.linalg.norm(np.cross(axes[0], other)) > 1e-3 for other in axes[1:])
        if total > 6 or skew:
            reason = f"{total} relative DOF constrained" if total > 6 else "revolute/cylindrical axes not collinear"
            found.append({"kind": "joint_overconstrained", "bodies": sorted(bodies),
                          "joints": [s for _, _, _, s in joints],
                          "message": f"{len(joints)} joints between the same two rigid bodies: {reason}"})
    return found


__all__ = ["FREE", "MOTOR_LAG", "RULES", "RigidBodies", "check_joints", "joint_kind", "node_set_blocks",
           "rigid_bodies", "uses_lagrange"]
