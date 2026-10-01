"""Typed selection of current GUI entities with exact ID and geometry readback."""

import hashlib
import json
import math

import numpy as np

from .gui_mesh import check_same_nodes, check_same_parts, mesh_index


def mesh_signature(state):
    """Bind selection buffers to the model actually read, not a mutable title."""
    mesh_index(state)
    canonical = dict(
        nodes=sorted(state["nodes"]),
        elements=sorted((e["type"], e["id"], e["nodes"]) for e in state["elements"]),
        parts=sorted((int(k), sorted(v)) for k, v in state["part_elements"].items()),
        part_ids=sorted(state["part_ids"]),
    )
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, allow_nan=False).encode()).hexdigest()


def buffer_slot(slot):
    if type(slot) is not int or not 1 <= slot <= 10:
        raise ValueError("Native buffer slot must be an integer from 1 to 10")
    return slot - 1


def available_ids(state, kind):
    if kind == "node":
        return {row[0] for row in state["nodes"]}
    if kind == "part":
        return set(state["part_ids"])
    all_ids = [e["id"] for e in state["elements"]]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("Element selection requires globally unique element IDs")
    return {e["id"] for e in state["elements"] if kind == "element" or e["type"] == kind}


def in_parts(state, kind, parts):
    if not set(parts) <= set(state["part_ids"]):
        raise ValueError("Unknown part ID")
    if kind == "part":
        return set(parts)
    element_ids = {eid for pid in parts for eid in state["part_elements"][str(pid)]}
    # Global IDs are needed to disambiguate mixed element domains.
    available_ids(state, "element")
    if kind == "node":
        return {n for e in state["elements"] if e["id"] in element_ids for n in e["nodes"] if n}
    return element_ids & available_ids(state, kind)


def verify_selection(before, after, expected, kind):
    old_nodes, old_elements = mesh_index(before)
    new_nodes, new_elements = mesh_index(after)
    check_same_nodes(old_nodes, new_nodes)
    check_same_parts(before, after)
    if old_elements != new_elements:
        raise ValueError("Selection unexpectedly changed connectivity")
    actual = after.get("selection_ids")
    if actual is None or len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise ValueError("Native selected IDs differ from the requested set")
    return dict(
        entity_type=kind,
        selected_ids=sorted(expected),
        selected_count=len(expected),
        geometry_unchanged=True,
        model_scope="current keyword model",
    )


