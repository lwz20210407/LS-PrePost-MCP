"""Create joints between rigid bodies at keyword level (tasks.yaml P12).

``add_joint`` writes new coincident joint nodes at ``origin`` (and at ``origin + length * axis`` and
``origin + length * perpendicular`` where the joint type needs them), attaches them to each side and
writes *CONSTRAINED_JOINT_<TYPE>_ID (with _LOCAL / _FAILURE and the motor PARM card when asked).

A side is a rigid part (``{"part": pid}``, *MAT_RIGID: the nodes are added with
*CONSTRAINED_EXTRA_NODES_SET), an existing nodal rigid body (``{"nodal_rigid_body": pid}``: the body
gets a new node set with its old members and the joint nodes) or nodes of a deformable part (``{"nodes": [...]}``, ``{"select":
{...}}`` or ``{"selector": {...}}``: a new *CONSTRAINED_NODAL_RIGID_BODY "spider" holds them together
with the joint nodes). The new joint is checked with :func:`joint_checks.check_joints`; any finding
on it raises, and ``edit_deck`` then leaves the deck unchanged.

Card order ID, 1, PARM, LOCAL, FAILURE x2 was confirmed on R11 (TFAIL took effect, 2026-10-05);
PyDYNA 0.12 cannot write the ID / LOCAL / FAILURE cards, so the text is built here and read back.
"""
from __future__ import annotations

import numpy as np

from . import geometry, joint_checks, selectors, sets
from .deck import KeywordDeck
from .fields import FieldError, format_value, single_line
from .loads import ensure_curve

KINDS = {"spherical": "SPHERICAL", "revolute": "REVOLUTE", "cylindrical": "CYLINDRICAL", "planar": "PLANAR",
         "universal": "UNIVERSAL", "translational": "TRANSLATIONAL", "locking": "LOCKING",
         "rotational_motor": "ROTATIONAL_MOTOR", "translational_motor": "TRANSLATIONAL_MOTOR"}
MOTOR_TYPES = {"velocity": 0, "acceleration": 1, "displacement": 2}
FAILURE_FIELDS = ("cid", "tfail", "coupl", "nxx", "nyy", "nzz", "mxx", "myy", "mzz")


def _unit(vector: object, name: str) -> np.ndarray:
    try:
        v = np.asarray(vector, dtype=float).reshape(3)
    except (TypeError, ValueError) as error:
        raise FieldError(f"{name} must be a non-zero 3-vector") from error
    norm = float(np.linalg.norm(v))
    if not np.isfinite(norm) or norm == 0:
        raise FieldError(f"{name} must be a non-zero 3-vector")
    return v / norm


def _perpendicular(axis: np.ndarray, hint: object = None) -> np.ndarray:
    if hint is not None:
        p = np.asarray(hint, dtype=float).reshape(3)
        p = p - (p @ axis) * axis
        if np.linalg.norm(p) <= 1e-9 * max(float(np.linalg.norm(hint)), 1e-300):
            raise FieldError("the reference direction is parallel to the axis")
        return p / np.linalg.norm(p)
    trial = np.eye(3)[int(np.argmin(np.abs(axis)))]
    p = trial - (trial @ axis) * axis
    return p / np.linalg.norm(p)


