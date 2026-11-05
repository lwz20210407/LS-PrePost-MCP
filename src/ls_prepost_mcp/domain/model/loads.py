"""Boundary conditions, loads and initial conditions at keyword level (tasks.yaml P05).

Every function writes one keyword through :func:`cards.insert_card` (PyDYNA text, every given
field read back) and creates the node set, segment set or curve it needs. Values are written
as given in the unit system the caller declares; nothing is converted and no physical value
is invented. Targets:

* nodes: ``{"node_set": sid}``, ``{"nodes": [...]}`` or ``{"select": {box|sphere|plane|parts}}``
* segments: ``{"segment_set": sid}``, ``{"segments": [[n1, n2, n3, n4], ...]}`` or
  ``{"exterior": {parts, direction, angle, box}}`` (outward faces of solid parts)
* curves: ``{"lcid": id}`` (must exist) or ``{"points": [[x, y], ...], "title"?: str}``
"""
from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING

import numpy as np

from . import geometry, selectors, sets
from ._identity import exact_integer
from .cards import insert_card
from .fields import FieldError, single_line

if TYPE_CHECKING:
    from .deck import KeywordDeck

DOFS = {"x": 1, "y": 2, "z": 3, "rx": 5, "ry": 6, "rz": 7}
MOTION = {"velocity": 0, "acceleration": 1, "displacement": 2}


def _append_boundary(function):
    """Undo P05's appended dependencies on rejection; never clone mesh arrays."""
    @wraps(function)
    def apply(deck, *args, **kwargs):
        main = deck.main
        blocks = list(main.blocks)
        tails = [(block, block.lines[-1]) for block in blocks if block.lines]
        modified, changes = main.modified, len(deck.changes)
        files, warnings = dict(deck.files), list(deck.warnings)
        try:
            return function(deck, *args, **kwargs)
        except Exception:
            # P05 only inserts main-file blocks and edits those new blocks.
            # Core insert may also supply a missing newline on an old tail.
            main.blocks[:] = blocks
            for block, tail in tails:
                block.lines[-1] = tail
            main.modified = modified
            del deck.changes[changes:]
            deck.files.clear()
            deck.files.update(files)
            main.invalidate_line_numbers()
            deck._rebuild()
            deck.warnings[:] = warnings
            raise
    return apply


def _node_target(deck: KeywordDeck, target: dict) -> dict:
    """Resolve and validate with existing readers before allocating dependencies."""
    from .node_sets import NodeSets, integer

    if "node_set" in target:
        sid = integer(target["node_set"], "Node set SID", positive=True)
        if sid not in deck.references(False).defined.get("node_set", set()):
            raise FieldError(f"Node set {sid} is not defined")
        if not NodeSets(deck).resolve(sid):
            raise FieldError("The target node set selects no nodes")
        return {"node_set": sid}
    if "selector" in target:
        chosen = selectors.selector(target["selector"])
        if chosen.entity_type != "node":
            raise FieldError("A load or boundary target Selector must select nodes")
        ids = selectors.resolve(deck, chosen).tolist()
    else:
        select = dict(target.get("select") or {})
        if "parts" in select:
            select["parts"] = [exact_integer(value, "Selected Part ID") for value in select["parts"]]
        ids = target["nodes"] if "nodes" in target else geometry.select_nodes(deck, **select).tolist()
    ids = [integer(value, "Target node ID", positive=True) for value in ids]
    if not ids:
        raise FieldError("The target selects no nodes")
    if np.any(~np.isin(ids, NodeSets(deck).ids)):
        raise FieldError("The target refers to undefined nodes")
    return {"nodes": ids, "title": target.get("title")}


def _node_set(deck: KeywordDeck, target: dict) -> int:
    target = _node_target(deck, target)
    if "node_set" in target:
        return target["node_set"]
    return sets.create_set(deck, "node", target["nodes"], title=target.get("title"))[0]


def _segment_target(deck: KeywordDeck, target: dict) -> dict:
    if "segment_set" in target:
        sid = exact_integer(target["segment_set"], "Segment set SID")
        if sid not in deck.references(False).defined.get("segment_set", set()):
            raise FieldError(f"Segment set {sid} is not defined")
        return {"segment_set": sid}
    exterior = dict(target.get("exterior") or {})
    if "parts" in exterior:
        exterior["parts"] = [exact_integer(value, "Exterior Part ID") for value in exterior["parts"]]
    rows = target["segments"] if "segments" in target else geometry.exterior_segments(deck, **exterior).tolist()
    if any(len(row) != 4 for row in rows):
        raise FieldError("Segments need 4 node IDs (repeat the third for triangles)")
    rows = [[exact_integer(value, "Segment node ID") for value in row] for row in rows]
    if not rows:
        raise FieldError("The segment target selects no segments")
    return {"segments": rows, "title": target.get("title")}


