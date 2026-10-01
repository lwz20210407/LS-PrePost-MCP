"""Typed selection of current GUI entities with exact ID and geometry readback."""

import math

import numpy as np

from .gui_mesh import check_same_nodes, check_same_parts, mesh_index


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
    def _select_gui(self, session_id, action, arguments, kind, choose):
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
            return result

        return self._gui_mesh_edit(
            session_id,
            action,
            arguments,
            commands,
            lambda a, b: verify_selection(a, b, expected, kind),
            precheck,
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
