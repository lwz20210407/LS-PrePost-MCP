"""Isolated LS-Reader worker. Run only with a configured ABI-compatible Python."""
import csv
import json
import math
import os
import sys
import traceback


def main():
    request = json.load(open(sys.argv[1], encoding="utf-8"))
    response = {"job_id": request["job_id"], "ok": False}
    try:
        from lsreader import D3plotReader
        from lsreader import DataType as dt
        source = request["source"]
        os.chdir(os.path.dirname(source))
        reader = D3plotReader(source)
        ids = [int(x) for x in reader.get_data(dt.D3P_NODE_IDS)]
        times = [float(t) for t in reader.get_data(dt.D3P_TIMES)]
        if request["action"] == "inspect":
            data = {"backend": "lsreader", "node_count": len(ids), "state_count": len(times),
                    "state_times": times[:10000], "node_id_preview": ids[:20], "python_version": sys.version}
        elif request["action"] == "nodal":
            p = request["parameters"]
            quantity = {"displacement": dt.D3P_NODE_DISPLACEMENTS, "velocity": dt.D3P_NODE_VELOCITIES}[p["quantity"]]
            lookup = {uid: i for i, uid in enumerate(ids)}
            if any(uid not in lookup for uid in p["node_ids"]):
                raise ValueError("Unknown user node ID")
            rows = []
            for state in p["states"]:
                if not 1 <= state <= len(times):
                    raise ValueError("State outside database")
                vectors = reader.get_data(quantity, ist=state-1)
                if len(vectors) != len(ids):
                    raise ValueError("Node/result array mismatch")
                for uid in p["node_ids"]:
                    vector = vectors[lookup[uid]]
                    xyz = [float(vector.x()), float(vector.y()), float(vector.z())]
                    rows.append([state, times[state-1], uid] + xyz + [math.sqrt(sum(v*v for v in xyz))])
            with open(request["output_csv"], "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["state", "time", "node_id", "x", "y", "z", "magnitude"])
                w.writerows(rows)
            data = {"backend": "lsreader", "row_count": len(rows), "public_state_base": 1,
                    "native_state_base": 0, "id_kind": "user"}
        else:
            raise ValueError("Unsupported LS-Reader action")
        response.update(ok=True, data=data)
    except Exception as exc:
        response["error"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(response, f, indent=2, ensure_ascii=False, allow_nan=False)


if __name__ == "__main__":
    main()

