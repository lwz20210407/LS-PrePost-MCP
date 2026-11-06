"""P04 owned-fixture native membership, using an observed reversible ID mapping.

This is a verification producer for one observed executable and owned fixture,
not a general node-set reader. The explicit one-based storage rule is admitted
only after full native registry/rank and reversible-ID checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model.includes import is_network
from ls_prepost_mcp.engine.environment import locate_config
from ls_prepost_mcp.native.versions import require_installation
from ls_prepost_mcp.service import Service
from tools.native_regression import execution_identity
from tools.probe_node_set_ids_native import native_processes, sha

ROOT = Path(__file__).resolve().parents[1]
NODE_IDS = (11, 37, 89, 121)
VERIFIED_BINARY_SHA256 = "ce76fdf75a2f14c0a3e94964809ddd178934d04381f7f31e1e1eb05592bd5414"
# The oracle is hand-written, never obtained from NodeSets or native output.
EXPECTED = {101: [121, 37], 202: [11, 37, 89], 303: [121, 37, 11, 89]}
SOURCE = "*KEYWORD\n*NODE\n11,0,0,0\n37,1,0,0\n89,2,0,0\n121,3,0,0\n*END\n"
OPERATIONS = [
    dict(op="create_set", kind="node", sid=101, ids=[121, 37]),
    dict(op="create_set", kind="node", sid=202, representation="generate", ranges=[[0, 100]]),
    dict(op="create_set", kind="node", sid=303, representation="add", set_ids=[101, 202]),
]
PRODUCT_PATHS = (
    "src/ls_prepost_mcp/service.py", "src/ls_prepost_mcp/programs.py",
    "src/ls_prepost_mcp/domain/model/deck.py", "src/ls_prepost_mcp/domain/model/fields.py",
    "src/ls_prepost_mcp/domain/model/layouts.py", "src/ls_prepost_mcp/domain/model/node_sets.py",
    "src/ls_prepost_mcp/domain/model/sets.py", "src/ls_prepost_mcp/domain/model/operations.py",
    "src/ls_prepost_mcp/domain/model/matching.py", "src/ls_prepost_mcp/domain/model/_identity.py",
    "src/ls_prepost_mcp/model_target_tools.py", "src/ls_prepost_mcp/domain/model/contact_report.py",
    "src/ls_prepost_mcp/domain/model/contact.py",
)

PROGRAM = '''import json
import sys
import DataCenter as dc

proof = {"protocol": "named_node_id_roundtrip_v1", "python_version": list(sys.version_info[:2]),
         "mapping": [], "sets": []}
try:
    if sys.version_info[:2] < (3, 10):
        raise RuntimeError("Vector ABI has not been verified for this runtime")
    count = dc.get_data("num_nodes")
    if type(count) is not int or count != 4:
        raise ValueError("Owned fixture must have exactly four nodes")
    # Copy immediately: the SDK may reuse a vector on the next get_data call.
    registry = list(dc.get_data("node_ids"))
    if any(type(v) is not int for v in registry) or sorted(registry) != [11, 37, 89, 121]:
        proof["invalid_registry_repr"] = repr(registry)
        raise ValueError("Native registry differs from the independent four-node oracle")
    proof["node_ids"] = registry
    seen = set()
    for ordinal, uid in enumerate(sorted(registry)):
        internal = dc.get_data("internal_id", type=dc.Type.NODE, id=uid)
        # Never pass a negative or out-of-fixture index into another native call.
        if type(internal) is not int or internal != ordinal or internal in seen:
            proof["failed_mapping"] = {"user_id": uid, "internal_repr": repr(internal)}
            raise ValueError("Native internal IDs do not match the independently sorted complete registry")
        seen.add(internal)
        returned = dc.get_data("user_id", type=dc.Type.NODE, id=internal)
        if type(returned) is not int or returned != uid:
            proof["failed_mapping"] = {"user_id": uid, "internal_id": internal, "roundtrip_repr": repr(returned)}
            raise ValueError("Named native ID roundtrip failed; no index arithmetic is allowed")
        proof["mapping"].append({"user_id": uid, "internal_id": internal, "roundtrip_user_id": returned})
    for sid in (101, 202, 303):
        values = list(dc.get_data("ids_inset", type=dc.Type.NODE, id=sid))
        if any(type(v) is not int for v in values):
            proof["invalid_members_repr"] = repr(values)
            raise ValueError("Raw native set vector contains a noninteger")
        proof["sets"].append({"sid": sid, "raw_ids_inset": values})
except Exception as error:
    proof["error"] = {"type": type(error).__name__, "message": str(error)}
with open("node-set-identities.json", "w") as stream:
    json.dump(proof, stream, allow_nan=False)
'''


def _integers(values, label):
    if not isinstance(values, list) or any(type(v) is not int for v in values) or len(values) != len(set(values)):
        raise ValueError(label + " must be a list of unique integer IDs")
    return values


def validate(raw):
    """Fail closed unless an independent full-registry roundtrip defines every key."""
    if not isinstance(raw, dict) or raw.get("protocol") != "named_node_id_roundtrip_v1" or raw.get("error"):
        raise ValueError("Native identity capture failed: " + str(raw.get("error") if isinstance(raw, dict) else raw))
    registry = _integers(raw.get("node_ids"), "Native registry")
    if sorted(registry) != list(NODE_IDS):
        raise ValueError("Native node registry is incomplete or changed")
    mappings = raw.get("mapping")
    if not isinstance(mappings, list) or len(mappings) != len(NODE_IDS):
        raise ValueError("Native identity mapping is incomplete")
    inverse, users = {}, set()
    for row in mappings:
        if not isinstance(row, dict) or set(row) != {"user_id", "internal_id", "roundtrip_user_id"}:
            raise ValueError("Malformed native mapping record")
        uid, internal, returned = (row[k] for k in ("user_id", "internal_id", "roundtrip_user_id"))
        if (any(type(v) is not int for v in (uid, internal, returned)) or uid not in NODE_IDS
                or uid in users or internal + 1 in inverse or internal != NODE_IDS.index(uid) or returned != uid):
            raise ValueError("Native mapping is not an exact bijection with a successful roundtrip")
        users.add(uid)
        # Static evidence for this executable: keyword NODE-set lookup returns
        # a one-based sorted-record rank; its fallback is node_lookup(...)+1.
        # Requiring every native internal_id to equal that sorted rank minus
        # one makes both paths identical in THIS complete four-node fixture.
        # Do not reuse this as an unconditional production numbering adapter.
        inverse[internal + 1] = uid
    if users != set(NODE_IDS):
        raise ValueError("Native mapping does not cover the independent registry")
    sets = raw.get("sets")
    if not isinstance(sets, list) or len(sets) != len(EXPECTED):
        raise ValueError("Native set capture is incomplete")
    result, seen = [], set()
    for row in sets:
        if not isinstance(row, dict) or set(row) != {"sid", "raw_ids_inset"}:
            raise ValueError("Malformed native set record")
        sid = row["sid"]
        if type(sid) is not int or sid not in EXPECTED or sid in seen:
            raise ValueError("Native set IDs are unknown or repeated")
        seen.add(sid)
        values = _integers(row["raw_ids_inset"], "Raw ids_inset")
        if any(v not in inverse for v in values):
            raise ValueError("Raw set member has no independently verified native inverse")
        converted = [inverse[v] for v in values]
        if sorted(converted) != sorted(EXPECTED[sid]):
            raise ValueError("Native membership differs from the hand-written oracle for " + str(sid))
        result.append(dict(sid=sid, raw_ids_inset=values, native_user_ids=converted,
                           expected_user_ids=EXPECTED[sid], membership_equal=True,
                           definition_order_equal=converted == EXPECTED[sid]))
    return dict(status="passed", mapping_method="one-based keyword set slot after complete native sorted-rank/ID roundtrip validation",
                registry_user_ids=registry, mapping=mappings, sets=result,
                scope="Four-node single-file LIST/GENERATE/ADD membership; ordering is reported separately")


def _directory(path):
    result = {}
    for item in path.iterdir():
        metadata = item.lstat()
        if item.is_symlink() or getattr(metadata, "st_file_attributes", 0) & 0x400:
            raise ValueError("Owned fixture directory contains an unexpected link")
        result[item.name] = dict(kind="directory") if item.is_dir() else dict(kind="file", sha256=sha(item))
    return result


def source_identity(identity):
    """Admit all selected products from the actual full snapshot before native/configuration IO."""
    captured = identity.get("source_files")
    if not isinstance(captured, dict):
        raise ValueError("Missing required P04 capture source hashes")
    for path in PRODUCT_PATHS:
        digest = captured.get(path)
        if (not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or not (ROOT / path).is_file() or sha(ROOT / path) != digest):
            raise ValueError("Missing or changed required P04 capture source: " + path)
    revision = identity.get("actual_git_head", "")
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("Missing committed P04 capture source revision")
    return [dict(path=path, git_blob_id=subprocess.check_output(
        ["git", "rev-parse", revision + ":" + path], cwd=ROOT, text=True, timeout=10).strip(),
        captured_file_sha256=captured[path]) for path in PRODUCT_PATHS]


def run(executable, output):
    """A single owned, serial, opt-in headless process through the existing APIs."""
    identity = execution_identity(ROOT)
    if not identity.get("actual_git_head") or identity["working_tree_dirty"] is not False:
        raise ValueError("A clean committed producer and product checkout is required")
    products = source_identity(identity)
    if not output.is_absolute() or is_network(str(output)) or output.exists() or output.resolve().is_relative_to(ROOT):
        raise ValueError("Use a fresh, local, absolute output directory outside the checkout")
    if native_processes():
        raise ValueError("Native process already running; acquire the serial lease first")
    profile = require_installation(executable, version="4.13")
    if profile["version_source"] != "file_version_resource" or profile["resource_conflict"]:
        raise ValueError("This vector diagnostic requires an unambiguous 4.13 version resource")
    config = locate_config(executable, os.environ)
    if config is None:
        raise ValueError("An initialized native configuration is required")
    before = dict(executable=sha(executable), configuration=sha(config))
    if before["executable"] != VERIFIED_BINARY_SHA256:
        raise ValueError("The keyword-set storage contract is verified only for the recorded executable SHA256")
    output.mkdir(parents=True)
    source_dir = output / "source"
    source_dir.mkdir()
    source = source_dir / "main.k"
    source.write_text(SOURCE, encoding="ascii", newline="\n")
    original = _directory(source_dir)
    service = Service(Settings(output / "work", executable, (output,), timeout=30))
    created = service.create_entities(str(source), OPERATIONS)
    if created["status"] != "succeeded":
        raise ValueError("Fixture creation failed: " + str(created.get("error")))
    model = Path(created["data"]["main"])
    model_before = _directory(model.parent)
    proof = dict(actual_git_revision=identity["actual_git_head"], working_tree_dirty=False,
        git_diff_sha256=identity["git_diff_sha256"], git_diff_scope=identity["git_diff_scope"],
        source_snapshot_sha256=identity["source_snapshot_sha256"], profile=profile,
        producer_sha256=sha(Path(__file__)), script_sha256=hashlib.sha256(PROGRAM.encode()).hexdigest(),
        source_before=original, created_model_sha256=sha(model), binary_before=before,
        native_executed=False, status="failed", graphics=False, solver_executed=False,
        product_source_identity=products)
    try:
        prepared = service.prepare_native_program("python", code=PROGRAM,
            outputs=[dict(name="node-set-identities.json", kind="json")], expected_counts=dict(nodes=4))
        native = service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"],
            model=str(model), file_type="keyword")
        proof["native_result"] = native
        job = service.jobs.get(native["job_id"])
        process = (job.get("engine_result") or {}).get("data") or {}
        proof["process"] = process
        proof["native_executed"] = type(process.get("pid")) is int
        if (native["status"] != "succeeded" or not proof["native_executed"] or process.get("graphics") is not False
                or "-nographics" not in process.get("argv", []) or process.get("returncode") != 0 or process.get("timed_out")):
            raise ValueError("Native API did not complete a successful owned headless process")
        raw_path = service.jobs.root / native["job_id"] / "node-set-identities.json"
        proof["raw_sha256"] = sha(raw_path)
        raw = json.loads(raw_path.read_text(encoding="utf8"))
        proof["raw"] = raw
        proof["comparison"] = validate(raw)
        proof["status"] = "passed"
    except Exception as error:
        proof["error"] = dict(type=type(error).__name__, message=str(error))
    finally:
        proof["identity_guards"] = dict(original_tree_unchanged=_directory(source_dir) == original,
            created_tree_unchanged=_directory(model.parent) == model_before,
            executable_unchanged=sha(executable) == before["executable"],
            configuration_unchanged=sha(config) == before["configuration"],
            checkout_unchanged=execution_identity(ROOT) == identity,
            no_native_processes_remain=not native_processes())
        if not all(proof["identity_guards"].values()):
            proof["status"] = "failed"
        (output / "comparison.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    return proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-native", action="store_true", required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    observed = run(args.executable, args.output)
    print(json.dumps(dict(status=observed["status"], native_executed=observed["native_executed"],
                          identity_guards=observed["identity_guards"]), ensure_ascii=False))
    raise SystemExit(0 if observed["status"] == "passed" else 1)
