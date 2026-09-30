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
            raise RuntimeError("Native vector arrays on the older embedded Python ABI did not pass numerical cross-checks. Use the explicit LASSO/LS-Reader tools or the verified 4.13 profile.")
        job_directory = request.get("job_directory", os.getcwd())
        if request.get("model"):
            # The application may reset cwd from GUI preferences. Load file families
            # from their parent, then restore the owned job cwd for every artifact.
            source = request["model"]
            os.chdir(os.path.dirname(source))
            try:
                kind = request["file_type"]
                opener = "openc" if kind == "d3plot" else "open"
                lp.execute_command(opener + " " + kind + ' "' + os.path.basename(source) + '"')
            finally:
                os.chdir(job_directory)
            if int(dc.get_data("num_nodes")) <= 0:
                raise ValueError("Input did not load a nonempty finite-element model")

        def get(key, **kw):
            return dc.get_data(key, **kw)

        def sequence(value):
            return [value[i] for i in range(len(value))]

        def inventory():
            data = {"python_version": sys.version, "python_executable": sys.executable,
                    "python_prefix": sys.prefix, "warnings": [], "counts": {}}
            aliases = {"nodes": ["num_nodes"], "elements": ["num_elements", "num_elem"],
                       "states": ["num_states"]}
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
            arrays = [sequence(dc.get_data(key, dc.Type.NODE, **({"ist": state} if state else {}))) for key in keys]
            if any(len(a) != len(all_ids) for a in arrays):
                raise ValueError("Node IDs and result array lengths differ")
            return [[uid] + [float(a[lookup[uid]]) for a in arrays] for uid in ids]

        if action in ("probe", "inspect_model"):
            data = inventory()
        elif action == "scl_probe":
            with open("scl_nodes.txt") as f:
                scl_nodes = int(f.read().strip())
            python_nodes = int(get("num_nodes"))
            if scl_nodes != python_nodes:
                raise ValueError("SCL and Python counters disagree")
            data = {"scl_nodes": scl_nodes, "python_nodes": python_nodes, "match": True}
        elif action == "list_nodes":
            ids = sequence(get("node_ids"))
            selected = [int(x) for x in ids[p["offset"]:p["offset"] + p["limit"]]]
            rows = node_rows(selected, ["node_x", "node_y", "node_z"], None)
            data = {"total": len(ids), "coordinate_configuration": "reference", "columns": ["node_id", "x", "y", "z"], "rows": rows}
        elif action == "list_parts":
            ids = sequence(get("validpart_ids"))
            parts = []
            for uid in ids[:p["limit"]]:
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
            data = {"element_id": p["element_id"], "element_type": p["element_type"], "node_ids": nodes, "id_kind": "user"}
        elif action in ("extract_nodal", "node_history"):
            mapping = {"displacement": ["disp_x", "disp_y", "disp_z"],
                       "velocity": ["velo_x", "velo_y", "velo_z"],
                       "position": ["state_node_x", "state_node_y", "state_node_z"]}
            keys = mapping[p["quantity"]]
            states = [p["state"]] if action == "extract_nodal" else p["states"]
            times = sequence(get("state_times"))
            rows = []
            for state in states:
                check_state(state)
                if state > len(times):
                    raise ValueError("Missing physical state time")
                for row in node_rows(p["node_ids"], keys, state):
                    rows.append([state, float(times[state - 1])] + row)
            if p["quantity"] != "position":
                for row in rows:
                    row.append(math.sqrt(sum(v*v for v in row[-3:])))
            columns = ["state", "time", "node_id", "x", "y", "z"]
            if p["quantity"] != "position":
                columns.append("magnitude")
            with open("nodal.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)
            data = {"quantity": p["quantity"], "columns": columns, "row_count": len(rows),
                    "states": states, "units": p["units"], "id_kind": "user", "preview": rows[:20]}
        elif action == "create_plate":
            nx, ny = p["nx"], p["ny"]
            ox, oy, oz = p["origin"]
            lx, ly = p["size"]
            coords = [ox, oy, oz, ox+lx, oy, oz, ox+lx, oy+ly, oz, ox, oy+ly, oz]
            lp.execute_command("meshing 4pshell create %d %d " % (nx, ny) + " ".join(str(x) for x in coords))
            lp.execute_command("meshing 4pshell accept %d %d %d plate" % (p["part_id"], p["element_start"], p["node_start"]))
            data = inventory()
            if data["counts"].get("nodes") != (nx+1)*(ny+1) or data["counts"].get("elements") != nx*ny:
                raise ValueError("Native mesh counts do not match the requested plate")
            data["units"] = p["units"]
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
            data = {"view": p["view"], "state": p.get("state"), "fringe_code": p.get("fringe_code"),
                    "note": "Image validation does not establish physical result correctness"}
        elif action == "export_keyword":
            data = inventory()
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
            data = {"measurements": rows, "note": "Raw command-result layout is build-dependent; values are not assigned guessed units"}
        else:
            raise ValueError("Unsupported bridge action: " + action)
        response.update(ok=True, data=data)
    except Exception as exc:
        response.update(error={"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
    with open(response_path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(response, f, ensure_ascii=False, indent=2, allow_nan=False)
    os.replace(response_path + ".tmp", response_path)
