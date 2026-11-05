"""One explicitly leased 4.13 headless diagnostic; raw ids_inset is never reinterpreted."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import psutil

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model.includes import is_network
from ls_prepost_mcp.engine.environment import locate_config
from ls_prepost_mcp.native.versions import require_installation
from ls_prepost_mcp.service import Service
from tools.native_regression import execution_identity

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {101: [37, 121], 202: [11, 37, 89], 303: [11, 37, 89, 121]}
DECK = """*KEYWORD
*NODE
11,0,0,0
37,1,0,0
89,2,0,0
121,3,0,0
*SET_NODE_LIST
101
121,37
*SET_NODE_LIST_GENERATE
202
0,100
*SET_NODE_ADD
303
101,202
*END
"""
PROGRAM = '''import json
import math
import sys
import DataCenter as dc

result = {"role": "diagnostic_raw_not_user_id_claim", "python_version": list(sys.version_info[:2]), "sets": []}
try:
    if sys.version_info[:2] < (3, 10):
        raise RuntimeError("Vector ABI has not been verified for this runtime")
    result["node_count"] = dc.get_data("num_nodes")
    result["type_expression"] = "DataCenter.Type.NODE"
    result["type_repr"] = repr(dc.Type.NODE)
    for sid in (101, 202, 303):
        row = {"requested_sid": sid}
        try:
            vector = dc.get_data("ids_inset", type=dc.Type.NODE, id=sid)
            values = list(vector)  # Own every returned scalar before any next SDK call.
            row["returned_type"] = type(vector).__name__
            row["raw_scalar_types"] = [type(value).__name__ for value in values]
            row["raw_representations"] = [repr(value) for value in values]
            if all(type(value) in (int, float, str, bool, type(None)) and
                   (type(value) is not float or math.isfinite(value)) for value in values):
                row["raw_json_values"] = values
            else:
                row["raw_json_values"] = None
        except Exception as error:
            row["error"] = {"type": type(error).__name__, "message": str(error)}
        result["sets"].append(row)
except Exception as error:
    result["error"] = {"type": type(error).__name__, "message": str(error)}
with open("sets-raw.json", "w") as stream:
    json.dump(result, stream, allow_nan=False)
'''


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def native_processes():
    return [dict(pid=process.pid, name=process.info["name"]) for process in psutil.process_iter(["name"])
            if (process.info["name"] or "").lower().startswith(("lsprepost", "lspost", "lspp"))]


def pilot(executable, output):
    context = execution_identity(ROOT)
    if context["working_tree_dirty"] is not False or not context["actual_git_head"]:
        raise ValueError("Diagnostic requires a clean committed product/producer/expected checkout")
    if is_network(str(output)) or not output.is_absolute():
        raise ValueError("Use an explicit local absolute output directory")
    output = output.resolve()
    if output.exists() or output.is_relative_to(ROOT):
        raise ValueError("Use a fresh external output directory")
    if native_processes():
        raise ValueError("LS-PrePost already running; no implicit acquisition of a second lease")
    profile = require_installation(executable)
    if (profile["version"] != "4.13" or profile["version_source"] != "file_version_resource"
            or profile["resource_conflict"]):
        raise ValueError("This named diagnostic is authorized only for the installed 4.13 resource profile")
    config = locate_config(executable, os.environ)
    if config is None:
        raise ValueError("Initialized native configuration is required")
    output.mkdir(parents=True)
    source = output / "single.k"
    source.write_text(DECK, encoding="ascii", newline="\n")
    before = dict(input=sha(source), executable=sha(executable), configuration=sha(config))
    service = Service(Settings(output / "work", executable, (output,), timeout=30))
    proof = dict(role="one_named_field_diagnostic_not_P04_L2", actual_git_revision=context["actual_git_head"],
        working_tree_dirty=context["working_tree_dirty"], git_diff_sha256=context["git_diff_sha256"],
        git_diff_scope=context["git_diff_scope"], profile=profile, producer_sha256=sha(Path(__file__)),
        script_sha256=hashlib.sha256(PROGRAM.encode()).hexdigest(), expected=EXPECTED, before=before,
        graphics=False, solver_executed=False)
    try:
        prepared = service.prepare_native_program("python", code=PROGRAM,
            outputs=[dict(name="sets-raw.json", kind="json")], expected_counts=dict(nodes=4))
        result = service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"],
                                                model=str(source), file_type="keyword")
        proof["result"] = result
        raw_path = Path(result["job_directory"]) / "sets-raw.json"
        if raw_path.is_file():
            raw = json.loads(raw_path.read_text(encoding="utf8"))
            proof.update(raw=raw, raw_sha256=sha(raw_path))
            proof["diagnostic_matches_expected_user_id_sets"] = {
                str(row["requested_sid"]): (sorted(row["raw_json_values"]) == EXPECTED[row["requested_sid"]]
                    if isinstance(row.get("raw_json_values"), list) and
                    all(type(value) is int for value in row["raw_json_values"]) else None)
                for row in raw["sets"]}
    finally:
        proof["identity_guards"] = dict(input_unchanged=sha(source) == before["input"],
            executable_unchanged=sha(executable) == before["executable"], configuration_unchanged=sha(config) == before["configuration"])
        proof["live_native_after"] = native_processes()
        (output / "diagnostic.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps(proof, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pilot(args.executable, args.output)