class GuiSelectionTools:
    def _select_gui(self, session_id, action, arguments, kind, choose, suffix=None, on_verified=None):
        expected = set()
        target = "element" if kind in ("solid", "beam") else kind

        def precheck(state):
            available = available_ids(state, kind)
            expected.update(choose(state))
            if not expected <= available or len(expected) > 20000:
                raise ValueError("Selection is outside the current entity registry or verification bound")

        def commands(state, directory):
            result = ["pall", "genselect clear", "genselect target " + target]
            if expected and expected == available_ids(state, target):
                result.append("genselect whole")
            else:
                result += ["genselect %s add %s %d" % (target, target, uid) for uid in sorted(expected)]
            return result + (suffix or [])

        return self._gui_mesh_edit(
            session_id,
            action,
            arguments,
            commands,
            lambda a, b: verify_selection(a, b, expected, kind),
            precheck,
            on_verified=on_verified,
            transaction_kind="selection",
        )

    def select_gui_entities(
        self,
        session_id: str,
        entity_type: str,
        entity_ids: list[int] | None = None,
        part_ids: list[int] | None = None,
        invert: bool = False,
    ) -> dict:
        """Select explicit nodes/shells/solids/beams/elements/parts in the visible keyword GUI. No ID/filter means whole; [] clears. Part filters derive connectivity membership; invert selects the complement."""
        from .post_backend import ids

        if entity_type not in ("node", "shell", "solid", "beam", "element", "part"):
            raise ValueError("Unsupported entity selection type")
        if entity_ids is not None and part_ids is not None:
            raise ValueError("Choose explicit IDs or a part filter")
        if entity_ids is not None and not isinstance(entity_ids, list):
            raise ValueError("entity_ids must be a list")
        if part_ids is not None and not isinstance(part_ids, list):
            raise ValueError("part_ids must be a list")
        if entity_ids:
            ids(entity_ids, "entity_ids", 20000)
        if part_ids:
            ids(part_ids, "part_ids", 1000)
        if type(invert) is not bool:
            raise ValueError("invert must be a boolean")

        def choose(state):
            available = available_ids(state, entity_type)
            selected = (
                set(entity_ids)
                if entity_ids is not None
                else in_parts(state, entity_type, part_ids)
                if part_ids is not None
                else available
            )
            if not selected <= available:
                raise ValueError("Unknown selected entity IDs")
            return available - selected if invert else selected

        return self._select_gui(
            session_id,
            "select_gui_entities",
            dict(entity_type=entity_type, entity_ids=entity_ids, part_ids=part_ids, invert=invert),
            entity_type,
            choose,
        )

    def combine_gui_selections(
        self,
        session_id: str,
        entity_type: str,
        left_ids: list[int],
        right_ids: list[int],
        operation: str = "union",
    ) -> dict:
        """Native selection from explicit union/intersection/difference/xor operands; verify exact IDs and unchanged keyword mesh. Does not infer entity type from an unknown current selection."""
        from .post_backend import ids

        if entity_type not in ("node", "shell", "solid", "beam", "element", "part"):
            raise ValueError("Unsupported entity selection type")
        for name, values in [("left_ids", left_ids), ("right_ids", right_ids)]:
            if not isinstance(values, list):
                raise ValueError(name + " must be a list")
            if values:
                ids(values, name, 20000)
        operations = dict(
            union=set.union,
            intersection=set.intersection,
            difference=set.difference,
            xor=set.symmetric_difference,
        )
        if operation not in operations:
            raise ValueError("Unknown selection set operation")
        left, right = set(left_ids), set(right_ids)

        def choose(state):
            if not (left | right) <= available_ids(state, entity_type):
                raise ValueError("Unknown operand entity IDs")
            return operations[operation](left, right)

        return self._select_gui(
            session_id,
            "combine_gui_selections",
            dict(entity_type=entity_type, left_ids=left_ids, right_ids=right_ids, operation=operation),
            entity_type,
            choose,
        )

    def save_gui_selection_buffer(
        self, session_id: str, entity_type: str, entity_ids: list[int], slot: int
    ) -> dict:
        """Select explicit IDs, save native Buffer1..10, clear and reload to verify it. Replaces that slot; persisted metadata is bound to this owned process and unchanged model."""
        from .post_backend import ids

        index = buffer_slot(slot)
        if entity_type not in ("node", "shell", "part"):
            raise ValueError("Native buffers currently support node, shell or part selection")
        if not isinstance(entity_ids, list) or not entity_ids:
            raise ValueError("A nonempty entity_ids list is required")
        ids(entity_ids, "entity_ids", 20000)

        def remember(before, after, meta):
            meta.setdefault("selection_buffers", {})[str(slot)] = dict(
                entity_type=entity_type, entity_ids=sorted(entity_ids), model_signature=mesh_signature(before)
            )

        return self._select_gui(
            session_id,
            "save_gui_selection_buffer",
            dict(entity_type=entity_type, entity_ids=entity_ids, slot=slot),
            entity_type,
            lambda state: set(entity_ids),
            [f"genselect save {index}", "genselect clear", f"genselect load {index}"],
            on_verified=remember,
        )

    def load_gui_selection_buffer(self, session_id: str, slot: int) -> dict:
        """Replace current selection from an owned verified native buffer. Reject stale model fingerprints; detect manual buffer replacement by native readback. Reopening or editing a model requires saving the slot again."""
        index = buffer_slot(slot)
        manager = self._session_manager()
        entry = {}

        def precheck(state):
            saved = manager.read(session_id).get("selection_buffers", {}).get(str(slot))
            if saved is None:
                raise ValueError("No verified native selection buffer in this session")
            entry.update(saved)
            kind, expected = entry["entity_type"], set(entry["entity_ids"])
            if mesh_signature(state) != entry["model_signature"]:
                raise ValueError("Selection buffer is stale after model changes; save it again")
            if not expected <= available_ids(state, kind):
                raise ValueError("Buffered IDs are absent from this model")

        return self._gui_mesh_edit(
            session_id,
            "load_gui_selection_buffer",
            dict(slot=slot),
            lambda state, directory: [
                "genselect clear",
                "genselect target " + entry["entity_type"],
                f"genselect load {index}",
            ],
            lambda a, b: verify_selection(a, b, entry["entity_ids"], entry["entity_type"]),
            precheck,
            transaction_kind="selection",
        )

    def select_gui_nodes_by_plane(
        self,
        session_id: str,
        point: list[float],
        normal: list[float],
        units: str,
        side: str = "band",
        tolerance: float = 0.0,
    ) -> dict:
        """Select reference nodes by signed distance to a plane: band |d|<=tolerance, positive d>tolerance, or negative d<-tolerance. Normalize the supplied normal; native ID readback verifies selection."""
        from .service import numbers, unit_label

        point, normal = numbers(point, 3, "point"), numbers(normal, 3, "normal")
        unit_label(units)
        scale = max(abs(v) for v in normal)
        if (
            scale == 0
            or side not in ("band", "positive", "negative")
            or not math.isfinite(tolerance)
            or tolerance < 0
        ):
            raise ValueError("Nonzero normal, supported side and nonnegative tolerance required")
        direction = np.asarray(normal) / scale
        direction /= np.linalg.norm(direction)

        def choose(state):
            chosen = set()
            for row in state["nodes"]:
                distance = float(np.dot(np.asarray(row[1:]) - point, direction))
                if not math.isfinite(distance):
                    raise ValueError("Plane distance exceeds finite numeric range")
                if (
                    abs(distance) <= tolerance
                    if side == "band"
                    else distance > tolerance
                    if side == "positive"
                    else distance < -tolerance
                ):
                    chosen.add(row[0])
            return chosen

        return self._select_gui(
            session_id,
            "select_gui_nodes_by_plane",
            dict(point=point, normal=normal, units=units, side=side, tolerance=tolerance),
            "node",
            choose,
        )

    def select_gui_nodes_by_box(
        self, session_id: str, bounds: list[float], units: str, inside: bool = True, tolerance: float = 0.0
    ) -> dict:
        """Select reference-coordinate nodes inside/outside an axis-aligned 3D box using native GUI readback and exact ID selection. This is a geometric predicate, not camera-space rectangle picking."""
        from .service import numbers, unit_label

        box = numbers(bounds, 6, "bounds")
        unit_label(units)
        if (
            any(box[i] > box[i + 3] for i in range(3))
            or not math.isfinite(tolerance)
            or tolerance < 0
            or type(inside) is not bool
        ):
            raise ValueError("Invalid box/tolerance/inside flag")
        lower, upper = np.asarray(box[:3]) - tolerance, np.asarray(box[3:]) + tolerance

        def choose(state):
            return {
                row[0]
                for row in state["nodes"]
                if bool(np.all(np.asarray(row[1:]) >= lower) and np.all(np.asarray(row[1:]) <= upper))
                == inside
            }

        return self._select_gui(
            session_id,
            "select_gui_nodes_by_box",
            dict(bounds=box, units=units, inside=inside, tolerance=tolerance),
            "node",
            choose,
        )

    def select_gui_nodes_by_sphere(
        self,
        session_id: str,
        center: list[float],
        radius: float,
        units: str,
        inside: bool = True,
        tolerance: float = 0.0,
    ) -> dict:
        """Select native GUI reference nodes by distance from a center, then verify exact selected IDs; preserve model geometry."""
        from .service import numbers, unit_label

        center = numbers(center, 3, "center")
        unit_label(units)
        if (
            not math.isfinite(radius)
            or radius <= 0
            or not math.isfinite(tolerance)
            or tolerance < 0
            or type(inside) is not bool
        ):
            raise ValueError("Positive radius, nonnegative tolerance and boolean inside required")

        def choose(state):
            return {
                row[0]
                for row in state["nodes"]
                if bool(np.linalg.norm(np.asarray(row[1:]) - center) <= radius + tolerance) == inside
            }

        return self._select_gui(
            session_id,
            "select_gui_nodes_by_sphere",
            dict(center=center, radius=radius, units=units, inside=inside, tolerance=tolerance),
            "node",
            choose,
        )