def _segment_set(deck: KeywordDeck, target: dict) -> int:
    target = _segment_target(deck, target)
    if "segment_set" in target:
        return target["segment_set"]
    return sets.create_set(deck, "segment", target["segments"], title=target.get("title"))[0]


@_append_boundary
def ensure_curve(deck: KeywordDeck, spec: dict) -> int:
    """Existing curve ID, or a new *DEFINE_CURVE from ``points`` (next free ID)."""
    defined = deck.references(False).defined.get("curve", set())
    if "lcid" in spec:
        lcid = exact_integer(spec["lcid"], "Curve LCID")
        if lcid not in defined:
            raise FieldError(f"Curve {lcid} is not defined")
        return lcid
    points = [(float(a), float(o)) for a, o in spec["points"]]
    if len(points) < 2:
        raise FieldError("A curve needs at least two points")
    lcid = max(defined, default=0) + 1
    title = spec.get("title")
    head = ["*DEFINE_CURVE_TITLE", single_line(title, "Curve title")] if title else ["*DEFINE_CURVE"]
    blocks = deck.insert("\n".join(head + [f"{lcid:>10}", "0.0 0.0"]) + "\n")
    deck.set_points(blocks[0], points)
    return lcid


def _card(deck: KeywordDeck, keyword: str, fields: dict, **ids: int) -> dict:
    block = insert_card(deck, keyword, fields)[0]
    return {"keyword": keyword, "file": str(block.file.path), "line": block.line_number, **ids}


@_append_boundary
def add_spc(deck: KeywordDeck, target: dict, dofs: list[str] | str, cid: int = 0) -> dict:
    """*BOUNDARY_SPC_SET; ``dofs`` from x, y, z, rx, ry, rz or ``"all"``."""
    wanted = set(DOFS) if dofs == "all" else {d.lower() for d in dofs}
    if not wanted or wanted - set(DOFS):
        raise FieldError(f"dofs must come from {sorted(DOFS)} or be 'all'")
    cid = exact_integer(cid, "SPC coordinate-system CID")
    nsid = _node_set(deck, target)
    fields = {"nsid": nsid, "cid": cid, **{f"dof{d}": int(d in wanted) for d in DOFS}}
    return _card(deck, "*BOUNDARY_SPC_SET", fields, nsid=nsid)


@_append_boundary
def add_prescribed_motion(deck: KeywordDeck, target: dict, dof: str, motion: str, curve: dict,
                          sf: float = 1.0) -> dict:
    """*BOUNDARY_PRESCRIBED_MOTION_SET, or _RIGID when ``target`` is ``{"rigid_part": pid}``."""
    fields = {"dof": DOFS[dof.lower()], "vad": MOTION[motion.lower()], "sf": float(sf)}
    if "rigid_part" in target:
        pid = exact_integer(target["rigid_part"], "Rigid Part ID")
        if pid not in deck.references(False).defined.get("part", set()):
            raise FieldError(f"Part {pid} is not defined")
    else:
        target = _node_target(deck, target)
    lcid = ensure_curve(deck, curve)
    fields["lcid"] = lcid
    if "rigid_part" in target:
        return _card(deck, "*BOUNDARY_PRESCRIBED_MOTION_RIGID", {"pid": pid, **fields}, pid=pid, lcid=lcid)
    nsid = _node_set(deck, target)
    return _card(deck, "*BOUNDARY_PRESCRIBED_MOTION_SET", {"nsid": nsid, **fields}, nsid=nsid, lcid=lcid)


@_append_boundary
def add_nodal_load(deck: KeywordDeck, target: dict, dof: str, curve: dict, sf: float = 1.0) -> dict:
    """*LOAD_NODE_SET (force for x/y/z, moment for rx/ry/rz)."""
    sf = float(sf)
    target = _node_target(deck, target)
    dof = DOFS[dof.lower()]
    lcid = ensure_curve(deck, curve)
    nsid = _node_set(deck, target)
    fields = {"nsid": nsid, "dof": dof, "lcid": lcid, "sf": sf}
    return _card(deck, "*LOAD_NODE_SET", fields, nsid=nsid, lcid=lcid)


@_append_boundary
def add_pressure(deck: KeywordDeck, target: dict, curve: dict, sf: float = 1.0) -> dict:
    """*LOAD_SEGMENT_SET (positive pressure acts against the segment normal)."""
    sf = float(sf)
    target = _segment_target(deck, target)
    lcid = ensure_curve(deck, curve)
    ssid = _segment_set(deck, target)
    return _card(deck, "*LOAD_SEGMENT_SET", {"ssid": ssid, "lcid": lcid, "sf": sf}, ssid=ssid, lcid=lcid)


