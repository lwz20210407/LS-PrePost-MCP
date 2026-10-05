"""Typed selection of current GUI entities with exact ID and geometry readback."""

import hashlib
import json
import math

import numpy as np
from pydantic import StrictFloat, StrictInt

from .field_contracts import EntitySelection
from .gui_mesh import (
    ReadOnlyScopeMismatch,
    check_same_nodes,
    check_same_parts,
    mesh_index,
    verify_mesh_digest,
)
from .native import commands as nc


def mesh_signature(state):
    """Bind selection buffers to the model actually read, not a mutable title."""
    if "mesh_digest" in state:
        verify_mesh_digest(state, state)
        canonical = dict(contract=state["digest_contract"], counts=state["counts"],
                         parts=state["part_ids"], **{key: state["mesh_digest"][key]
                         for key in ("node_ids", "coordinates", "connectivity", "part_membership")})
        return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
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
    if "mesh_digest" in state:
        return set(state["registry_matches"])
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


def part_visibility(state):
    """Require complete native part flags before a display-preserving selection."""
    flags = state.get("part_visibility")
    if (
        not isinstance(flags, dict)
        or set(flags) != {str(uid) for uid in state["part_ids"]}
        or any(type(value) is not bool for value in flags.values())
    ):
        raise ValueError(
            "Complete native part visibility is required; start a new GUI session for the updated bridge"
        )
    return flags


def verify_selection(before, after, expected, kind):
    if "mesh_digest" in before or "mesh_digest" in after:
        verify_mesh_digest(before, after)
    old_nodes, old_elements = mesh_index(before)
    new_nodes, new_elements = mesh_index(after)
    check_same_nodes(old_nodes, new_nodes)
    check_same_parts(before, after)
    if old_elements != new_elements:
        raise ValueError("Selection unexpectedly changed connectivity")
    if before.get("current_state") != after.get("current_state"):
        raise ReadOnlyScopeMismatch("Result state changed during selection; pause animation before retrying")
    if part_visibility(before) != part_visibility(after):
        raise ReadOnlyScopeMismatch("Native part visibility changed during selection")
    visibility = before.get("visibility_binary")
    if visibility is not None and visibility != after.get("visibility_binary"):
        raise ReadOnlyScopeMismatch("Native entity display-active flags changed during selection")
    actual = after.get("selection_ids")
    if actual is None or len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise ReadOnlyScopeMismatch("Native selected IDs differ from the requested set")
    return dict(
        entity_type=kind,
        selected_ids=sorted(expected),
        selected_count=len(expected),
        geometry_unchanged=True,
        model_scope="current managed model",
        model_kind=before.get("model_kind", "keyword"),
        coordinate_configuration="reference",
        native_current_state=after.get("current_state"),
        validity_scope="registered entities accepted by native selection; no explicit alive/deletion mask",
        selection_spec=EntitySelection(kind, sorted(expected)).describe(),
        part_visibility_preserved=True,
        entity_display_active_preserved=None if before.get("auxiliary_elements") else visibility is not None,
        structural_display_active_preserved=visibility is not None,
        display_check_scope="Current part configuration and registered shell/solid/beam flags; auxiliary mass glyph flags unverified; display-active is not physical erosion",
    )


def hidden_parts_only(state):
    """Allow the existing part reveal plan only with current native readback.

    A hidden part can still contain Blank members; exact selected-ID and display
    verification below must succeed before publishing any successful result.
    """
    visibility = state.get("visibility_binary") or {}
    plan = state.get("native_selection_plan") or {}
    return (plan.get("strategy") in ("whole", "parts")
            and visibility.get("inactive_in_visible_parts") == 0
            and any(not active for active in part_visibility(state).values()))


