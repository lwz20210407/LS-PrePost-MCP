"""P08 small owned offline oracles and readback admission; no native dispatch in this stage."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import stat
import subprocess
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import Selector
from ls_prepost_mcp.domain.model import KeywordDeck, access
from ls_prepost_mcp.gui_mesh import mesh_index
from ls_prepost_mcp.native.versions import require_capability, require_installation
from ls_prepost_mcp.service import Service
from tools import verify_p05_boundary_roundtrip as shared
from tools.native_regression import execution_identity

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/data/p08-mesh-roundtrip.json"
MAX_BYTES = 256 * 1024
CASE_IDS = ("translate", "rotate", "reflect", "copy", "merge", "normals", "renumber", "delete")
PRODUCT_PATHS = tuple("src/ls_prepost_mcp/" + p for p in (
    "domain/model/_identity.py", "domain/model/access.py", "domain/model/blocks.py", "domain/model/fields.py",
    "domain/model/text.py", "domain/model/layouts.py", "domain/model/schema.py", "domain/model/matching.py",
    "domain/model/parameters.py", "domain/model/scope.py", "domain/model/tables.py", "domain/model/includes.py",
    "domain/model/tree.py", "domain/model/persist.py", "domain/model/deck.py", "domain/model/geometry.py",
    "domain/model/selectors.py", "domain/model/node_sets.py", "domain/model/sets.py", "domain/model/lists.py",
    "domain/model/set_rows.py", "domain/model/links.py", "domain/model/references.py", "domain/model/mesh.py",
    "domain/model/renumber.py", "domain/model/quality.py", "domain/model/operations.py", "domain/model/preflight.py",
    "domain/model/keyword_docs.py", "model_target_tools.py", "service.py", "config.py", "jobs.py", "gui_mesh.py",
    "keyword_staging.py", "native_results.py", "runner.py", "embedded.py", "native/bundle.py", "native/commands.py",
    "native/versions.py", "native/_version_resource.py", "engine/__init__.py", "engine/context.py", "engine/batch.py",
    "engine/jobs.py", "engine/environment.py", "engine/processes.py", "engine/windows_job.py", "engine/workspace.py",
    "core/contracts.py", "core/validation.py", "core/native_log.py",
))
CAPTURE_SOURCE_PATHS = PRODUCT_PATHS + (
    "tools/verify_p08_mesh_roundtrip.py", "tools/verify_p05_boundary_roundtrip.py", "tools/native_regression.py",
    "tests/data/p08-mesh-roundtrip.json", "tests/test_p08_mesh_roundtrip_contract.py",
    "tests/test_p08_mesh_roundtrip_guards.py", "pyproject.toml", "uv.lock",
)
BRIDGE_SOURCES = {"bridge.py": "src/ls_prepost_mcp/embedded.py",
    "native_commands.py": "src/ls_prepost_mcp/native/commands.py",
    "native_versions.py": "src/ls_prepost_mcp/native/versions.py",
    "native__version_resource.py": "src/ls_prepost_mcp/native/_version_resource.py"}


def fixture():
    raw = FIXTURE.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("P08 fixture exceeds its bounded source contract")
    data = json.loads(raw)
    if data.get("schema_version") != 1 or tuple(c["id"] for c in data["cases"]) != CASE_IDS:
        raise ValueError("P08 fixture must explicitly register the eight original operations")
    return data


def case_spec(ident):
    return copy.deepcopy(next(c for c in fixture()["cases"] if c["id"] == ident))


def _uid(value):
    if type(value) is not int or not 1 <= value <= 99_999_999:
        raise ValueError("Owned/user UIDs must be positive exact integers fitting the fixture fields")
    return value


def _keyed(rows, key):
    result = {}
    for row in rows:
        ident = _uid(key(row))
        if ident in result:
            raise ValueError("Duplicate UID in bounded observation")
        result[ident] = row
    return result


def validate_case(case):
    if case["id"] not in CASE_IDS or not 0 <= case["coordinate_atol"] <= 1e-8:
        raise ValueError("Unknown case or comparison tolerance")
    if "selector" in case["operation"]:
        Selector.model_validate(case["operation"]["selector"])
    for data in (case["input"], case["expected"]):
        if not 1 <= len(data["nodes"]) <= 32 or not 1 <= len(data["elements"]) <= 8:
            raise ValueError("Owned fixture is limited to32 nodes and8 elements")
        nodes = _keyed(data["nodes"], lambda r: r[0])
        parts = _keyed(data["parts"], lambda r: r["id"])
        _keyed(data["elements"], lambda r: r["id"])
        if any(len(r) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in r[1:]) for r in nodes.values()):
            raise ValueError("Fixture coordinates must be finite numeric triples")
        for row in data["elements"]:
            width = {"solid": 8, "shell": 4}.get(row["kind"])
            if width is None or len(row["nodes"]) != width or _uid(row["pid"]) not in parts:
                raise ValueError("Only explicit HEX8/QUAD4 and registered Parts are admitted")
            if any(_uid(n) not in nodes for n in row["nodes"]):
                raise ValueError("Fixture connectivity references an undefined node")
        _keyed(data["node_sets"], lambda r: r["id"])
        for row in data["node_sets"]:
            if any(_uid(n) not in nodes for n in row["members"]):
                raise ValueError("Fixture node-set reference is undefined")
        _keyed(data["spc"], lambda r: r[0])
        if any(row[0] not in nodes for row in data["spc"]):
            raise ValueError("Fixture constraint references an undefined node")
    original, expected = case["input"], case["expected"]
    sentinel_ids = {n for e in original["elements"] if e["pid"] == 1 for n in e["nodes"]}
    for section in ("parts", "materials", "sections"):
        if expected[section] != original[section]:
            raise ValueError("Geometry oracle may not rewrite shared properties")
    if {r[0]: r for r in expected["nodes"] if r[0] in sentinel_ids} != {r[0]: r for r in original["nodes"] if r[0] in sentinel_ids}:
        raise ValueError("Oracle changes an unselected sentinel coordinate/UID")
    if [r for r in expected["elements"] if r["pid"] == 1] != [r for r in original["elements"] if r["pid"] == 1]:
        raise ValueError("Oracle changes an unselected sentinel connection")
    if [r for r in expected["node_sets"] if r["id"] == 51] != [r for r in original["node_sets"] if r["id"] == 51]:
        raise ValueError("Oracle changes a sentinel reference")
    if [r for r in expected["spc"] if r[0] in sentinel_ids] != [r for r in original["spc"] if r[0] in sentinel_ids]:
        raise ValueError("Oracle changes a sentinel constraint")


def source_text(data):
    """Formatting of handwritten tables only, never an edit or geometry engine."""
    lines = ["*KEYWORD"]
    for row in data["parts"]:
        lines += ["*PART", "owned Part" + str(row["id"]), "".join(f"{row[k]:10d}" for k in ("id", "secid", "mid"))]
    for row in data["sections"]:
        lines += ["*SECTION_" + row["kind"].upper(), f"{row['id']:10d}{row['elform']:10d}"]
        if row["kind"] == "shell":
            lines.append("".join(f"{v:10g}" for v in row["thickness"]))
    for row in data["materials"]:
        lines += ["*MAT_ELASTIC", f"{row['id']:10d}{row['ro']:10g}{row['e']:10g}{row['pr']:10g}"]
    lines += ["*NODE"] + [f"{r[0]:8d}" + "".join(f"{v:16g}" for v in r[1:]) for r in data["nodes"]]
    for kind in ("solid", "shell"):
        elements = [r for r in data["elements"] if r["kind"] == kind]
        if elements:
            lines += ["*ELEMENT_" + kind.upper()] + ["".join(f"{v:8d}" for v in (r["id"], r["pid"], *r["nodes"])) for r in elements]
    for row in data["node_sets"]:
        lines += ["*SET_NODE_LIST", f"{row['id']:10d}", "".join(f"{n:10d}" for n in row["members"])]
    if data["spc"]:
        lines += ["*BOUNDARY_SPC_NODE"] + ["".join(f"{n:10d}" for n in row) for row in data["spc"]]
    return "\n".join(lines + ["*END", ""])


def _records(deck, keyword, names):
    result = []
    for block in deck.blocks(keyword):
        layout = deck.layout(block)
        rows = list(layout.rows) if layout.key is not None else [None]
        result += [[deck.get(block, name, row=row).value for name in names] for row in rows]
    return result


def snapshot(path):
    path = Path(path)
    shared._regular(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Readback exceeds the small owned case bound")
    deck = KeywordDeck.load(path)
    if len(deck.files) != 1 or deck.blocks("*INCLUDE*"):
        raise ValueError("P08 first matrix is standalone only")
    nodes = _records(deck, "*NODE", ("nid", "x", "y", "z"))
    elements = []
    for kind, width in (("solid", 8), ("shell", 4)):
        rows = _records(deck, "*ELEMENT_" + kind.upper(), ("eid", "pid", *("n" + str(i) for i in range(1, width + 1))))
        elements += [dict(kind=kind, id=r[0], pid=r[1], nodes=r[2:]) for r in rows]
    report = deck.references(True)
    if report.dangling_count or report.unverified_count or report.unchecked:
        raise ValueError("Readback reference coverage is incomplete or dangling")
    node_sets = [dict(id=deck.get(b, "sid").value, members=deck.members(b)) for b in deck.blocks("*SET_NODE_LIST")]
    parts = [dict(zip(("id", "secid", "mid"), r)) for r in _records(deck, "*PART", ("pid", "secid", "mid"))]
    materials = [dict(zip(("id", "ro", "e", "pr"), r)) for r in _records(deck, "*MAT_ELASTIC*", ("mid", "ro", "e", "pr"))]
    sections = []
    for kind in ("solid", "shell"):
        for b, row in deck.find("*SECTION_" + kind.upper() + "*"):
            value = dict(kind=kind, id=deck.get(b, "secid", row=row).value, elform=deck.get(b, "elform", row=row).value)
            if kind == "shell":
                value["thickness"] = [deck.get(b, "t" + str(i), row=row).value for i in range(1, 5)]
            sections.append(value)
    data = dict(nodes=nodes, elements=elements, node_sets=node_sets,
        spc=_records(deck, "*BOUNDARY_SPC_NODE", ("nid", "cid", "dofx", "dofy", "dofz", "dofrx", "dofry", "dofrz")),
        parts=parts, materials=materials, sections=sections)
    _keyed(nodes, lambda r: r[0])
    return data


def _ordered(data):
    result = copy.deepcopy(data)
    for key in ("nodes", "spc"):
        result[key] = sorted(result[key], key=lambda r: r[0])
    for key in ("elements", "node_sets", "parts", "materials", "sections"):
        result[key] = sorted(result[key], key=lambda r: r["id"])
    return result


def projection_differences(actual, case):
    expected, actual = _ordered(case["expected"]), _ordered(actual)
    differences = []
    want_nodes = _keyed(expected["nodes"], lambda r: r[0])
    got_nodes = _keyed(actual["nodes"], lambda r: r[0])
    if got_nodes.keys() != want_nodes.keys():
        differences.append("node_uid_set")
    for uid in got_nodes.keys() & want_nodes.keys():
        tolerance = case["coordinate_atol"] if uid in case["coordinate_atol_node_ids"] else 0.0
        if any(not math.isfinite(float(a)) or not math.isclose(float(a), float(b), rel_tol=0, abs_tol=tolerance)
               for a, b in zip(got_nodes[uid][1:], want_nodes[uid][1:])):
            differences.append("coordinate:" + str(uid))
    for key in ("elements", "node_sets", "spc", "parts", "materials", "sections"):
        if actual[key] != expected[key]:
            differences.append(key)
    return differences


def compare_export(path, case):
    return projection_differences(snapshot(path), case)


def compare_typed(data, case):
    """Existing G03 mesh-index validation, then literal UID/geometry/Part oracles."""
    for row in data["nodes"]:
        _uid(row[0])
        if len(row) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in row[1:]):
            raise ValueError("Typed coordinates must be finite numeric reference triples")
    for row in data["elements"]:
        _uid(row["id"])
        for uid in row["nodes"]:
            _uid(uid)
    for uid in data.get("part_ids", []):
        _uid(uid)
    for ids in data.get("part_elements", {}).values():
        for uid in ids:
            _uid(uid)
    nodes, elements = mesh_index(data)
    wanted = case["expected"]
    differences = []
    expected_nodes = _keyed(wanted["nodes"], lambda r: r[0])
    if nodes.keys() != expected_nodes.keys():
        differences.append("typed_node_uid_set")
    for uid in nodes.keys() & expected_nodes.keys():
        tolerance = case["coordinate_atol"] if uid in case["coordinate_atol_node_ids"] else 0.0
        if any(not math.isclose(float(a), float(b), rel_tol=0, abs_tol=tolerance) for a, b in zip(nodes[uid], expected_nodes[uid][1:])):
            differences.append("typed_coordinate:" + str(uid))
    expected_elements = {(r["kind"], r["id"]): tuple(r["nodes"]) for r in wanted["elements"]}
    if elements != expected_elements:
        differences.append("typed_connectivity")
    counts = dict(nodes=len(wanted["nodes"]), elements=len(wanted["elements"]))
    if any(type(data.get("counts", {}).get(k)) is not int or data["counts"][k] != v for k, v in counts.items()):
        differences.append("native_counts")
    expected_parts = {str(p["id"]): sorted(r["id"] for r in wanted["elements"] if r["pid"] == p["id"]) for p in wanted["parts"]}
    if (sorted(data.get("part_ids", [])) != sorted(p["id"] for p in wanted["parts"])
            or {str(k): sorted(v) for k, v in data.get("part_elements", {}).items()} != expected_parts):
        differences.append("typed_part_membership")
    return differences


def source_identity(identity, expected_head=None, expected_snapshot=None):
    """Admit a clean actual pinned Git/full source before config, native or outputs."""
    if not isinstance(identity, dict):
        raise ValueError("Source admission requires an actual source object")
    revision, captured = identity.get("actual_git_head"), identity.get("source_files", {})
    if not isinstance(revision, str) or re.fullmatch(r"[a-f0-9]{40}", revision) is None or identity.get("working_tree_dirty") is not False:
        raise ValueError("Source admission requires a clean actual committed revision")
    if (expected_head is not None and revision != expected_head) or (expected_snapshot is not None and identity.get("source_snapshot_sha256") != expected_snapshot):
        raise ValueError("Source admission differs from the explicitly pinned head/snapshot")
    if hashlib.sha256(json.dumps(captured, sort_keys=True).encode()).hexdigest() != identity.get("source_snapshot_sha256"):
        raise ValueError("Full source snapshot digest mismatch")
    actual = execution_identity(ROOT)
    if any(actual.get(k) != identity.get(k) for k in ("actual_git_head", "working_tree_dirty", "source_snapshot_sha256", "source_files")):
        raise ValueError("Actual checkout changed since source capture")
    for path in CAPTURE_SOURCE_PATHS:
        value = captured.get(path)
        if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None or not (ROOT / path).is_file() or shared.sha(ROOT / path) != value:
            raise ValueError("Missing or changed required source: " + path)
        shared._regular(ROOT / path)
    rows = subprocess.check_output(["git", "--no-optional-locks", "ls-tree", "-r", revision], cwd=ROOT, text=True, timeout=20)
    blobs = {line.split("\t", 1)[1]: line.split("\t", 1)[0].split()[2] for line in rows.splitlines()}
    if not set(captured) <= blobs.keys():
        raise ValueError("Full captured sources must be tracked in the actual revision")
    return {p: dict(git_blob_id=blobs[p], captured_file_sha256=captured[p]) for p in CAPTURE_SOURCE_PATHS}


def prepare_case(directory, ident, identity):
    source_identity(identity)
    spec = case_spec(ident)
    validate_case(spec)
    directory = Path(directory)
    if directory.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Owned outputs must stay outside the checkout")
    directory.mkdir(parents=True, exist_ok=False)
    source = directory / "input.k"
    source.write_text(source_text(spec["input"]), encoding="ascii", newline="\n")
    source_bytes = source.read_bytes()
    if projection_differences(snapshot(source), {**spec, "expected": spec["input"], "coordinate_atol_node_ids": []}):
        raise ValueError("Written fixture differs from its independent input table")
    service = Service(Settings(directory / "work", allowed_roots=(directory,)))
    creation = service.mesh_ops(str(source), [copy.deepcopy(spec["operation"])])
    if creation.get("status") != "succeeded":
        raise ValueError("Offline mesh_ops failed: " + str(creation.get("error")))
    job, _ = shared._job(service, creation)
    edited = Path(creation["data"]["main"])
    access.root_guard((job,))(edited)
    if compare_export(edited, spec) or source.read_bytes() != source_bytes:
        raise ValueError("Offline output differs from handwritten oracle or changed original input")
    return dict(directory=directory, spec=spec, source=source, source_bytes=source_bytes,
                edited=edited, source_identity=shared._one_file(source), edited_identity=shared._one_file(edited),
                service=service, creation=creation)


def profile_inputs_identity(inputs):
    """Full readonly dual-profile fingerprints; no global preferences or C++ launch."""
    if not isinstance(inputs, dict) or set(inputs) != {"4.13", "4.10"}:
        raise ValueError("Declare both readonly private profiles")
    output = {}
    for version, row in inputs.items():
        executable, source = Path(row["executable"]), Path(row["source"])
        shared._regular(executable)
        shared._regular(source)
        before = source.stat()
        readonly = bool(getattr(before, "st_file_attributes", 0) & 1) if hasattr(before, "st_file_attributes") else not bool(before.st_mode & stat.S_IWUSR)
        if not readonly or before.st_size > 2 * 1024 * 1024:
            raise ValueError("Private configuration must be readonly and bounded")
        with source.open("rb") as f:
            opened = os.fstat(f.fileno())
            raw = f.read(2 * 1024 * 1024 + 1)
            closed = os.fstat(f.fileno())
        after = source.stat()
        def key(s):
            return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns
        if not (key(before) == key(opened) == key(closed) == key(after)) or len(raw) != before.st_size:
            raise ValueError("Private configuration changed while reading complete bytes")
        configuration = dict(sha256=hashlib.sha256(raw).hexdigest(), size=len(raw), mtime_ns=after.st_mtime_ns,
                             device=after.st_dev, inode=after.st_ino, readonly=True)
        exe_before = executable.stat()
        fingerprint = shared._file_identity(executable)
        exe_after = executable.stat()
        if key(exe_before) != key(exe_after) or fingerprint["size"] != exe_after.st_size:
            raise ValueError("Executable changed while measuring its complete fingerprint")
        if (row.get("executable_sha256") != fingerprint["sha256"] or row.get("source_sha256") != configuration["sha256"]):
            raise ValueError("Profile full SHA differs from the explicit expected executable/configuration")
        policy = require_installation(executable, version=version)
        if policy["version_source"] != "file_version_resource":
            raise ValueError("Executable resource-backed policy is required")
        require_capability(executable, "batch")
        output[version] = dict(executable=fingerprint, configuration=configuration, source=str(source.resolve()),
                               executable_path=str(executable.resolve()), profile=policy,
                               directory_entries=sorted(p.name for p in source.parent.iterdir()))
    return output


def validate_job_binding(manifest, expected_action, profile):
    """Validate recorded job evidence; this function does not execute or attest a fake process."""
    shared._engine(manifest)
    uid = manifest.get("job_id")
    if not isinstance(uid, str) or re.fullmatch(r"[a-f0-9]{32}", uid) is None:
        raise ValueError("Missing actual native job UUID")
    process = manifest["engine_result"]["data"]
    if (manifest.get("status") != "succeeded" or manifest.get("action") != expected_action
            or manifest.get("execution_mode") != "nographics" or process.get("launch_mode") != "c"
            or process.get("timed_out") is not False or manifest.get("session_id") is not None
            or manifest.get("native_channel") != "embedded_python"
            or process.get("process_isolation") != "windows_job"):
        raise ValueError("Native role/mode/Windows Job binding mismatch")
    argv, executable = process.get("argv", []), manifest.get("executable", {})
    if (not argv or any(str(value).startswith("w=") for value in argv) or Path(argv[0]).resolve() != Path(profile["executable_path"])
            or Path(executable.get("path", "")).resolve() != Path(profile["executable_path"])):
        raise ValueError("Per-job executable path differs from selected profile")
    outer = profile["executable"]
    if any(executable.get(k) != outer[k] for k in ("size", "mtime_ns")):
        raise ValueError("Per-job executable stat differs from outer full fingerprint")
    stat_only = executable.get("sha256") is None and outer["size"] > 64 * 1024 * 1024 and "64 MiB" in executable.get("hash_note", "")
    if not stat_only and executable.get("sha256") != outer["sha256"]:
        raise ValueError("Per-job executable hash is neither exact nor documented stat-only")
    config = process.get("configuration", {})
    if (Path(config.get("source", "")).resolve() != Path(profile["source"])
            or config.get("source_sha256") != profile["configuration"]["sha256"] or config.get("source_modified") is not False):
        raise ValueError("Native job used another private configuration")
    return dict(job_id=uid, expected_action=expected_action, pid=process["pid"],
                executable_identity=copy.deepcopy(executable), per_job_full_sha256=not stat_only,
                outer_full_sha256=outer["sha256"], os_process_creation_time="not_continuously_observed")


def validate_staged_bridge(directory, sources):
    for destination, origin in BRIDGE_SOURCES.items():
        path = Path(directory) / destination
        shared._regular(path)
        if shared.sha(path) != sources[origin]["captured_file_sha256"]:
            raise ValueError("Staged bridge/helper differs from admitted source: " + destination)


def validate_job_pair(typed, exported, profile):
    bindings = dict(typed_geometry=validate_job_binding(typed, "gui_mesh_state", profile),
                    keyword_retention=validate_job_binding(exported, "export_keyword", profile))
    if len({row["job_id"] for row in bindings.values()}) != 2:
        raise ValueError("The two observation roles require distinct owned job UUIDs")
    return dict(record_validation_only=True, bindings=bindings)


def job_plan():
    return dict(native_executed=False, native_dispatch_enabled=False,
        units="caller-declared model coordinates, no conversion", frame="reference", identity="user UID plus entity kind, not internal index",
        retention_only=dict(native_jobs_per_case=1, api="Service.export_keyword", expected_action="export_keyword",
            proves=["actual native inventory counts", "exported keyword geometry/reference retention"], typed_geometry_verified=False),
        typed_geometry=dict(native_jobs_per_case=2, headless_abi_verified=False,
            jobs=[dict(role="typed_geometry", api="Service._native", action="gui_mesh_state", graphics=False, session=None),
                  dict(role="keyword_retention", api="Service.export_keyword", action="export_keyword", graphics=False, session=None)],
            future_proves=["DataCenter user node coordinates/connectivity/Part membership", "independent keyword reference retention"],
            pending="root-leased first headless ABI pilot; no inference from source availability or fake tests"),
        mandatory_future_admission=["source_identity before private profiles/output", "explicit readonly dual-profile full fingerprints",
            "per-role validate_job_pair and per-job validate_staged_bridge", "owned request/staged input SHA binding",
            "independent typed and keyword projections", "original/edited/source/profile after-guards and no residual native process"],
        physical_response="not_run", solver_or_GUI_equivalence="unverified")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=("all", *CASE_IDS), default="all")
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-source-snapshot", required=True)
    parser.add_argument("--run-native", action="store_true")
    args = parser.parse_args(argv)
    identity = execution_identity(ROOT)
    sources = source_identity(identity, args.expected_head, args.expected_source_snapshot)
    if args.run_native:
        raise ValueError("Native dispatch is not enabled during offline preparation; root must approve the headless pilot")
    output = args.output.resolve()
    if output.is_relative_to(ROOT.resolve()) or not output.is_relative_to(ROOT.parent.resolve()):
        raise ValueError("Use fresh task-owned output outside the checkout")
    output.mkdir(parents=True, exist_ok=False)
    (output / "execution-context.json").write_text(json.dumps(identity, indent=2), encoding="utf8")
    results = []
    for ident in CASE_IDS if args.case == "all" else (args.case,):
        prepared = prepare_case(output / ident, ident, identity)
        results.append(dict(case=ident, status="passed_offline", source_sha256=shared.sha(prepared["source"]),
                            edited_sha256=shared.sha(prepared["edited"]), native_executed=False))
    after = execution_identity(ROOT)
    if any(after[k] != identity[k] for k in ("actual_git_head", "working_tree_dirty", "source_snapshot_sha256")):
        raise ValueError("Source changed during offline preparation")
    report = dict(status="passed_offline", native_executed=False, source=identity, capture_source_identity=sources,
                  cases=results, job_plan=job_plan(), L2_complete=False)
    (output / "offline.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    print(json.dumps(dict(status=report["status"], cases=len(results), native_executed=False, L2_complete=False)))


if __name__ == "__main__":
    main()
