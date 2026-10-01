"""Bundled application-side bridge. Keep compatible with embedded Python 3.6+.

Only this module executes inside LS-PrePost; no user Python is evaluated.
"""

import csv
import hashlib
import json
import math
import os
import struct
import sys
import traceback
from array import array as packed_array


def scoped_mesh_state(dc, lp, parameters):
    """Stream complete native geometry fingerprints, materialize only requested nodes.

    This remains O(model size) work: unchanged entities are checked, not sampled.
    Native SDK arrays may be transient, so consume each before the next SDK call.
    """
    wanted_nodes = parameters.get("node_ids", [])
    wanted_ids = parameters.get("entity_ids", [])
    domain = parameters.get("entity_type", "node")
    query = parameters.get("selection_query")
    registry_query = parameters.get("registry_query")
    if registry_query and (query or wanted_nodes or wanted_ids):
        raise ValueError("Registry query cannot be combined with explicit digest scopes")
    if query and (domain != "node" or wanted_nodes or wanted_ids or query.get("kind") not in ("box", "sphere", "plane")):
        raise ValueError("Spatial queries require node domain and no explicit IDs")
    if domain not in ("node", "shell", "solid", "beam", "element", "part"):
        raise ValueError("Unsupported scoped entity domain")
    for values in (wanted_nodes, wanted_ids):
        if (not isinstance(values, list) or len(values) > 20000
                or any(type(v) is not int or v <= 0 for v in values)
                or len(values) != len(set(values))):
            raise ValueError("Scoped IDs must be unique positive integers, at most20000")
    wanted_nodes, wanted_ids = set(wanted_nodes), set(wanted_ids)
    hashes = {key: hashlib.sha256() for key in (
        "node_ids", "coordinates", "unselected_coordinates", "connectivity", "part_membership")}
    node_indices, rows, matched, occurrences = {}, {}, [], {}
    get = dc.get_data
    array = get("validpart_ids")
    parts = [int(array[i]) for i in range(len(array))]
    visibility, filter_elements, active_elements = {}, set(), set()
    requested_parts = registry_query.get("part_ids") if registry_query else None
    if requested_parts is not None and not set(requested_parts) <= set(parts):
        raise ValueError("Unknown part ID")
    for pid in parts:
        visibility[str(pid)] = bool(lp.check_if_part_is_active_u(pid))
        array = get("elemofpart_ids", type=1, id=pid)
        hashes["part_membership"].update(struct.pack("!qq", pid, len(array)))
        for i in range(len(array)):
            eid = int(array[i])
            hashes["part_membership"].update(struct.pack("!q", eid))
            if registry_query:
                if requested_parts is not None and pid in requested_parts:
                    filter_elements.add(eid)
                if visibility[str(pid)]:
                    active_elements.add(eid)
        if domain == "part" and pid in wanted_ids:
            matched.append(pid)
    domain_ids, filter_ids, active_ids, both_ids, seen_elements = set(), set(), set(), set(), set()
    registry = get("node_ids")
    count = len(registry)
    query_ids = packed_array("q") if query else None
    accum = packed_array("d", [0.0]) * count if query else None
    for i in range(count):
        uid = int(registry[i])
        if registry_query and domain == "node":
            domain_ids.add(uid)
        if query:
            query_ids.append(uid)
        hashes["node_ids"].update(struct.pack("!q", uid))
        if uid in wanted_nodes:
            if uid in rows:
                raise ValueError("Duplicate requested native node ID")
            node_indices[i] = uid
            rows[uid] = [uid]
        if domain == "node" and uid in wanted_ids:
            matched.append(uid)
    if set(rows) != wanted_nodes:
        raise ValueError("Unknown requested node IDs")
    for axis, key in enumerate(("node_x", "node_y", "node_z")):
        array = get(key, type=dc.Type.NODE)
        if len(array) != count:
            raise ValueError("Native node coordinate count differs from registry")
        for start in range(0, count, 1024):
            whole, unchanged = bytearray(), bytearray()
            for i in range(start, min(count, start + 1024)):
                value = float(array[i])
                if not math.isfinite(value):
                    raise ValueError("Nonfinite native reference coordinate")
                if query:
                    if query["kind"] == "box":
                        if not query["lower"][axis] <= value <= query["upper"][axis]:
                            accum[i] = 1.0
                    elif query["kind"] == "sphere":
                        accum[i] = math.hypot(accum[i], value - query["center"][axis])
                    else:
                        accum[i] += (value - query["point"][axis]) * query["direction"][axis]
                    if not math.isfinite(accum[i]):
                        raise ValueError("Spatial predicate exceeds finite numeric range")
                packed = struct.pack("!d", value)
                whole.extend(packed)
                if i in node_indices:
                    rows[node_indices[i]].append(value)
                else:
                    unchanged.extend(packed)
            hashes["coordinates"].update(whole)
            hashes["unselected_coordinates"].update(unchanged)
    if query:
        for i, value in enumerate(accum):
            if query["kind"] == "box":
                chosen = (value == 0) == query["inside"]
            elif query["kind"] == "sphere":
                chosen = (value <= query["radius"]) == query["inside"]
            else:
                chosen = (abs(value) <= query["tolerance"] if query["side"] == "band" else
                          value > query["tolerance"] if query["side"] == "positive" else
                          value < -query["tolerance"])
            if chosen:
                matched.append(query_ids[i])
                if len(matched) > 20000:
                    raise ValueError("Spatial selection exceeds20000 selected nodes per operation; narrow the region. This is not a global model-size limit")
    element_count, affected_count, affected = 0, 0, []
    for label, kind in (("shell", dc.Type.SHELL), ("solid", dc.Type.SOLID), ("beam", dc.Type.BEAM)):
        # Materialize only domain IDs: a new SDK call may invalidate the array.
        # Coordinates/connectivity are never retained for unrequested entities.
        array = get("element_ids", type=kind)
        eids = [int(array[i]) for i in range(len(array))]
        hashes["connectivity"].update(label.encode("ascii") + struct.pack("!q", len(eids)))
        for uid in eids:
            array = get("element_connectivity", type=kind, id=uid)
            conn = [int(array[i]) for i in range(len(array))]
            hashes["connectivity"].update(struct.pack("!qq", uid, len(conn)))
            hashes["connectivity"].update(struct.pack("!" + "q" * len(conn), *conn))
            element_count += 1
            if registry_query:
                needs_unique = domain not in ("node", "part") or (domain == "node" and
                    (requested_parts is not None or registry_query["scope"] == "active_parts"))
                if needs_unique and uid in seen_elements:
                    raise ValueError("Part-aware selection requires globally unique element IDs")
                seen_elements.add(uid)
                if domain == "node":
                    if uid in filter_elements:
                        filter_ids.update(n for n in conn if n)
                    if uid in active_elements:
                        active_ids.update(n for n in conn if n)
                    if uid in filter_elements and uid in active_elements:
                        both_ids.update(n for n in conn if n)
                elif domain in (label, "element"):
                    domain_ids.add(uid)
                    if uid in filter_elements:
                        filter_ids.add(uid)
                    if uid in active_elements:
                        active_ids.add(uid)
            if wanted_nodes.intersection(conn):
                affected_count += 1
                if len(affected) < 20:
                    affected.append(dict(type=label, id=uid))
            if uid in wanted_ids and domain not in ("node", "part"):
                occurrences[uid] = occurrences.get(uid, 0) + 1
                if domain in (label, "element"):
                    matched.append(uid)
    if element_count != int(get("num_elements")):
        raise ValueError("Scoped verification does not cover this model's element types")
    if any(n > 1 for n in occurrences.values()):
        raise ValueError("Requested element IDs are ambiguous across native domains")
    native_plan, selection_limit = None, 20000
    if registry_query:
        if domain == "node" and (not filter_ids <= domain_ids or not active_ids <= domain_ids):
            raise ValueError("Part connectivity refers to an unregistered node")
        if domain == "part":
            domain_ids = set(parts)
            filter_ids = set(requested_parts or [])
            active_ids = {pid for pid in parts if visibility[str(pid)]}
        explicit = registry_query.get("entity_ids")
        if explicit is not None and not set(explicit) <= domain_ids:
            raise ValueError("Unknown selected entity IDs")
        candidates = set(explicit) if explicit is not None else filter_ids if requested_parts is not None else domain_ids
        eligible = domain_ids if registry_query["scope"] == "all" else active_ids
        selected_set = eligible - candidates if registry_query["invert"] else candidates & eligible
        target = "element" if domain in ("solid", "beam") else domain
        whole_domain = domain in ("node", "part", "shell", "element") or len(domain_ids) == element_count
        if selected_set and selected_set == domain_ids and whole_domain:
            native_plan = dict(strategy="whole", target=target)
        elif domain != "part" and explicit is None and not registry_query["invert"]:
            chosen_parts = parts if requested_parts is None else requested_parts
            if registry_query["scope"] == "active_parts":
                chosen_parts = [pid for pid in chosen_parts if visibility[str(pid)]]
            # Whole-scope node selection includes orphans, so only use part
            # commands when connectivity precisely defines the requested scope.
            if domain == "node":
                bulk_ids = (both_ids if requested_parts is not None and registry_query["scope"] == "active_parts" else
                            filter_ids if requested_parts is not None else active_ids)
            else:
                bulk_ids = (filter_elements & active_elements if requested_parts is not None and registry_query["scope"] == "active_parts" else
                            filter_elements if requested_parts is not None else active_elements if registry_query["scope"] == "active_parts" else seen_elements)
            if selected_set == bulk_ids and (domain != "node" or requested_parts is not None or registry_query["scope"] == "active_parts"):
                native_plan = dict(strategy="parts", target=target, part_ids=chosen_parts)
        selection_limit = 1000000 if native_plan else 20000
        if len(selected_set) > selection_limit:
            raise ValueError("Selected set exceeds the command/readback budget for this operation; this is not a global model-size limit")
        matched = sorted(selected_set)
    if not query and not registry_query and (set(matched) != wanted_ids or len(matched) != len(wanted_ids)):
        raise ValueError("Requested IDs are absent or duplicated in the native entity registry")
    selection_count = int(get("num_selection"))
    selected = None
    if selection_count <= selection_limit:
        array = get("selection_ids", type=0)
        selected = [int(array[i]) for i in range(len(array))]
        if len(selected) != selection_count:
            raise ValueError("Native selection count differs from selected-ID readback")
    return dict(
        nodes=[rows[k] for k in sorted(rows)], elements=[],
        part_ids=parts, part_visibility=visibility, selection_ids=selected,
        selection_types=None, registry_matches=matched,
        query_selected_ids=matched if query or registry_query else None,
        native_selection_plan=native_plan, selection_limit=selection_limit,
        affected_element_count=affected_count, affected_element_sample=affected,
        mesh_digest={key: value.hexdigest() for key, value in hashes.items()},
        digest_contract="native_registry_order_sha256_v1",
        digest_node_ids=sorted(wanted_nodes),
        verification_scope="All reference coordinates/connectivity/part membership streamed; only requested nodes materialized",
    )