class GuiSelectionTools:
    def _select_gui(
        self, session_id, action, arguments, kind, choose, suffix=None, on_verified=None, part_selection=None,
        snapshot_parameters=None, prepare_snapshot=None, source_verification=None,
    ):
        expected = set()
        strategy = {}
        target = "element" if kind in ("solid", "beam") else kind

        def precheck(state):
            part_visibility(state)
            if prepare_snapshot is not None and state.get("query_selected_ids") is None:
                raise ValueError("Start a new GUI session for resolved set-selection registry queries; refusing whole-scope fallback")
            topology = (state.get("native_selection_plan") or {}).get("strategy") == "topology"
            if snapshot_parameters and snapshot_parameters.get("topology_query") and not topology:
                raise ValueError("Start a new GUI session for the topology-query bridge")
            if topology and state.get("model_kind") != "keyword":
                raise ValueError("Topology selection currently requires a keyword model; deformed-result propagation is not verified")
            if topology and state.get("topology_error"):
                raise ValueError(state["topology_error"])
            if "mesh_digest" in state and state.get("visibility_binary") is None:
                raise ValueError("Restart the GUI session to enable selection display-state verification")
            available = available_ids(state, kind)
            expected.update(state["query_selected_ids"] if state.get("query_selected_ids") is not None else choose(state))
            EntitySelection(kind, sorted(expected))
            if not expected <= available or len(expected) > state.get("selection_limit", 20000):
                raise ValueError("Selection is outside the current entity registry or verification bound")
            visibility = state.get("visibility_binary")
            if visibility and visibility.get("active_count", 0) < visibility["count"] and len(expected) > 20000 and not topology and not hidden_parts_only(state):
                raise ValueError("Hidden entities require exact-ID selection (20,000 selected-ID budget); narrow the scope or explicitly show entities first")

        def commands(state, directory):
            # pall also clears per-element Blank flags. Reveal only hidden parts;
            # +m/-m retains those flags, as checked by native mixed-domain tests.
            plan = state.get("native_selection_plan")
            topology = plan and plan.get("strategy") == "topology"
            result = [] if topology else ["+m " + pid for pid, active in part_visibility(state).items() if not active]
            result += [nc.selection('clear'), nc.selection_target(target)]
            visibility = state.get("visibility_binary")
            if visibility and visibility.get("active_count", 0) < visibility["count"] and not topology and not hidden_parts_only(state):
                # Whole/by-part native selection omits Blank members in 4.13.
                # Explicit IDs preserve the declared registered-entity semantics.
                plan = None
            if plan:
                if plan["target"] != target:
                    raise ValueError("Native bulk-selection plan targets the wrong domain")
                if topology:
                    result += [nc.selection_propagation(False), nc.selection_propagation(False, adaptive=True), nc.selection_surface(False)]
                    if plan["mode"] == "propagate":
                        result += [nc.feature_angle(plan['feature_angle']), nc.selection_propagation(True)]
                    result += [nc.selection_add('shell', uid, 'shell') for uid in plan["seed_ids"]]
                    if plan["mode"] == "adjacent":
                        result += [nc.selection('adjacent')] * plan["rings"]
                    result.append(nc.selection_propagation(False))
                elif plan["strategy"] == "whole":
                    result.append(nc.selection('whole'))
                else:
                    result += [nc.selection_add(target, pid, 'part') for pid in plan["part_ids"]]
                strategy["name"] = "native_" + plan["strategy"] + "_streamed_verification"
            elif "mesh_digest" in state:
                result += [nc.selection_add(target, uid, target) for uid in sorted(expected)]
                strategy["name"] = "explicit_ids_streamed_verification"
            elif expected and expected == available_ids(state, target):
                result.append(nc.selection('whole'))
                strategy["name"] = "native_whole"
            elif part_selection is not None and expected == in_parts(state, target, part_selection):
                result += [nc.selection_add(target, pid, 'part') for pid in part_selection]
                strategy["name"] = "native_part"
            else:
                result += [nc.selection_add(target, uid, target) for uid in sorted(expected)]
                strategy["name"] = "explicit_ids"
            restore = ["-m " + pid for pid, active in part_visibility(state).items() if not active]
            return result + (suffix or []) + restore

        return self._gui_mesh_edit(
            session_id,
            action,
            arguments,
            commands,
            lambda a, b: dict(
                **verify_selection(a, b, expected, kind),
                command_strategy=strategy["name"],
                selection_scope=arguments.get("scope", "all"),
                **(source_verification or {}),
            ),
            precheck,
            on_verified=on_verified,
            transaction_kind="selection",
            snapshot_parameters=dict(snapshot_parameters or {}, visibility_readback=True),
            **({"prepare_snapshot": prepare_snapshot} if prepare_snapshot is not None else {}),
        )

    def select_gui_shell_topology(self, session_id: str, seed_ids: list[StrictInt], mode: str = "propagate",
                                  feature_angle: StrictFloat | None = None, rings: StrictInt | None = None,
                                  scope: str = "visible") -> dict:
        """Native visible keyword-shell topology selection: adjacent grows shared-node rings; propagate follows shared edges with local unoriented normal-angle threshold. Independent graph checks exact IDs and preserves geometry/part/Blank/state. Tri3/Quad4; visible shells only, up to1m scope/selection. Reversed normals do not block smooth propagation. Deformed-result/adaptive propagation is unverified. Leaves propagation/adaptive/3dsurf off and the requested angle setting."""
        from .post_backend import ids

        ids(seed_ids, "seed_ids", 1000)
        if scope != "visible":
            raise ValueError("Topology selection currently supports the visible shell scope")
        if mode not in ("adjacent", "propagate"):
            raise ValueError("Topology mode is adjacent or propagate")
        if mode == "propagate" and rings is not None or mode == "adjacent" and feature_angle is not None:
            raise ValueError("feature_angle applies only to propagate; rings applies only to adjacent")
        resolved_rings = 1 if rings is None else rings
        angle = 30. if feature_angle is None else feature_angle
        if type(resolved_rings) is not int or not 1 <= resolved_rings <= 100:
            raise ValueError("Topology mode is adjacent/propagate; rings must be1..100")
        if type(angle) not in (int, float) or not math.isfinite(angle) or not 0 < angle <= 180:
            raise ValueError("Feature angle must be in (0,180] degrees")
        query = dict(seed_ids=list(seed_ids), mode=mode, rings=resolved_rings, feature_angle=float(angle))
        arguments = dict(seed_ids=list(seed_ids), mode=mode, rings=rings, feature_angle=feature_angle, scope=scope)
        return self._select_gui(session_id, "select_gui_shell_topology", arguments, "shell",
                                lambda state: set(), snapshot_parameters=dict(entity_type="shell", topology_query=query))

    def select_gui_entities(
        self,
        session_id: str,
        entity_type: str,
        entity_ids: list[int] | None = None,
        part_ids: list[int] | None = None,
        invert: bool = False,
        scope: str = "all",
        set_ids: list[int] | None = None,
    ) -> dict:
        """Select keyword/d3plot entities with streamed geometry/exact ID checks and preserved display/state. Choose entity_ids, part_ids or set_ids. set_ids unions current same-domain explicit-list node/part/shell/solid/beam sets in a keyword model, using an isolated native export under the selection lock; at most20000 union members, unknown variants reject. all includes hidden parts/orphans; active_parts intersects displayed-part connectivity; invert is within that scope. No filter means whole scope; entity_ids=[] clears. Whole/part bulk plans can exceed20000 within existing1m readback bounds. No physical alive mask, arbitrary set expansion or screen/deformed picking."""
        from .post_backend import ids

        if entity_type not in ("node", "shell", "solid", "beam", "element", "part"):
            raise ValueError("Unsupported entity selection type")
        if sum(v is not None for v in (entity_ids, part_ids, set_ids)) > 1:
            raise ValueError("Choose explicit IDs, a part filter or set_ids")
        source_verification = {}
        prepare_snapshot = None
        if set_ids is not None:
            from .set_selection import prepare_set_selection

            ids(set_ids, "set_ids", 1000)
            if entity_type == "element":
                raise ValueError("set_ids requires an explicit node/part/shell/solid/beam domain")
            prepare_snapshot = prepare_set_selection(entity_type, set_ids, source_verification)
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
        if scope not in ("all", "active_parts"):
            raise ValueError("Selection scope must be all or active_parts")

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
            eligible = (
                available
                if scope == "all"
                else in_parts(
                    state, entity_type, [int(pid) for pid, active in part_visibility(state).items() if active]
                )
            )
            return eligible - selected if invert else selected & eligible

        return self._select_gui(
            session_id,
            "select_gui_entities",
            dict(
                entity_type=entity_type, entity_ids=entity_ids, part_ids=part_ids, invert=invert, scope=scope,
                **({"set_ids": set_ids} if set_ids is not None else {}),
            ),
            entity_type,
            choose,
            part_selection=part_ids if not invert else None,
            snapshot_parameters=dict(entity_type=entity_type, registry_query=dict(
                entity_ids=entity_ids, part_ids=part_ids, invert=invert, scope=scope)),
            prepare_snapshot=prepare_snapshot, source_verification=source_verification,
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
            snapshot_parameters=dict(entity_type=entity_type, entity_ids=sorted(left | right)),
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
            [nc.selection_buffer('save', index), nc.selection('clear'), nc.selection_buffer('load', index)],
            on_verified=remember,
            snapshot_parameters=dict(entity_type=entity_type, entity_ids=entity_ids),
        )

    def load_gui_selection_buffer(self, session_id: str, slot: int) -> dict:
        """Replace current selection from an owned verified native buffer. Reject stale model fingerprints; detect manual buffer replacement by native readback. Reopening or editing a model requires saving the slot again."""
        index = buffer_slot(slot)
        manager = self._session_manager()
        initial = manager.read(session_id).get("selection_buffers", {}).get(str(slot))
        if initial is None:
            raise ValueError("No verified native selection buffer in this session")
        entry = {}

        def precheck(state):
            part_visibility(state)
            if "mesh_digest" in state and state.get("visibility_binary") is None:
                raise ValueError("Restart the GUI session to enable selection display-state verification")
            saved = manager.read(session_id).get("selection_buffers", {}).get(str(slot))
            if saved is None:
                raise ValueError("No verified native selection buffer in this session")
            if saved != initial:
                raise ValueError("Selection buffer metadata changed before the operation")
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
                nc.selection('clear'),
                nc.selection_target(entry['entity_type']),
                nc.selection_buffer('load', index),
            ],
            lambda a, b: verify_selection(a, b, entry["entity_ids"], entry["entity_type"]),
            precheck,
            transaction_kind="selection",
            snapshot_parameters=dict(entity_type=initial["entity_type"], entity_ids=initial["entity_ids"],
                                     visibility_readback=True),
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
            snapshot_parameters=dict(selection_query=dict(kind="plane", point=point,
                direction=direction.tolist(), side=side, tolerance=tolerance)),
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
        if not np.isfinite(lower).all() or not np.isfinite(upper).all():
            raise ValueError("Expanded box bounds exceed finite numeric range")

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
            snapshot_parameters=dict(selection_query=dict(kind="box", lower=lower.tolist(),
                upper=upper.tolist(), inside=inside)),
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
        if not math.isfinite(radius + tolerance):
            raise ValueError("Expanded sphere radius exceeds finite numeric range")

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
            snapshot_parameters=dict(selection_query=dict(kind="sphere", center=center,
                radius=radius + tolerance, inside=inside)),
        )
