"""Portable capture-time runtime bindings for newly selected P08 refresh contexts.

This validates recorded identities, not whether C++ executed. Original domain
source contracts and native domain-verdict tests remain separate and unchanged.
"""
import ast
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath

PREFIX = "src/ls_prepost_mcp/"
OPS = PREFIX + "domain/model/operations.py"
HOST_TASKS = frozenset(("P03", "P06_identity", "P06_geometry"))
HOST_SOURCES = frozenset(OPS if name == "operations" else PREFIX + name for name in (
    "operations", "config.py", "jobs.py", "core/contracts.py", "engine/context.py"))
COMMON_NATIVE = frozenset(PREFIX + name for name in (
    "config.py", "jobs.py", "runner.py", "core/contracts.py", "core/native_log.py",
    "engine/__init__.py", "engine/jobs.py", "engine/batch.py", "engine/context.py",
    "engine/environment.py", "engine/processes.py", "engine/windows_job.py", "engine/workspace.py",
    "native/commands.py", "native/versions.py", "native/_version_resource.py")) | {OPS}
BRIDGE_SOURCES = {
    "bridge.py": PREFIX + "embedded.py",
    "native_commands.py": PREFIX + "native/commands.py",
    "native_versions.py": PREFIX + "native/versions.py",
    "native__version_resource.py": PREFIX + "native/_version_resource.py",
}
EMBEDDED_SOURCES = COMMON_NATIVE | frozenset(BRIDGE_SOURCES.values()) | {PREFIX + "native/bundle.py"}
PROGRAM_SOURCES = COMMON_NATIVE | frozenset(PREFIX + name for name in (
    "programs.py", "program_bundle.py", "native_results.py")) | {"tools/verify_node_set_user_ids.py"}
PROGRAM_FILES = frozenset(("program.py", "bootstrap.py", "contract.json", "commands.cfile", "complete.scl"))
NATIVE_ROLES = {
    "P04": {"4.13": Counter(execute_native_program=1)},
    "P05": {version: Counter(inspect_model=2, export_keyword=1) for version in ("4.13", "4.10")},
    "P12": {version: Counter(inspect_model=6, export_keyword=3) for version in ("4.13", "4.10")},
    "P10": {version: Counter(inspect_model=2, export_keyword=1) for version in ("4.13", "4.10")},
}


def _require(condition, message):
    if not condition:
        raise ValueError("P08 refresh capsule: " + message)


def _hex(value, width=64):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{" + str(width) + "}", value) is not None


def _relative(value):
    _require(isinstance(value, str) and value and "\\" not in value, "noncanonical relative path")
    path = PurePosixPath(value)
    _require(not path.is_absolute() and not PureWindowsPath(value).drive and not any(
        item in (".", "..") for item in path.parts) and path.as_posix() == value, "path leaves admitted namespace")
    return path


def _git(root, *arguments):
    return subprocess.check_output(["git", "--no-optional-locks", *arguments], cwd=root, timeout=20)


