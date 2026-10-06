"""Bounded absolute-coordinate corrections using verified native GUI transforms."""

import math

import numpy as np

from .core.validation import integer, unit_label
from .gui_mesh import check_same_parts, mesh_index, verify_mesh_digest
from .gui_selection import part_visibility
from .native import commands as nc


def verify_coordinates(before, after, targets, tolerance):
    if "mesh_digest" in before or "mesh_digest" in after:
        verify_mesh_digest(before, after, allow_selected_coordinates=True)
        if set(before["digest_node_ids"]) != set(targets):
            raise ValueError("Coordinate verification excludes the wrong node set")
    old, old_elements = mesh_index(before)
    actual, actual_elements = mesh_index(after)
    if old.keys() != actual.keys() or old_elements != actual_elements:
        raise ValueError("Coordinate editing changed node IDs or element connectivity")
    check_same_parts(before, after)
    if part_visibility(before) != part_visibility(after):
        raise ValueError("Coordinate editing did not restore part visibility")
    maximum_error = 0.0
    for uid, xyz in old.items():
        if uid not in targets:
            if not np.array_equal(actual[uid], xyz):
                raise ValueError("Coordinate editing changed an unrequested node")
            continue
        error = float(np.max(np.abs(actual[uid] - targets[uid])))
        if error > tolerance:
            raise ValueError("Absolute coordinate target exceeds the explicit tolerance")
        maximum_error = max(error, maximum_error)
    affected = [
        dict(type=kind, id=eid) for (kind, eid), conn in old_elements.items() if set(conn) & targets.keys()
    ]
    return dict(
        requested_node_ids=sorted(targets),
        requested_count=len(targets),
        changed_count=sum(not np.array_equal(old[uid], actual[uid]) for uid in targets),
        maximum_coordinate_error=maximum_error,
        absolute_tolerance=tolerance,
        affected_element_count=before.get("affected_element_count", len(affected)),
        affected_element_sample=before.get("affected_element_sample", affected[:20]),
        all_connectivity_preserved=True,
        unrequested_nodes_preserved=True,
        part_visibility_preserved=True,
        scope="Absolute global node coordinates and original topology; mesh quality/loads/material axes require separate checks",
    )


def set_coordinates(service, session_id, nodes, units, tolerance):

    unit_label(units)
    if type(tolerance) not in (int, float) or not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("A positive finite absolute coordinate tolerance is required")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 100:
        raise ValueError("Coordinate correction accepts 1..100 node rows")
    updates = {}
    for row in nodes:
        if not isinstance(row, dict) or set(row) != {"id", "coordinates"}:
            raise ValueError("Each node requires id and coordinates")
        uid, values = integer(row["id"], "node id"), row["coordinates"]
        if uid in updates:
            raise ValueError("Duplicate node ID")
        if not isinstance(values, list) or len(values) != 3 or all(v is None for v in values):
            raise ValueError("Coordinates require three axes and at least one numeric target")
        if any(v is not None and (type(v) not in (int, float) or not math.isfinite(v)) for v in values):
            raise ValueError("Coordinates must be finite numbers or null; booleans are not coordinates")
        updates[uid] = tuple(values)
    targets, groups = {}, {}

    def precheck(state):
        old, _ = mesh_index(state)
        part_visibility(state)
        if not updates.keys() <= old.keys():
            raise ValueError("Unknown node IDs")
        for uid, values in updates.items():
            target = np.asarray([old[uid][i] if v is None else v for i, v in enumerate(values)], float)
            delta = target - old[uid]
            if not np.isfinite(delta).all():
                raise ValueError("Native translation exceeds finite coordinate range")
            targets[uid] = target
            if np.any(delta):
                groups.setdefault(tuple(delta), []).append(uid)

    def commands(state, directory):
        result = ["pall", nc.selection('clear'), nc.selection_target('node'), nc.selection_transfer(0)]
        for delta, uids in groups.items():
            result.extend(nc.selection_add('node', uid, 'node') for uid in uids)
            result.extend(
                [
                    "translate_model " + " ".join(str(float(v)) for v in delta),
                    "translate_model accept",
                    nc.selection('clear'),
                ]
            )
        result.extend("-m " + pid for pid, active in part_visibility(state).items() if not active)
        return result

    arguments = dict(
        nodes=[dict(id=uid, coordinates=list(values)) for uid, values in updates.items()],
        units=units,
        tolerance=tolerance,
    )
    return service._gui_mesh_edit(
        session_id,
        "set_gui_node_coordinates",
        arguments,
        commands,
        lambda before, after: verify_coordinates(before, after, targets, tolerance),
        precheck,
        snapshot_parameters=dict(node_ids=sorted(updates)),
    )
