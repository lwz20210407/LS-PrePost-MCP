"""Bundled application-side bridge. Keep compatible with embedded Python 3.6+.

Only this module executes inside LS-PrePost; no user Python is evaluated.
"""

import csv
import json
import math
import os
import sys
import traceback


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
            if action == "probe":
                data["sdk_functions"] = [name for name in dir(lp) if not name.startswith("_")]
        elif action == "scl_probe":
            with open("scl_nodes.txt") as f:
                scl_nodes = int(f.read().strip())
            python_nodes = int(get("num_nodes"))
            if scl_nodes != python_nodes:
                raise ValueError("SCL and Python counters disagree")
            data = {"scl_nodes": scl_nodes, "python_nodes": python_nodes, "match": True}
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