def _layout(kind: str, origin: np.ndarray, axis: np.ndarray | None, second: np.ndarray | None,
            perp: np.ndarray | None, length: float, third: np.ndarray | None = None
            ) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Positions of the new nodes on side A (N1, N3, N5) and side B (N2, N4, N6)."""
    if kind == "SPHERICAL":
        return [origin], [origin]
    tip = origin + length * axis
    if kind == "UNIVERSAL":
        return [origin, tip], [origin, origin + length * second]
    if kind == "TRANSLATIONAL_MOTOR":
        return [origin], [origin, tip]  # N3 (direction N2 -> N3) is on side B
    if kind in ("TRANSLATIONAL", "LOCKING", "ROTATIONAL_MOTOR"):
        side = third if third is not None else origin + length * perp
        return [origin, tip, side], [origin, tip, side]
    return [origin, tip], [origin, tip]


def _rigid_parts(deck: KeywordDeck) -> set[int]:
    return joint_checks.rigid_bodies(deck).rigid_parts


def _cnrb(deck: KeywordDeck, pid: int) -> tuple[object, int | None] | None:
    """(block, row) of the *CONSTRAINED_NODAL_RIGID_BODY with PID ``pid``."""
    for block in deck.iter_blocks():
        if block.name.startswith("*CONSTRAINED_NODAL_RIGID_BODY"):
            hits = deck.find(block.name, pid=pid)
            hits = [(b, r) for b, r in hits if b is block]
            if hits:
                return hits[0]
    return None


def _side_nodes(deck: KeywordDeck, spec: dict, label: str) -> tuple[str, int | None, list[int]]:
    """('part', pid, []) for a rigid part, ('spider', None, node IDs) for nodes of a deformable part."""
    if not isinstance(spec, dict) or len(spec) != 1:
        raise FieldError(f"Side {label}: give exactly one of part, nodal_rigid_body, nodes, select, selector")
    (key, value), = spec.items()
    if key == "nodal_rigid_body":
        pid = int(value)
        if _cnrb(deck, pid) is None:
            raise FieldError(f"Side {label}: no *CONSTRAINED_NODAL_RIGID_BODY with PID {pid}")
        return "cnrb", pid, []
    if key == "part":
        pid = int(value)
        if pid not in deck.references(False).defined.get("part", set()):
            raise FieldError(f"Side {label}: part {pid} is not defined")
        if pid not in _rigid_parts(deck):
            raise FieldError(f"Side {label}: part {pid} is not a rigid part (*MAT_RIGID); give the nodes of the "
                             "deformable part that the joint should hold (nodes / select / selector)")
        return "part", pid, []
    if key == "nodes":
        ids = [int(n) for n in value]
    elif key == "select":
        ids = geometry.select_nodes(deck, **value).tolist()
    elif key == "selector":
        chosen = selectors.selector(value)
        if chosen.entity_type != "node":
            raise FieldError(f"Side {label}: the selector must select nodes")
        ids = selectors.resolve(deck, chosen).tolist()
    else:
        raise FieldError(f"Side {label}: unknown key {key!r}; use part, nodes, select or selector")
    if not ids:
        raise FieldError(f"Side {label}: the selection is empty")
    owned = joint_checks.rigid_bodies(deck)
    taken = sorted(n for n in ids if owned.of(int(n)))
    if taken:
        raise FieldError(f"Side {label}: nodes {taken[:10]} already belong to a rigid body; a node may belong to one")
    return "spider", None, ids


def _length(deck: KeywordDeck, sides: list[tuple[str, int | None, list[int]]], given: float | None) -> float:
    if given is not None:
        if not float(given) > 0:
            raise FieldError("length must be positive")
        return float(given)
    ids, xyz = geometry.nodes(deck)
    index = {n: i for i, n in enumerate(ids.tolist())}
    rigid = joint_checks.rigid_bodies(deck)
    chosen: list[int] = []
    for kind, pid, nodes in sides:
        chosen += nodes if kind == "spider" else [n for n, b in rigid.owner.items() if ("part", pid) in b]
    points = xyz[[index[n] for n in chosen if n in index]]
    extent = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0))) if len(points) else 0.0
    if extent <= 0:
        raise FieldError("Cannot derive the node spacing from the sides; give length")
    return 0.5 * extent  # node pairs as far apart as practical (R17 Vol I *CONSTRAINED_JOINT)


def _write_nodes(deck: KeywordDeck, first: int, points: list[np.ndarray], file: object) -> list[int]:
    ids = list(range(first, first + len(points)))
    if len(str(ids[-1])) > 8:
        raise FieldError("New node IDs need more than 8 digits; use a long-format deck")
    rows = "".join(f"{n:>8}" + "".join(format_value(float(v), 16, "float", symmetric=True)[0].rjust(16) for v in p)
                   + "\n" for n, p in zip(ids, points))
    deck.insert("*NODE\n" + rows, file=file)
    return ids


def _attach(deck: KeywordDeck, side: tuple[str, int | None, list[int]], new: list[int], file: object,
            title: str) -> dict:
    kind, pid, selected = side
    if kind == "part":
        nsid = sets.create_set(deck, "node", new, title=f"{title} extra nodes", file=file)[0]
        deck.insert(f"*CONSTRAINED_EXTRA_NODES_SET\n{pid:>10}{nsid:>10}{0:>10}\n", file=file)
        return {"rigid_part": pid, "extra_nodes_set": nsid}
    if kind == "cnrb":
        # the existing set may be shared with other keywords: the body gets a new set (old members + new nodes)
        block, row = _cnrb(deck, pid)
        old = int(deck.get(block, "nsid", row=row).value)
        node_sets = joint_checks.node_set_blocks(deck)
        if old not in node_sets:
            raise FieldError(f"Node set {old} of nodal rigid body {pid} is not one readable member list "
                             "(missing, several _COLLECT blocks or a duplicate SID)")
        members = deck.members(node_sets[old])
        nsid = sets.create_set(deck, "node", members + new, title=f"{title} on nodal rigid body {pid}", file=file)[0]
        deck.set(block, "nsid", nsid, row=row)
        return {"nodal_rigid_body": pid, "node_set": nsid, "previous_node_set": old}
    nsid = sets.create_set(deck, "node", selected + new, title=f"{title} spider", file=file)[0]
    # a nodal rigid body ID shares the part ID space (and must differ from every other rigid body)
    used = deck.references(False).defined.get("part", set()) | {
        body[1] for owners in joint_checks.rigid_bodies(deck).owner.values() for body in owners}
    cnrb = max(used, default=0) + 1
    deck.insert(f"*CONSTRAINED_NODAL_RIGID_BODY\n{cnrb:>10}{0:>10}{nsid:>10}\n", file=file)
    return {"nodal_rigid_body": cnrb, "node_set": nsid, "held_nodes": len(selected)}


def _real(value: object) -> str:
    return format_value(float(value), 10, "float")[0].rjust(10)


def _card_text(kind: str, nodes: list[int], jid: int, title: str, rps: float, damp: float, motor: dict | None,
               local: dict | None, failure: dict | None) -> str:
    keyword = f"*CONSTRAINED_JOINT_{kind}_ID" + ("_LOCAL" if local else "") + ("_FAILURE" if failure else "")
    lines = [keyword, f"{jid:>10}{single_line(title, 'Joint title')[:70]}"]
    lines.append("".join(f"{n:>10}" if n else " " * 10 for n in nodes) + _real(rps) + _real(damp))
    if motor is not None:
        lines.append(" " * 10 + f"{motor['lcid']:>10}{motor['type']:>10}")
    if local:
        lines.append(f"{int(local['raid']):>10}{int(local.get('lst', 0)):>10}")
    if failure:
        values = {k: failure.get(k, 0) for k in FAILURE_FIELDS}
        lines.append(f"{int(values['cid']):>10}" + _real(values["tfail"]) + _real(values["coupl"]))
        lines.append("".join(_real(values[k]) for k in ("nxx", "nyy", "nzz", "mxx", "myy", "mzz")))
    return "\n".join(lines) + "\n"


def add_joint(deck: KeywordDeck, kind: str, a: dict, b: dict, origin: list[float], axis: list[float] | None = None,
              second_axis: list[float] | None = None, reference: list[float] | None = None,
              third_point: list[float] | None = None,
              length: float | None = None, jid: int | None = None, title: str | None = None, rps: float = 1.0,
              damp: float = 1.0, motor: dict | None = None, local: dict | None = None, failure: dict | None = None,
              file: object = None) -> dict:
    """Joint ``kind`` between sides ``a`` and ``b`` at ``origin``; see the module docstring."""
    name = KINDS.get(str(kind).lower())
    if name is None:
        raise FieldError(f"Unknown joint kind {kind!r}; use one of {sorted(KINDS)}")
    p0 = np.asarray(origin, dtype=float).reshape(3)
    unit = None if name == "SPHERICAL" else _unit(axis if axis is not None else [], "axis")
    second = perp = None
    if name == "UNIVERSAL":
        second = _unit(second_axis if second_axis is not None else _perpendicular(unit), "second_axis")
        if abs(float(second @ unit)) > 1e-6:
            raise FieldError("second_axis must be perpendicular to axis for a universal joint")
    if name in ("TRANSLATIONAL", "LOCKING", "ROTATIONAL_MOTOR"):
        perp = _perpendicular(unit, reference)
    third = None
    if third_point is not None:  # the third pair need not be perpendicular to the axis (R17 Vol I)
        if name not in ("TRANSLATIONAL", "LOCKING", "ROTATIONAL_MOTOR"):
            raise FieldError("third_point is used by translational, locking and rotational_motor joints")
        third = np.asarray(third_point, dtype=float).reshape(3)
    if name.endswith("MOTOR"):
        if not motor:
            raise FieldError(f"{name} needs motor = {{curve: {{points | lcid}}, type: velocity|acceleration|displacement}}")
        if motor.get("type", "velocity") not in MOTOR_TYPES:
            raise FieldError(f"motor type must be one of {sorted(MOTOR_TYPES)}")
    elif motor:
        raise FieldError("motor is only used by rotational_motor and translational_motor")
    if failure and set(failure) - set(FAILURE_FIELDS):
        raise FieldError(f"failure fields must come from {FAILURE_FIELDS}")
    sides = [_side_nodes(deck, a, "a"), _side_nodes(deck, b, "b")]
    if sides[0][0] == sides[1][0] == "part" and sides[0][1] == sides[1][1]:
        raise FieldError("Both sides are the same rigid part")
    spacing = 0.0 if name == "SPHERICAL" else _length(deck, sides, length)
    pos_a, pos_b = _layout(name, p0, unit, second, perp, spacing, third)
    target = file or deck.main
    ids, _ = geometry.nodes(deck)
    first = int(ids.max()) + 1 if ids.size else 1
    new_a = _write_nodes(deck, first, pos_a, target)
    new_b = _write_nodes(deck, first + len(new_a), pos_b, target)
    defined = deck.references(False).defined
    jid = int(jid) if jid is not None else max(defined.get("joint", set()) | _joint_ids(deck), default=0) + 1
    label = (title or f"{kind} joint")[:70]
    attach_a = _attach(deck, sides[0], new_a, target, f"{label} A")
    attach_b = _attach(deck, sides[1], new_b, target, f"{label} B")
    nodes = [0] * 6
    for slot, node in zip((1, 3, 5), new_a):
        nodes[slot - 1] = node
    for slot, node in zip((2, 4, 6), new_b):
        nodes[slot - 1] = node
    if name == "TRANSLATIONAL_MOTOR":  # N1 on A, N2 and N3 on B, N4 unused
        nodes = [new_a[0], new_b[0], new_b[1], 0, 0, 0]
    drive = None
    if motor:
        drive = {"lcid": ensure_curve(deck, motor["curve"]), "type": MOTOR_TYPES[motor.get("type", "velocity")]}
    text = _card_text(name, nodes, jid, label, rps, damp, drive, local, failure)
    block = deck.insert(text, file=target)[0]
    _verify(deck, block, nodes, jid, drive, local, failure)
    findings = joint_checks.check_joints(deck)
    mine = [f for level in ("errors", "unverified") for f in findings[level] if f.get("line") == block.line_number
            and f.get("file") == str(block.file.path)]
    if mine:
        raise FieldError(f"The new joint failed its check: {mine[0].get('message', mine[0])}")
    summary = next(j for j in findings["joints"] if j["line"] == block.line_number and j["file"] == str(block.file.path))
    notes = [w["message"] for w in findings["warnings"] if w.get("line") == block.line_number
             and w.get("file") == str(block.file.path)]
    return {"keyword": block.name, "jid": jid, "file": str(block.file.path), "line": block.line_number,
            "nodes": {f"n{i}": n for i, n in enumerate(nodes, 1) if n}, "new_nodes": new_a + new_b,
            "side_a": attach_a, "side_b": attach_b, "length": spacing,
            "constrained_dof": summary["constrained_dof"], "free": summary["free"],
            **({"lcid": drive["lcid"]} if drive else {}), **({"warnings": notes} if notes else {})}


def _joint_ids(deck: KeywordDeck) -> set[int]:
    found = set()
    for block in deck.iter_blocks():
        if joint_checks.joint_kind(block.name) and "_ID" in block.name:
            try:
                found.add(int(deck.get(block, "jid").value))
            except (FieldError, KeyError, ValueError, TypeError):
                continue
    return found


def _verify(deck: KeywordDeck, block: object, nodes: list[int], jid: int, drive: dict | None, local: dict | None,
            failure: dict | None) -> None:
    expected = {f"n{i}": n for i, n in enumerate(nodes, 1) if n} | {"jid": jid}
    if drive:
        expected |= {"lcid": drive["lcid"], "type": drive["type"]}
    if local:
        expected |= {"raid": int(local["raid"])}
    if failure and "tfail" in failure:
        expected |= {"tfail": float(failure["tfail"])}
    for name, value in expected.items():
        read = deck.get(block, name).value
        if read is None or abs(float(read) - float(value)) > 1e-9 * max(1.0, abs(float(value))):
            deck.delete(block, force=True)
            raise FieldError(f"{block.name}.{name}: wrote {value!r} but read back {read!r}")


__all__ = ["KINDS", "MOTOR_TYPES", "add_joint"]