def run(request_path, response_path):
    request = json.load(open(request_path, encoding="utf-8"))
    response = {"job_id": request["job_id"], "ok": False}
    try:
        import DataCenter as dc
        import LsPrePost as lp

        action = request["action"]
        p = request["parameters"]
        if action in ("extract_nodal", "node_history") and sys.version_info[:2] < (3, 10):
            raise RuntimeError(
                "Native vector arrays on the older embedded Python ABI did not pass numerical cross-checks. Use the explicit LASSO/LS-Reader tools or the verified 4.13 profile."
            )
        job_directory = request.get("job_directory", os.getcwd())
        if request.get("model"):
            # The application may reset cwd from GUI preferences. Load file families
            # from their parent, then restore the owned job cwd for every artifact.
            source = request["model"]
            os.chdir(os.path.dirname(source))
            try:
                kind = request["file_type"]
                opener = "openc" if kind == "d3plot" else "open"
                load_name = (
                    source.replace("\\", "/")
                    if kind == "keyword" and request.get("absolute_keyword_path")
                    else os.path.basename(source)
                )
                lp.execute_command(opener + " " + kind + ' "' + load_name + '"')
            finally:
                os.chdir(job_directory)
            if int(dc.get_data("num_nodes")) <= 0:
                raise ValueError("Input did not load a nonempty finite-element model")

        def get(key, **kw):
            return dc.get_data(key, **kw)

        def sequence(value):
            return [value[i] for i in range(len(value))]

        def inventory():
            data = {
                "python_version": sys.version,
                "python_executable": sys.executable,
                "python_prefix": sys.prefix,
                "warnings": [],
                "counts": {},
            }
            aliases = {
                "nodes": ["num_nodes"],
                "elements": ["num_elements", "num_elem"],
                "states": ["num_states"],
            }
            for label, names in aliases.items():
                for key in names:
                    try:
                        data["counts"][label] = int(get(key))
                        break
                    except Exception:
                        pass
                else:
                    data["warnings"].append("Unavailable counter: " + label)
            try:
                data["part_ids"] = sequence(get("validpart_ids"))
            except Exception:
                data["part_ids"] = []
            try:
                data["state_times"] = sequence(get("state_times"))
            except Exception:
                data["state_times"] = []
            try:
                data["current_state"] = int(get("current_state"))
            except Exception:
                data["current_state"] = None
            return data

        def check_state(state):
            count = int(get("num_states"))
            if not 1 <= state <= count:
                raise ValueError("Native state must be 1..%s" % count)

        def node_rows(ids, keys, state):
            if state is not None:
                check_state(state)
                lp.switch_state(state)
            all_ids = sequence(get("node_ids"))
            lookup = {int(uid): i for i, uid in enumerate(all_ids)}
            missing = [uid for uid in ids if uid not in lookup]
            if missing:
                raise ValueError("Unknown user node IDs: " + str(missing[:20]))
            # Older bindings may expose application-owned buffers. Materialize
            # each component before the next native call can reuse its memory.
            arrays = [
                sequence(dc.get_data(key, dc.Type.NODE, **({"ist": state} if state else {}))) for key in keys
            ]
            if any(len(a) != len(all_ids) for a in arrays):
                raise ValueError("Node IDs and result array lengths differ")
            return [[uid] + [float(a[lookup[uid]]) for a in arrays] for uid in ids]

        if action in ("probe", "inspect_model"):
            data = inventory()
            if p.get("include_display_scope"):
                data["part_visibility"] = {str(int(pid)): bool(lp.check_if_part_is_active_u(int(pid))) for pid in data["part_ids"]}
                data["selection_count"] = int(get("num_selection"))
            if action == "probe":
                data["sdk_functions"] = [name for name in dir(lp) if not name.startswith("_")]
        elif action == "scl_probe":
            with open("scl_nodes.txt") as f:
                scl_nodes = int(f.read().strip())
            python_nodes = int(get("num_nodes"))
            if scl_nodes != python_nodes:
                raise ValueError("SCL and Python counters disagree")
            data = {"scl_nodes": scl_nodes, "python_nodes": python_nodes, "match": True}
        elif action == "gui_mesh_digest":
            data = inventory()
            data.update(scoped_mesh_state(dc, lp, p))
        elif action == "gui_mesh_page":
            label, offset, limit = p["entity_type"], p["offset"], p["limit"]
            if label not in ("node", "shell", "solid", "beam"):
                raise ValueError("Unsupported mesh page entity_type")
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 5000:
                raise ValueError("Invalid mesh page bounds")
            data = inventory()
            kind = {"node": dc.Type.NODE, "shell": dc.Type.SHELL,
                    "solid": dc.Type.SOLID, "beam": dc.Type.BEAM}[label]
            registry = get("node_ids") if label == "node" else get("element_ids", type=kind)
            total = len(registry)
            end = min(total, offset + limit)
            selected = [int(registry[i]) for i in range(offset, end)]
            if label == "node":
                # Native coordinate arrays are whole-domain buffers, but only
                # the requested slice is materialized before another SDK call.
                arrays = []
                for key in ("node_x", "node_y", "node_z"):
                    values = get(key, type=kind)
                    if len(values) != total:
                        raise ValueError("Native node coordinate length differs from registry")
                    arrays.append([float(values[i]) for i in range(offset, end)])
                rows = [[uid] + [a[i] for a in arrays] for i, uid in enumerate(selected)]
                data["nodes"] = rows
            else:
                data["elements"] = [
                    {"type": label, "id": uid,
                     "nodes": [int(n) for n in sequence(get("element_connectivity", type=kind, id=uid))]}
                    for uid in selected
                ]
            data.update(entity_type=label, offset=offset, limit=limit, total=total,
                        returned=len(selected), next_offset=end if end < total else None,
                        id_kind="user", coordinate_configuration="reference",
                        snapshot_scope="one locked native request; no cross-page atomicity")
        elif action == "gui_mesh_state":
            data = inventory()
            if max(data["counts"].get("nodes", 0), data["counts"].get("elements", 0)) > 20000:
                raise ValueError("GUI mesh verification currently supports at most 20000 nodes/elements")
            node_ids = [int(x) for x in sequence(get("node_ids"))]
            data["nodes"] = node_rows(node_ids, ["node_x", "node_y", "node_z"], None)
            elements = []
            for label, kind in [("shell", dc.Type.SHELL), ("solid", dc.Type.SOLID), ("beam", dc.Type.BEAM)]:
                for eid in sequence(get("element_ids", type=kind)):
                    elements.append({"type": label, "id": int(eid),
                                     "nodes": [int(n) for n in sequence(get("element_connectivity", type=kind, id=int(eid)))]})
            if len(elements) != data["counts"].get("elements"):
                raise ValueError("GUI mesh snapshot does not cover this model's element types")
            data["elements"] = elements
            data["part_elements"] = {str(int(pid)): [int(eid) for eid in sequence(get("elemofpart_ids", type=1, id=int(pid)))] for pid in data["part_ids"]}
            data["part_visibility"] = {str(int(pid)): bool(lp.check_if_part_is_active_u(int(pid))) for pid in data["part_ids"]}
            try:
                data["selection_ids"] = [int(x) for x in sequence(get("selection_ids", type=0))]
                # This binding returned invalid pointer-like integers for the
                # selection_types array in a real 4.13 GUI check. Do not expose
                # those values as verified entity type codes.
                data["selection_types"] = None
            except Exception:
                data["selection_ids"] = None
                data["selection_types"] = None
        elif action == "list_nodes":
            ids = sequence(get("node_ids"))
            selected = [int(x) for x in ids[p["offset"] : p["offset"] + p["limit"]]]
            rows = node_rows(selected, ["node_x", "node_y", "node_z"], None)
            data = {
                "total": len(ids),
                "coordinate_configuration": "reference",
                "columns": ["node_id", "x", "y", "z"],
                "rows": rows,
            }
        elif action == "list_parts":
            ids = sequence(get("validpart_ids"))
            parts = []
            for uid in ids[: p["limit"]]:
                item = {"part_id": int(uid)}
                try:
                    item["name"] = str(get("part_name", id=int(uid)))
                except Exception:
                    item["name"] = None
                parts.append(item)
            data = {"total": len(ids), "parts": parts}
        elif action == "connectivity":
            kind = {"shell": dc.Type.SHELL, "solid": dc.Type.SOLID, "beam": dc.Type.BEAM}[p["element_type"]]
            nodes = sequence(get("element_connectivity", type=kind, id=p["element_id"]))
            if not nodes:
                raise ValueError("No connectivity returned for the requested element")
            data = {
                "element_id": p["element_id"],
                "element_type": p["element_type"],
                "node_ids": nodes,
                "id_kind": "user",
            }
        elif action in ("extract_nodal", "node_history"):
            mapping = {
                "displacement": ["disp_x", "disp_y", "disp_z"],
                "velocity": ["velo_x", "velo_y", "velo_z"],
                "position": ["state_node_x", "state_node_y", "state_node_z"],
            }
            keys = mapping[p["quantity"]]
            states = [p["state"]] if action == "extract_nodal" else p["states"]
            times = sequence(get("state_times"))
            rows = []
            if p.get("preserve_state"):
                lp.execute_command("anim stop")
            initial_state = int(get("current_state")) if p.get("preserve_state") else None
            if initial_state is not None:
                check_state(initial_state)
            try:
                for state in states:
                    check_state(state)
                    if state > len(times):
                        raise ValueError("Missing physical state time")
                    for row in node_rows(p["node_ids"], keys, state):
                        rows.append([state, float(times[state - 1])] + row)
            finally:
                if initial_state is not None:
                    lp.switch_state(initial_state)
            if p["quantity"] != "position":
                for row in rows:
                    row.append(math.sqrt(sum(v * v for v in row[-3:])))
            columns = ["state", "time", "node_id", "x", "y", "z"]
            if p["quantity"] != "position":
                columns.append("magnitude")
            if any(not math.isfinite(float(v)) for row in rows for v in row):
                raise ValueError("Nonfinite native nodal result/time")
            components = p.get("curve_components", [])
            if components:
                selected_times = [float(times[state - 1]) for state in states]
                if len(selected_times) < 2 or any(a >= b for a, b in zip(selected_times, selected_times[1:])):
                    raise ValueError("Scalar curves require strictly increasing physical time")
            with open(os.path.join(job_directory, "nodal.csv"), "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)
            curves = []
            for uid in (p["node_ids"] if components else []):
                samples = [row for row in rows if row[2] == uid]
                for component in components:
                    filename = "node_%d_%s.csv" % (uid, component)
                    column = columns.index(component)
                    with open(os.path.join(job_directory, filename), "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(["time", "value"])
                        writer.writerows([[row[1], row[column]] for row in samples])
                    curves.append({"node_id": uid, "component": component,
                                   "quantity": p["quantity"], "units": p["units"],
                                   "time_unit": p.get("time_unit"), "row_count": len(samples),
                                   "path": os.path.join(job_directory, filename)})
            data = {
                "quantity": p["quantity"],
                "columns": columns,
                "row_count": len(rows),
                "states": states,
                "units": p["units"],
                "id_kind": "user",
                "preview": rows[:20],
                "field_spec": p.get("field_spec"),
                "curves": curves,
                "original_state": initial_state,
                "state_restore_requested": initial_state is not None,
                "state_restored": False,
                "animation_policy": "stopped; not automatically resumed" if initial_state is not None else "unchanged",
            }
        elif action == "create_plate":
            nx, ny = p["nx"], p["ny"]
            ox, oy, oz = p["origin"]
            lx, ly = p["size"]
            coords = [ox, oy, oz, ox + lx, oy, oz, ox + lx, oy + ly, oz, ox, oy + ly, oz]
            lp.execute_command("meshing 4pshell create %d %d " % (nx, ny) + " ".join(str(x) for x in coords))
            lp.execute_command(
                "meshing 4pshell accept %d %d %d plate" % (p["part_id"], p["element_start"], p["node_start"])
            )
            data = inventory()
            if (
                data["counts"].get("nodes") != (nx + 1) * (ny + 1)
                or data["counts"].get("elements") != nx * ny
            ):
                raise ValueError("Native mesh counts do not match the requested plate")
            data["units"] = p["units"]
        elif action == "create_box":
            nx, ny, nz = p["divisions"]
            lower = p["origin"]
            upper = [lower[i] + p["size"][i] for i in range(3)]
            lp.execute_command(
                "meshing boxsolid create "
                + " ".join(str(v) for v in lower + upper)
                + " %d %d %d 0.0" % (nx, ny, nz)
            )
            lp.execute_command(
                "meshing boxsolid accept %d %d %d boxsolid"
                % (p["part_id"], p["element_start"], p["node_start"])
            )
            data = inventory()
            if (
                data["counts"].get("nodes") != (nx + 1) * (ny + 1) * (nz + 1)
                or int(get("num_solid_elements")) != nx * ny * nz
            ):
                raise ValueError("Native box mesh counts differ from requested divisions")
            data["units"] = p["units"]
        elif action == "create_sphere":
            try:
                before = set(int(v) for v in sequence(get("node_ids")))
                old_parts = set(int(v) for v in sequence(get("validpart_ids")))
            except Exception:
                before, old_parts = set(), set()
            if p["part_id"] in old_parts:
                raise ValueError("Sphere part ID already exists")
            lp.execute_command(
                "meshing spheresolid create "
                + " ".join(str(v) for v in p["center"])
                + " %s %d 1 0 0 0 1 0" % (p["radius"], p["divisions"])
            )
            lp.execute_command("meshing spheresolid accept %d" % p["part_id"])
            ids = [int(v) for v in sequence(get("node_ids"))]
            created = [v for v in ids if v not in before]
            if not created or len(ids) != len(set(ids)):
                raise ValueError("Sphere did not create a unique node registry")
            rows = node_rows(created, ["node_x", "node_y", "node_z"], None)
            radii = [math.sqrt(sum((row[i + 1] - p["center"][i]) ** 2 for i in range(3))) for row in rows]
            if abs(max(radii) - p["radius"]) > max(1e-6, p["radius"] * 1e-5):
                raise ValueError("Sphere mesh extent differs from requested radius")
            data = inventory()
            data.update(created_node_count=len(created), maximum_radius=max(radii), units=p["units"])
        elif action == "rotate_nodes":
            ids = [int(v) for v in sequence(get("node_ids"))]
            selected = set(p["node_ids"])
            if not selected.issubset(set(ids)):
                raise ValueError("Unknown node ID")
            before = node_rows(ids, ["node_x", "node_y", "node_z"], None)
            lp.execute_command("genselect clear")
            lp.execute_command("genselect target node")
            lp.execute_command("genselect transfer 0")
            for uid in p["node_ids"]:
                lp.execute_command("genselect node add node %d" % uid)
            lp.execute_command(
                "rotate_model " + " ".join(str(v) for v in p["center"]) + " %s %s" % (p["axis"], p["angle"])
            )
            lp.execute_command("rotate_model accept 0 0 0")
            lp.execute_command("genselect clear")
            after = node_rows(ids, ["node_x", "node_y", "node_z"], None)
            angle = math.radians(p["angle"])
            cos, sin = math.cos(angle), math.sin(angle)
            axis = {"x": 0, "y": 1, "z": 2}[p["axis"]]
            a, b = (axis + 1) % 3, (axis + 2) % 3
            max_error = 0.0
            for old, new in zip(before, after):
                expected = old[1:]
                if old[0] in selected:
                    qa, qb = expected[a] - p["center"][a], expected[b] - p["center"][b]
                    expected[a] = p["center"][a] + cos * qa - sin * qb
                    expected[b] = p["center"][b] + sin * qa + cos * qb
                for i in range(3):
                    error = abs(new[i + 1] - expected[i])
                    max_error = max(max_error, error)
                    if error > max(1e-6, abs(expected[i]) * 1e-5):
                        raise ValueError("Native rotation coordinate verification failed")
            data = {
                "rotated_nodes": len(selected),
                "axis": p["axis"],
                "angle_degrees": p["angle"],
                "maximum_coordinate_error": max_error,
            }
        elif action == "translate_nodes":
            all_ids = [int(v) for v in sequence(get("node_ids"))]
            if len(all_ids) > 1000000:
                raise ValueError("Translation verification is limited to one million nodes")
            selected = set(p["node_ids"])
            if not selected.issubset(set(all_ids)):
                raise ValueError("Requested user node ID does not exist")
            before = node_rows(all_ids, ["node_x", "node_y", "node_z"], None)
            lp.execute_command("genselect clear")
            lp.execute_command("genselect target node")
            for uid in p["node_ids"]:
                lp.execute_command("genselect node add node %d" % uid)
            lp.execute_command("translate_model " + " ".join(str(v) for v in p["offset"]))
            lp.execute_command("translate_model accept")
            lp.execute_command("genselect clear")
            after_ids = [int(v) for v in sequence(get("node_ids"))]
            if after_ids != all_ids:
                raise ValueError("Translation unexpectedly changed the node ID registry")
            after = node_rows(all_ids, ["node_x", "node_y", "node_z"], None)
            max_error = 0.0
            for old, new in zip(before, after):
                expected = [old[i + 1] + (p["offset"][i] if old[0] in selected else 0) for i in range(3)]
                for i in range(3):
                    error = abs(new[i + 1] - expected[i])
                    max_error = max(max_error, error)
                    if error > max(1e-7, abs(expected[i]) * 1e-6):
                        raise ValueError("Native translation changed an unexpected coordinate")
            data = {
                "translated_nodes": len(selected),
                "verified_nodes": len(all_ids),
                "max_coordinate_error": max_error,
                "units": p["units"],
                "verification": "All selected and unselected coordinates checked before save",
            }
        elif action == "move_elements_to_part":
            kind = {"shell": dc.Type.SHELL, "solid": dc.Type.SOLID, "beam": dc.Type.BEAM}[p["element_type"]]
            before_ids = [int(v) for v in sequence(get("element_ids", type=kind))]
            if not set(p["element_ids"]).issubset(set(before_ids)):
                raise ValueError("Requested user element ID not found")
            for other_kind in (dc.Type.SHELL, dc.Type.SOLID, dc.Type.BEAM):
                if other_kind != kind:
                    other_ids = set(int(v) for v in sequence(get("element_ids", type=other_kind)))
                    if set(p["element_ids"]) & other_ids:
                        raise ValueError(
                            "Generic native selector is ambiguous: selected ID also occurs in another element type"
                        )
            before_nodes = int(get("num_nodes"))
            before_elements = int(get("num_elements"))
            lp.execute_command("genselect clear")
            lp.execute_command("genselect target element")
            for uid in p["element_ids"]:
                lp.execute_command("genselect element add element %d" % uid)
            lp.execute_command('elemmove apply %d "mcp_part"' % p["part_id"])
            lp.execute_command("elemmove accept %d" % p["part_id"])
            lp.execute_command("genselect clear")
            moved = set(int(v) for v in sequence(get("elemofpart_ids", type=1, id=p["part_id"])))
            if not set(p["element_ids"]).issubset(moved):
                raise ValueError("Native target part does not contain requested element IDs")
            if int(get("num_nodes")) != before_nodes or int(get("num_elements")) != before_elements:
                raise ValueError("Part reassignment changed mesh counts")
            data = {
                "element_type": p["element_type"],
                "element_ids": p["element_ids"],
                "part_id": p["part_id"],
                "verification": "Target part membership and mesh counts checked; target material/section requires explicit configuration",
            }
        elif action == "extrude_shell":
            part_ids = [int(v) for v in sequence(get("validpart_ids"))]
            shell_count = int(get("num_shell_elements"))
            if part_ids != [p["part_id"]] or shell_count != int(get("num_elements")):
                raise ValueError("Initial extrusion adapter requires a single shell-only part")
            if shell_count * p["layers"] > 100000:
                raise ValueError("Extrusion exceeds 100000 solid elements")
            before_shells = [int(v) for v in sequence(get("element_ids", type=dc.Type.SHELL))]
            z = [float(v) for v in sequence(get("node_z"))]
            if max(z) - min(z) > 1e-8:
                raise ValueError("Initial extrusion adapter requires a planar XY shell mesh")
            lp.execute_command("genselect clear")
            lp.execute_command("genselect target shell")
            lp.execute_command("genselect shell add part %d" % p["part_id"])
            lp.execute_command(
                "elgenerate solid shelldrag 2 0 %s %d 0 0 0 0 0 10000" % (p["length"], p["layers"])
            )
            lp.execute_command("genselect clear")
            lp.execute_command("elgenerate accept")
            data = inventory()
            data["solid_count"] = int(get("num_solid_elements"))
            solid_ids = [int(v) for v in sequence(get("element_ids", type=dc.Type.SOLID))]
            if len(solid_ids) != len(set(solid_ids)) or before_shells != [
                int(v) for v in sequence(get("element_ids", type=dc.Type.SHELL))
            ]:
                raise ValueError("Extrusion changed source shell IDs or produced duplicate solid IDs")
            if data["solid_count"] != shell_count * p["layers"]:
                raise ValueError("Extrusion did not create expected number of solids")
            after_z = [float(v) for v in sequence(get("node_z"))]
            if abs((max(after_z) - min(after_z)) - p["length"]) > max(1e-6, p["length"] * 1e-6):
                raise ValueError("Extrusion extent does not match requested length")
            data.update(units=p["units"], source_shells_retained=True, z_extent=max(after_z) - min(after_z))
        elif action == "gui_new":
            with open("initial.k", "w") as f:
                f.write("*KEYWORD\n*TITLE\nMCP session model\n*END\n")
            lp.execute_command(
                'open keyword "' + os.path.join(job_directory, "initial.k").replace("\\", "/") + '"'
            )
            data = inventory()
        elif action == "gui_display":
            if p.get("state") is not None:
                check_state(p["state"])
                lp.execute_command("anim stop")
                lp.switch_state(p["state"])
            for command in p["commands"]:
                lp.execute_command(command)
            if p.get("capture"):
                output = os.path.join(job_directory, "snapshot.png").replace("\\", "/")
                lp.execute_command('print png "' + output + '" opaque enlisted "OGL1x1"')
            data = inventory()
            data["applied_commands"] = p["commands"]
        elif action == "gui_parts":
            valid = [int(v) for v in sequence(get("validpart_ids"))]
            if not set(p["part_ids"]).issubset(set(valid)):
                raise ValueError("Unknown part IDs")
            before = {uid: bool(lp.check_if_part_is_active_u(uid)) for uid in valid}
            if p["mode"] == "all":
                lp.execute_command("pall")
            elif p["mode"] == "isolate":
                lp.execute_command("m " + ",".join(str(v) for v in p["part_ids"]))
            else:
                prefix = "+m " if p["mode"] == "show" else "-m "
                for uid in p["part_ids"]:
                    lp.execute_command(prefix + str(uid))
            after = {uid: bool(lp.check_if_part_is_active_u(uid)) for uid in valid}
            expected = dict(before)
            if p["mode"] in ("all", "isolate"):
                expected = {uid: (p["mode"] == "all" or uid in p["part_ids"]) for uid in valid}
            else:
                for uid in p["part_ids"]:
                    expected[uid] = p["mode"] == "show"
            if after != expected:
                raise ValueError("Native part visibility did not match requested state")
            data = {"visibility": after, "mode": p["mode"], "verified": True}
        elif action == "gui_animation":
            if p["operation"] == "stop":
                lp.execute_command("anim stop")
            else:
                check_state(p["first"])
                check_state(p["last"])
                lp.execute_command("anim first %d" % p["first"])
                lp.execute_command("anim last %d" % p["last"])
                lp.execute_command("anim incr %d" % p["increment"])
                lp.execute_command("anim " + p["direction"])
                lp.execute_command("anim start")
            data = {
                "operation": p["operation"],
                "configuration": p,
                "verification": "Native commands submitted; use current_state/captured frames to observe playback",
            }
        elif action == "render_snapshot":
            if p.get("state") is not None:
                check_state(p["state"])
                lp.switch_state(p["state"])
            if p.get("fringe_code") is not None:
                lp.execute_command("fringe " + str(p["fringe_code"]))
                lp.execute_command("pfringe")
            lp.execute_command(p["view"])
            lp.execute_command("ac")
            output = os.path.join(job_directory, "snapshot.png").replace("\\", "/")
            lp.execute_command('print png "' + output + '" opaque enlisted "OGL1x1"')
            data = {
                "view": p["view"],
                "state": p.get("state"),
                "fringe_code": p.get("fringe_code"),
                "note": "Image validation does not establish physical result correctness",
            }
        elif action == "export_keyword":
            data = inventory()
        elif action == "raw_command":
            lp.execute_command(p["command"])
            os.chdir(job_directory)
            data = inventory()
            for key, expected in p["expected_counts"].items():
                if data["counts"].get(key) != expected:
                    raise ValueError("Raw command count verification failed: " + key)
            data["command"] = p["command"]
            data["verification_scope"] = "Inventory and declared outputs only; raw command semantics are user-defined"
        elif action == "measure_parts":
            valid = set(int(x) for x in sequence(get("validpart_ids")))
            if not set(p["part_ids"]).issubset(valid):
                raise ValueError("Unknown user part ID")
            rows = []
            for uid in p["part_ids"]:
                lp.execute_command("measure vol part %d" % uid)
                values = [lp.cmd_result_get_value(i) for i in range(lp.cmd_result_get_value_count())]
                if not values:
                    raise ValueError("Native measurement returned no values")
                rows.append({"part_id": uid, "command_values": values})
            data = {
                "measurements": rows,
                "note": "Raw command-result layout is build-dependent; values are not assigned guessed units",
            }
        else:
            raise ValueError("Unsupported bridge action: " + action)
        response.update(ok=True, data=data)
    except Exception as exc:
        response.update(
            error={"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        )
    with open(response_path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(response, f, ensure_ascii=False, indent=2, allow_nan=False)
    os.replace(response_path + ".tmp", response_path)