def _tracked(root, revision):
    rows = _git(root, "ls-tree", "-r", revision).decode("utf8").splitlines()
    output = {}
    for row in rows:
        metadata, path = row.split("\t", 1)
        mode, kind, blob = metadata.split()
        if kind == "blob" and mode in ("100644", "100755"):
            output[path] = blob
    return output


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_capsule(evidence, task, root):
    """Reject missing/stale sources and unmeasured or wrong-role staged records."""
    _require(task in HOST_TASKS or task in NATIVE_ROLES, "unknown task runtime role")
    capsule = evidence.get("p08_refresh_capsule")
    _require(isinstance(capsule, dict) and type(capsule.get("schema_version")) is int
             and capsule["schema_version"] == 1, "missing new capture-time capsule")
    _require(capsule.get("task") == task and capsule.get("working_tree_dirty") is False, "task/clean-source mismatch")
    origin = evidence
    if "source_checkpoints" in evidence:
        origin = evidence["source_checkpoints"][evidence["active_source_checkpoint"]]
    revision = origin.get("actual_git_revision")
    snapshot = origin.get("source_snapshot_sha256", origin.get("raw_source_snapshot_sha256"))
    _require(_hex(revision, 40) and _hex(snapshot) and origin.get("working_tree_dirty") is False,
             "missing actual clean capture revision/full snapshot")
    _require(capsule.get("actual_git_revision") == revision and capsule.get("source_snapshot_sha256") == snapshot,
             "capsule does not belong to the actual domain capture")
    files = capsule.get("source_files")
    _require(isinstance(files, dict) and files, "missing capture-time full raw source map")
    for path, raw_hash in files.items():
        _relative(path)
        _require(_hex(raw_hash), "invalid captured raw source SHA")
    _require(_sha(json.dumps(files, sort_keys=True).encode()) == snapshot, "full raw source digest mismatch")
    after_files = capsule.get("source_after_files")
    _require(after_files == files and capsule.get("source_after_snapshot_sha256") == snapshot,
             "capture-time project source before/after mismatch")
    tree = _tracked(root, revision)
    _require(set(files) <= tree.keys(), "captured sources absent from actual Git revision")
    rows = capsule.get("runtime_sources")
    _require(isinstance(rows, list) and rows, "missing runtime source identities")
    sources = {}
    for row in rows:
        _require(isinstance(row, dict), "invalid runtime identity")
        path = row.get("path")
        _relative(path)
        _require(path not in sources and path in files, "duplicate or uncaptured runtime source")
        _require(_hex(row.get("raw_sha256")) and row["raw_sha256"] == files[path], "raw SHA not bound to capture snapshot")
        _require(row.get("git_blob_id") == tree.get(path) and _hex(row.get("sha256_lf")), "runtime Git/LF identity missing")
        captured = _git(root, "show", revision + ":" + path).replace(b"\r\n", b"\n")
        _require(_sha(captured) == row["sha256_lf"], "runtime recorded Git/LF mismatch")
        raw_path = Path(root) / path
        current = raw_path.resolve()
        _require(current.is_relative_to(Path(root).resolve()) and current.is_file() and not raw_path.is_symlink()
                 and not getattr(raw_path.lstat(), "st_file_attributes", 0) & 0x400, "runtime source leaves current checkout")
        _require(_sha(current.read_bytes().replace(b"\r\n", b"\n")) == row["sha256_lf"], "runtime current source drift")
        sources[path] = row
    required = HOST_SOURCES if task in HOST_TASKS else PROGRAM_SOURCES if task == "P04" else EMBEDDED_SOURCES
    _require(required <= sources.keys(), "missing consumed runtime source: " + ", ".join(sorted(required - sources.keys())))
    jobs = capsule.get("native_jobs")
    _require(isinstance(jobs, list), "missing explicit native job registry")
    if task in HOST_TASKS:
        _require(not jobs and evidence.get("native_executed") is False, "host evidence cannot claim native runtime")
        return
    _require(evidence.get("native_executed") is True, "native context lacks actual execution declaration")
    profiles = capsule.get("profiles")
    _require(isinstance(profiles, dict) and set(NATIVE_ROLES[task]) <= profiles.keys()
             and set(profiles) <= {"4.13", "4.10"}, "missing selected immutable profile identities")
    for item in profiles.values():
        _require(isinstance(item, dict) and _hex(item.get("outer_executable_sha256"))
                 and _hex(item.get("configuration_sha256")) and item.get("configuration_source_kind") == "immutable_private_snapshot",
                 "incomplete executable/private configuration identity")
    intended_program = None
    if task == "P04":
        syntax = ast.parse(_git(root, "show", revision + ":tools/verify_node_set_user_ids.py").decode("utf8"))
        program = next((ast.literal_eval(node.value) for node in syntax.body if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == "PROGRAM" for target in node.targets)), None)
        _require(isinstance(program, str), "missing captured P04 PROGRAM oracle")
        intended_program = _sha(program.encode().replace(b"\r\n", b"\n"))
    observed, identifiers = {}, set()
    for job in jobs:
        _require(isinstance(job, dict), "invalid staged job record")
        uid, profile, role = job.get("job_id"), job.get("profile"), job.get("role")
        _require(_hex(uid, 32) and uid not in identifiers, "missing/duplicate native job UUID")
        identifiers.add(uid)
        _require(profile in NATIVE_ROLES[task] and role in NATIVE_ROLES[task][profile], "wrong native runtime profile/role")
        _require(job.get("manifest_action") == role and job.get("engine_operation") == role
                 and job.get("engine_job_id") == uid
                 and job.get("native_channel") == ("python" if task == "P04" else "embedded_python"),
                 "job UUID/observed runtime action or channel differs from role")
        _require(job.get("outer_executable_sha256") == profiles[profile]["outer_executable_sha256"]
                 and job.get("configuration_sha256") == profiles[profile]["configuration_sha256"]
                 and job.get("argv_matches_profile") is True and job.get("manifest_executable_matches_profile") is True
                 and job.get("configuration_matches_profile") is True, "job executable/configuration binding differs")
        observed.setdefault(profile, Counter())[role] += 1
        _require(job.get("actual_git_revision") == revision and job.get("source_snapshot_sha256") == snapshot,
                 "staged job source context differs")
        _require("measured_before_native" not in job, "staged pre-execution measurement must not be invented")
        staged = job.get("staged_files")
        expected = PROGRAM_FILES if task == "P04" else BRIDGE_SOURCES.keys()
        _require(isinstance(staged, dict) and set(staged) == set(expected), "missing/wrong staged runtime files")
        for name, item in staged.items():
            _relative(name)
            _require(isinstance(item, dict) and item.get("phase") == "post_native_capture" and _hex(item.get("sha256"))
                     and not {"before_sha256", "after_sha256"} & item.keys(), "missing actual post-native staged measurement")
            _require("post_capture_reread_sha256" not in item or item["post_capture_reread_sha256"] == item["sha256"],
                     "post-capture staged reread differs")
            if task != "P04":
                origin_path = BRIDGE_SOURCES[name]
                _require(item.get("source") == origin_path and item["sha256"] == sources[origin_path]["raw_sha256"],
                         "staged bridge/helper differs from captured source")
        if task == "P04":
            _require(job.get("program_source_sha256_lf") == intended_program, "intended program differs from captured producer")
            _require(staged["program.py"].get("sha256_lf") == job["program_source_sha256_lf"], "generated program differs from intended source")
            _require(job.get("contract_program_sha256") == staged["program.py"]["sha256"], "contract does not bind staged program")
    _require(observed == NATIVE_ROLES[task], "native role counts/profiles incomplete")