@_append_boundary
def add_gravity(deck: KeywordDeck, direction: str, curve: dict, sf: float = 1.0) -> dict:
    """*LOAD_BODY_X/Y/Z with the curve scaled by ``sf`` (sign convention as in LS-DYNA, not altered)."""
    axis = direction.lower()
    if axis not in ("x", "y", "z"):
        raise FieldError("direction must be x, y or z")
    sf = float(sf)
    lcid = ensure_curve(deck, curve)
    return _card(deck, f"*LOAD_BODY_{axis.upper()}", {"lcid": lcid, "sf": sf}, lcid=lcid)


@_append_boundary
def add_initial_velocity(deck: KeywordDeck, target: dict, velocity: list[float]) -> dict:
    """*INITIAL_VELOCITY_GENERATION for ``{"part": pid}`` / ``{"part_set": sid}``, else *INITIAL_VELOCITY."""
    vx, vy, vz = (float(v) for v in velocity)
    defined = deck.references(False).defined
    if "part" in target or "part_set" in target:
        kind, styp = ("part", 2) if "part" in target else ("part_set", 1)
        ident = exact_integer(target[kind], "Initial-velocity " + kind + " ID")
        if ident not in defined.get(kind, set()):
            raise FieldError(f"{kind} {ident} is not defined")
        fields = {"id": ident, "styp": styp, "omega": 0.0, "vx": vx, "vy": vy, "vz": vz}
        return _card(deck, "*INITIAL_VELOCITY_GENERATION", fields, **{kind: ident})
    nsid = _node_set(deck, target)
    return _card(deck, "*INITIAL_VELOCITY", {"nsid": nsid, "vx": vx, "vy": vy, "vz": vz}, nsid=nsid)


@_append_boundary
def add_rigid_wall(deck: KeywordDeck, point: list[float], normal: list[float], target: dict | None = None,
                   friction: float = 0.0) -> dict:
    """*RIGIDWALL_PLANAR through ``point`` with ``normal`` towards the model; nodes default to all."""
    tail = [float(v) for v in point]
    head = [t + float(n) for t, n in zip(tail, normal)]
    if head == tail:
        raise FieldError("normal must not be zero")
    friction = float(friction)
    nsid = _node_set(deck, target) if target else 0
    fields = {"nsid": nsid, "xt": tail[0], "yt": tail[1], "zt": tail[2], "xh": head[0], "yh": head[1],
              "zh": head[2], "fric": friction}
    return _card(deck, "*RIGIDWALL_PLANAR", fields, nsid=nsid)


@_append_boundary
def add_nodal_rigid_body(deck: KeywordDeck, target: dict, pid: int | None = None) -> dict:
    """*CONSTRAINED_NODAL_RIGID_BODY; ``pid`` defaults to the next ID above every part ID."""
    defined = deck.references(False).defined.get("part", set())
    pid = max(defined, default=0) + 1 if pid is None else exact_integer(pid, "Nodal rigid-body PID")
    if pid in defined:
        raise FieldError(f"Part ID {pid} is already used by a part")
    nsid = _node_set(deck, target)
    block = deck.insert(f"*CONSTRAINED_NODAL_RIGID_BODY\n{pid:>10}{0:>10}{nsid:>10}\n")[0]
    if deck.get(block, "nsid", row=pid).value != nsid:
        deck.delete(block, force=True)
        raise FieldError("New *CONSTRAINED_NODAL_RIGID_BODY failed verification")
    return {"keyword": block.name, "file": str(block.file.path), "line": block.line_number, "pid": pid, "nsid": nsid}


@_append_boundary
def add_non_reflecting(deck: KeywordDeck, target: dict) -> dict:
    """*BOUNDARY_NON_REFLECTING on a segment set (dilatational and shear waves absorbed)."""
    ssid = _segment_set(deck, target)
    return _card(deck, "*BOUNDARY_NON_REFLECTING", {"ssid": ssid}, ssid=ssid)


KINDS = {"spc": add_spc, "prescribed_motion": add_prescribed_motion, "nodal_load": add_nodal_load,
         "pressure": add_pressure, "gravity": add_gravity, "initial_velocity": add_initial_velocity,
         "rigid_wall": add_rigid_wall, "cnrb": add_nodal_rigid_body, "non_reflecting": add_non_reflecting}

__all__ = ["DOFS", "KINDS", "MOTION", "add_gravity", "add_initial_velocity", "add_nodal_load",
           "add_nodal_rigid_body", "add_non_reflecting", "add_pressure", "add_prescribed_motion",
           "add_rigid_wall", "add_spc", "ensure_curve"]
