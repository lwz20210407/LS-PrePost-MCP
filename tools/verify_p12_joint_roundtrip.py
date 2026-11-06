"""Owned single-file P12 definitions, through existing create/save/export APIs only.

Native export retention is not a typed native Joint query or solver-motion test.
Use --run-native only in an explicitly authorized serial headless window.
"""
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
from ls_prepost_mcp.domain.model import KeywordDeck, access, preflight_includes
from ls_prepost_mcp.domain.model.blocks import SourceFile, parse_blocks
from ls_prepost_mcp.domain.model.joint_checks import joint_instances, joint_kind
from ls_prepost_mcp.domain.model.text import encode
from ls_prepost_mcp.engine.environment import locate_config
from ls_prepost_mcp.native.versions import require_capability, require_installation
from ls_prepost_mcp.service import Service
from tools.native_regression import execution_identity

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/data/p12-roundtrip-fixtures.json"
KINDS = frozenset(("SPHERICAL", "REVOLUTE", "CYLINDRICAL", "PLANAR", "UNIVERSAL", "TRANSLATIONAL",
                   "LOCKING", "ROTATIONAL_MOTOR", "TRANSLATIONAL_MOTOR"))
ATOL, RTOL = 1e-10, 1e-12
MAX_BYTES = 10 * 1024 * 1024
PRODUCT_PATHS = tuple("src/ls_prepost_mcp/" + path for path in (
    "domain/model/_identity.py", "domain/model/joints.py", "domain/model/joint_checks.py", "domain/model/loads.py",
    "domain/model/deck.py", "domain/model/matching.py", "domain/model/fields.py",
    "domain/model/layouts.py", "domain/model/keyword_docs.py", "domain/model/blocks.py",
    "domain/model/text.py", "domain/model/geometry.py", "domain/model/access.py",
    "domain/model/contact_report.py", "domain/model/contact.py",
    "domain/model/preflight.py", "domain/model/persist.py", "domain/model/node_sets.py",
    "domain/model/sets.py", "domain/model/selectors.py", "domain/model/operations.py",
    "domain/model/references.py", "model_save.py", "model_target_tools.py", "keyword_staging.py",
    "service.py", "config.py", "jobs.py", "runner.py", "engine/batch.py", "engine/environment.py",
    "engine/processes.py", "native/commands.py", "native/versions.py",
))
CAPTURE_SOURCE_PATHS = PRODUCT_PATHS + (
    "tools/verify_p12_joint_roundtrip.py", "tools/native_regression.py",
    "tests/data/p12-roundtrip-fixtures.json", "tests/test_joint_native_readback.py",
    "tests/test_joint_roundtrip_contract.py", "tests/test_joint_native_format.py",
    "tests/test_joint_source_identity.py", "pyproject.toml", "uv.lock",
)
MOTOR_R1_KEYWORDS = frozenset(("*CONSTRAINED_JOINT_ROTATIONAL_MOTOR_ID",
                               "*CONSTRAINED_JOINT_TRANSLATIONAL_MOTOR_ID"))
MOTOR_R1_FORMAT_SOURCE = {
    "manual": {"release": "R11", "volume": "I", "pdf_page": 735, "printed_page": "10-57",
               "sha256": "3f1cf3cc8c8222ad059459aca2c452f6af6afcce263b8eb8ba157495684da343",
               "scope": "R1 radius applies to gear/pulley; this does not establish a motor blank=zero default"},
    "sdk": {"package": "ansys-dyna-core", "version": "0.12.1", "field": "r1", "columns": "31-40",
            "scope": "Both motor classes mark R1 not to be defined; schema blank default is None",
            "class_sha256": {
                "constrained_joint_rotational_motor.py": "8d0d3b5445f2a05ab70fe2dd2ad0be72bc578c046381d47cec98db1a27e54be9",
                "constrained_joint_translational_motor.py": "1371ab91335160cda6611c5b3ab4e61e38f7f519f89f62fe03d61a218912596f"}},
    "observed_capture": {"actual_git_revision": "1b7fc6047c61b9df9f9f14f1cfc2d1a4001445f3",
                         "comparison_sha256": "bb4d4dfca9cebf4a6547da90e2d54cfe5c991cfabc494beaaa0feaede8b9049d",
                         "scope": "4.13 export changed blank R1 to 0.0 for the two registered type-0 motors"},
}


def plain(value):
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    return value


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def capture_source_identity(identity):
    """Require current critical dependencies; historical captures are never backfilled."""
    captured = identity.get("source_files")
    if not isinstance(captured, dict):
        raise ValueError("Missing required capture source hashes")
    for path in CAPTURE_SOURCE_PATHS:
        digest = captured.get(path)
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None or not (ROOT / path).is_file():
            raise ValueError("Missing required capture source: " + path)
        if sha(ROOT / path) != digest:
            raise ValueError("Required capture source changed after identity capture: " + path)
    revision = identity.get("actual_git_head")
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("Cannot resolve committed capture source revision")
    try:
        output = subprocess.check_output(["git", "ls-tree", "-r", revision, "--", *CAPTURE_SOURCE_PATHS],
                                         cwd=ROOT, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("Cannot resolve committed capture source identities") from error
    blobs = {}
    for line in output.splitlines():
        metadata, path = line.split("\t", 1)
        mode, kind, blob = metadata.split()
        if mode in ("100644", "100755") and kind == "blob":
            blobs[path] = blob
    missing = set(CAPTURE_SOURCE_PATHS) - blobs.keys()
    if missing:
        raise ValueError("Missing committed capture source identities: " + ", ".join(sorted(missing)))
    return {path: dict(git_blob_id=blobs[path], captured_file_sha256=captured[path]) for path in CAPTURE_SOURCE_PATHS}


def fixture(name):
    data = json.loads(FIXTURES.read_text(encoding="utf8"))
    if name not in data["cases"]:
        raise ValueError("Unknown P12 fixture")
    return copy.deepcopy(data["cases"][name])


def build_source(name, directory):
    """Serialize tiny input geometry only; production add_joint creates every Joint."""
    spec = fixture(name)
    directory.mkdir(parents=True, exist_ok=False)
    nodes, elements, parts = [], [], []
    for index, part in enumerate(spec["input"]["parts"], 1):
        lo, hi, base = part["lo"], part["hi"], part["node_base"]
        corners = [(lo[0], lo[1], lo[2]), (hi[0], lo[1], lo[2]), (hi[0], hi[1], lo[2]), (lo[0], hi[1], lo[2]),
                   (lo[0], lo[1], hi[2]), (hi[0], lo[1], hi[2]), (hi[0], hi[1], hi[2]), (lo[0], hi[1], hi[2])]
        nodes += [f"{base+n:>8}" + "".join(f"{float(v):>16g}" for v in point) for n, point in enumerate(corners, 1)]
        elements.append("".join(f"{v:>8}" for v in (1000+index, part["pid"], *range(base+1, base+9))))
        parts += ["*PART", f"fixture Part {part['pid']}", f"{part['pid']:>10}{1:>10}{part['mid']:>10}"]
    lines = ["*KEYWORD", "*TITLE", "P12 owned definition fixture", "*NODE", *nodes,
             "*ELEMENT_SOLID", *elements, "*SECTION_SOLID", "         1         1", *parts,
             "*MAT_RIGID", "         1   7.85e-9    210000       0.3", "         1         7         7", "         0",
             "*MAT_RIGID", "         2   7.85e-9    210000       0.3", "         0", "         0",
             "*CONTROL_RIGID", "         1", "*CONTROL_TERMINATION", "       0.1"]
    if any(part["mid"] == 3 for part in spec["input"]["parts"]):
        lines += ["*MAT_ELASTIC", "         3   7.85e-9    210000       0.3"]
    for item in spec["input"]["sets"]:
        lines += ["*SET_NODE_LIST", f"{item['sid']:>10}", "".join(f"{n:>10}" for n in item["members"])]
    for item in spec["input"]["cnrbs"]:
        lines += ["*CONSTRAINED_NODAL_RIGID_BODY", f"{item['pid']:>10}{0:>10}{item['nsid']:>10}"]
    for lcid, points in spec["input"]["curves"].items():
        lines += ["*DEFINE_CURVE", f"{int(lcid):>10}", *[f"{float(a):>20g}{float(o):>20g}" for a, o in points]]
    path = directory / "main.k"
    path.write_text("\n".join([*lines, "*END", ""]), encoding="utf8", newline="\n")
    return path, spec


def _fields(deck, block, row=None):
    values = {}
    for field in deck.fields(block, row):
        if field.name in values:
            raise ValueError("Ambiguous named field in verification projection: " + field.name)
        values[field.name] = field.value
    return values


def _rows(deck, block):
    layout = deck.layout(block)
    return [_fields(deck, block, key) for key in layout.rows] if layout.key else [_fields(deck, block)]


def joint_records(deck, block):
    """Locate all instances with the existing engine, then read its named fields."""
    kind = joint_kind(block.name)
    if kind not in KINDS:
        raise ValueError("Unverified Joint keyword in readback: " + block.name)
    instances = joint_instances(deck, block)
    starts = [site["line"] - block.line_number for site, _ in instances]
    data_lines = {index for index, _ in block.data()}
    if not starts or starts != sorted(set(starts)) or starts[0] != min(data_lines):
        raise ValueError("Joint instance boundaries do not cover the block")
    result, covered = [], set()
    for start, end in zip(starts, [*starts[1:], len(block.lines)]):
        text = "*KEYWORD\n" + block.lines[0] + "".join(block.lines[start:end]) + "*END\n"
        # Use the existing lossless block parser and named-field engine in memory.
        source = SourceFile(block.file.path, encode(text), parse_blocks(text))
        for item in source.blocks:
            item.file = source
        projection = KeywordDeck(source, [], network=False)
        candidates = [item for item in projection.iter_blocks() if item.name.startswith("*CONSTRAINED_JOINT_")]
        if len(candidates) != 1:
            raise ValueError("Joint projection is not exactly one instance")
        projected = candidates[0]
        rows = _rows(projection, projected)
        if len(rows) != 1:
            raise ValueError("Joint named-field projection did not resolve to one instance")
        layout = projection.layout(projected)
        infos = [*layout.fields, *[info for fields in layout.rows.values() for info in fields]]
        if not {n for n, _ in projected.data()} <= {info.slot.line for info in infos}:
            raise ValueError("Joint named fields leave unread data cards")
        record = rows[0]
        record.update(kind=kind, keyword=block.name)
        result.append(record)
        covered.update(index for index in data_lines if start <= index < end)
    if covered != data_lines:
        raise ValueError("Joint instance reader skipped data cards")
    return result


def _unique(mapping, key, value, label):
    if type(key) is not int or key in mapping:
        raise ValueError("Invalid or duplicate " + label + " in readback")
    mapping[key] = value


def snapshot(path):
    """Read only a self-contained output with the established keyword engine."""
    path = Path(path).absolute()
    guard = access.root_guard((path.parent,))
    with access.confined(guard):
        guard(path)
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("P12 verification output exceeds 10 MiB")
        preflight = preflight_includes(path)
        if not preflight["ok"] or preflight["references"] or len(preflight["files"]) != 1:
            raise ValueError("P12 readback must be a self-contained single file")
        deck = KeywordDeck.load(path)
        result = dict(joints={}, nodes={}, parts={}, extra_nodes={}, cnrbs={}, curves={}, solids={})
        sets, rigid_materials = {}, set()
        for block in deck.iter_blocks():
            name = block.name
            if name.startswith("*CONSTRAINED_JOINT_"):
                for record in joint_records(deck, block):
                    _unique(result["joints"], record.get("jid"), record, "Joint ID")
            elif name == "*NODE":
                for record in _rows(deck, block):
                    _unique(result["nodes"], record["nid"], [record[k] for k in ("x", "y", "z")], "Node ID")
            elif name == "*PART":
                for record in _rows(deck, block):
                    _unique(result["parts"], record["pid"], record["mid"], "Part ID")
            elif name in ("*MAT_RIGID", "*MAT_020"):
                rigid_materials.update(record["mid"] for record in _rows(deck, block))
            elif name == "*ELEMENT_SOLID":
                for record in _rows(deck, block):
                    _unique(result["solids"], record["eid"], dict(pid=record["pid"], nodes=[record[f"n{i}"] for i in range(1, 9)]), "Solid ID")
            elif name.startswith("*ELEMENT_"):
                raise ValueError("Unverified alternate element representation in fixture export")
            elif name.startswith("*SET_NODE_LIST"):
                sid = deck.get(block, "sid").value
                _unique(sets, sid, deck.members(block), "Node Set ID")
            elif name == "*CONSTRAINED_EXTRA_NODES_SET":
                for record in _rows(deck, block):
                    key = (record["pid"], record["nsid"])
                    if key in result["extra_nodes"]:
                        raise ValueError("Duplicate extra-node attachment")
                    result["extra_nodes"][key] = None
            elif name.startswith("*CONSTRAINED_EXTRA_NODES"):
                raise ValueError("Unverified alternate extra-node representation")
            elif name == "*CONSTRAINED_NODAL_RIGID_BODY":
                for record in _rows(deck, block):
                    _unique(result["cnrbs"], record["pid"], dict(nsid=record["nsid"]), "CNRB ID")
            elif name.startswith("*CONSTRAINED_NODAL_RIGID_BODY"):
                raise ValueError("Unverified alternate CNRB representation")
            elif name in ("*DEFINE_CURVE", "*DEFINE_CURVE_TITLE"):
                _unique(result["curves"], deck.get(block, "lcid").value, deck.points(block), "Curve ID")
        for pid, nsid in result["extra_nodes"]:
            if result["parts"].get(pid) not in rigid_materials or nsid not in sets:
                raise ValueError("Extra nodes lack a declared rigid Part and node set")
            result["extra_nodes"][(pid, nsid)] = sorted(sets[nsid])
        for record in result["cnrbs"].values():
            if record["nsid"] not in sets:
                raise ValueError("CNRB references a missing node set")
            record["members"] = sorted(sets[record["nsid"]])
        return result


def compare(path, expected):
    """Strict named-field comparison, including the blank motor R1 slot."""
    return _projection_differences(snapshot(path), expected)


def _projection_differences(actual, expected):
    differences = []

    def equal(field, wanted, observed):
        if observed != wanted:
            differences.append(dict(field=field, expected=wanted, actual=observed))

    def real(field, wanted, observed):
        if (type(observed) not in (int, float) or not math.isfinite(observed)
                or not math.isclose(observed, wanted, rel_tol=RTOL, abs_tol=ATOL)):
            differences.append(dict(field=field, expected=wanted, actual=observed))

    equal("node_count", expected["node_count"], len(actual["nodes"]))
    equal("solid_count", expected["solid_count"], len(actual["solids"]))
    equal("solids", {int(k): v for k, v in expected["solids"].items()}, actual["solids"])
    equal("node_ids", sorted(int(k) for k in expected["nodes"]), sorted(actual["nodes"]))
    equal("parts", {int(k): v for k, v in expected["parts"].items()}, actual["parts"])
    wanted_ids = {record["jid"] for record in expected["joints"]}
    equal("joint_ids", sorted(wanted_ids), sorted(actual["joints"]))
    for joint in expected["joints"]:
        observed = actual["joints"].get(joint["jid"], {})
        prefix = f"Joint {joint['jid']}."
        # This producer covers ordinary _ID cards only.  Extra LOCAL/FAILURE
        # fields change the definition even when every core node/value matches.
        fields = {"jid", "heading", "kind", "keyword", "rps", "damp",
                  *(f"n{i}" for i in range(1, 7))}
        fields.update(key for key in ("lcid", "type", "parm", "r1") if key in joint)
        equal(prefix + "field_names", sorted(fields), sorted(observed))
        equal(prefix + "keyword", joint["keyword"], observed.get("keyword"))
        equal(prefix + "heading", joint["heading"], observed.get("heading"))
        equal(prefix + "jid", joint["jid"], observed.get("jid"))
        equal(prefix + "kind", joint["kind"], observed.get("kind"))
        for index, node in enumerate(joint["nodes"], 1):
            equal(prefix + f"n{index}", node, observed.get(f"n{index}") or 0)
        for key in ("rps", "damp", "parm", "r1"):
            if key in joint:
                if joint[key] is None:
                    equal(prefix + key, None, observed.get(key))
                else:
                    real(prefix + key, joint[key], observed.get(key))
        for key in ("lcid", "type"):
            if key in joint:
                equal(prefix + key, joint[key], observed.get(key))
    for uid, point in expected["nodes"].items():
        observed = actual["nodes"].get(int(uid), [None]*3)
        for axis, wanted, value in zip("xyz", point, observed):
            real(f"Node {uid}.{axis}", wanted, value)
    equal("extra_nodes", {(r["pid"], r["nsid"]): sorted(r["members"]) for r in expected["extra_nodes"]}, actual["extra_nodes"])
    equal("cnrbs", {r["pid"]: {"nsid": r["nsid"], "members": sorted(r["members"])} for r in expected["cnrbs"]}, actual["cnrbs"])
    equal("curves", {int(k): [tuple(p) for p in v] for k, v in expected["curves"].items()}, actual["curves"])
    return differences


def native_export_comparison(path, expected):
    """Audit writer representation separately; never relax default/offline comparison."""
    actual = snapshot(path)
    strict = _projection_differences(actual, expected)
    eligible = {}
    for joint in expected["joints"]:
        observed = actual["joints"].get(joint["jid"], {})
        keyword = joint.get("keyword")
        value = observed.get("r1")
        if (keyword in MOTOR_R1_KEYWORDS and observed.get("keyword") == keyword
                and "r1" in joint and joint["r1"] is None and "r1" in observed
                and type(joint.get("type")) is int and joint["type"] == 0
                and type(observed.get("type")) is int and observed["type"] == 0
                and type(value) in (int, float) and value == 0):
            eligible[f"Joint {joint['jid']}.r1"] = value
    normalizations, differences = [], []
    for difference in strict:
        field = difference["field"]
        if field in eligible:
            normalizations.append(dict(field=field, expected=None, actual=eligible[field],
                rule="native_motor_type0_inapplicable_r1_zero_fill", source=copy.deepcopy(MOTOR_R1_FORMAT_SOURCE)))
        else:
            differences.append(difference)
    return dict(strict_card_differences=strict, format_normalizations=normalizations, differences=differences)


def _one_file(path):
    path = Path(path)
    return dict(sha256=sha(path), names=sorted(p.name for p in path.parent.iterdir()))


def prepare_case(name, directory, executable=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    source, spec = build_source(name, directory / "input")
    before = _one_file(source)
    service = Service(Settings(directory / "work", executable, (source.parent,), timeout=60))
    created = service.create_entities(str(source), spec["operations"])
    if created["status"] != "succeeded":
        raise ValueError("create_entities failed: " + str(created.get("error")))
    edited = Path(created["data"]["main"])
    differences = compare(edited, spec["expected"])
    checked = service.check_model(str(edited))
    if differences or checked["status"] != "succeeded" or checked["data"]["errors"]:
        raise ValueError("Offline P12 fixture failed: " + str(differences or checked))
    if _one_file(source) != before:
        raise ValueError("Original fixture changed during creation")
    return dict(name=name, directory=directory, source=source, service=service, spec=spec,
                edited=edited, source_identity=before, edited_identity=_one_file(edited), creation=created)


def _job(service, result):
    job_id = result.get("job_id")
    if not isinstance(job_id, str) or re.fullmatch(r"[a-f0-9]{32}", job_id) is None:
        raise ValueError("Native result has no owned job identity")
    directory = service.jobs.root / job_id
    manifest = service.jobs.get(job_id)
    if (manifest.get("job_id") != job_id or result.get("status") != "succeeded"
            or manifest.get("status") != "succeeded"):
        raise ValueError("Native API job failed: " + str(result.get("error") or manifest.get("error")))
    if directory.is_symlink() or getattr(directory.lstat(), "st_file_attributes", 0) & 0x400:
        raise ValueError("Native job directory is an unexpected link")
    return directory, manifest


def _engine(manifest):
    engine = manifest.get("engine_result") or {}
    process = engine.get("data") or {}
    if (engine.get("job_id") != manifest.get("job_id") or engine.get("operation") != manifest.get("action")
            or engine.get("backend") != "lsprepost" or engine.get("stage") != "execution"
            or engine.get("status") not in ("unverified", "succeeded") or engine.get("error")
            or type(process.get("pid")) is not int or process["pid"] <= 0
            or process.get("graphics") is not False or "-nographics" not in process.get("argv", [])
            or process.get("returncode") != 0 or process.get("timed_out")):
        raise ValueError("Native job lacks successful owned headless execution evidence")
    if any(check.get("required", True) and check.get("status") not in ("passed", "not_applicable")
           for check in engine.get("checks", [])):
        raise ValueError("Native job lacks successful owned headless execution evidence: required checks")


def verify_native(prepared, identity):
    """Three existing API processes; no raw-tree purpose or lower-level runner workaround."""
    service, source, edited = prepared["service"], prepared["source"], prepared["edited"]
    if not identity.get("actual_git_head") or identity.get("working_tree_dirty") is not False:
        raise ValueError("Native readback requires a clean actual Git identity")
    sources = capture_source_identity(identity)
    executable = service.settings.native_executable()
    config = locate_config(executable, os.environ)
    if config is None:
        raise ValueError("An initialized native configuration is required")
    binary_sha, config_sha = sha(executable), sha(config)
    proof = dict(case=prepared["name"], actual_git_revision=identity["actual_git_head"],
        working_tree_dirty=identity["working_tree_dirty"], git_diff_sha256=identity["git_diff_sha256"],
        source_snapshot_sha256=identity["source_snapshot_sha256"], native_executed=False, status="failed",
        typed_joint_recognition="unverified", motion_verification="not_run",
        executable_sha256=binary_sha, source_config_sha256=config_sha,
        product_source_identity={path: sources[path] for path in PRODUCT_PATHS},
        auxiliary_source_identity={path: sources[path] for path in CAPTURE_SOURCE_PATHS if path not in PRODUCT_PATHS},
        producer_source_identity=sources["tools/verify_p12_joint_roundtrip.py"],
        fixture_source_identity=sources["tests/data/p12-roundtrip-fixtures.json"],
        source_identity_scope="Required critical call paths and producer/fixture/tests/lock; full source snapshot remains separate",
        scope="Owned synthetic single-file definition export roundtrip in a separate export process",
        differences=[], strict_card_differences=None, format_normalizations=[])
    saved_main, saved_before = None, None

    def remember_process(result):
        job_id = result.get("job_id")
        if isinstance(job_id, str) and re.fullmatch(r"[a-f0-9]{32}", job_id):
            manifest = service.jobs.get(job_id)
            process = (manifest.get("engine_result") or {}).get("data") or {}
            if type(process.get("pid")) is int and process["pid"] > 0:
                proof["native_executed"] = True
                proof.setdefault("native_job_ids", []).append(job_id)

    try:
        saved = service.save_model(str(edited))
        proof["save_model"] = saved
        for observation in saved.get("data", {}).get("observations", {}).values():
            remember_process(observation)
        saved_dir, _ = _job(service, saved)
        for observation in saved["data"]["observations"].values():
            manifest = service.jobs.get(observation["job_id"])
            _engine(manifest)
        saved_main = Path(saved["data"]["main"])
        access.root_guard((saved_dir,))(saved_main)
        reopened = saved["data"]["observations"]["after_reopen"].get("input_open") or {}
        reopened_guard = access.root_guard((saved_main.parent,))
        reopened_guard(Path(reopened.get("cwd", "")))
        reopened_guard(Path(reopened.get("resolved_main", "")))
        if (reopened.get("normalized") is not False or reopened.get("load_name") != saved_main.name
                or Path(reopened.get("cwd", "")).resolve() != saved_main.parent.resolve()
                or Path(reopened.get("resolved_main", "")).resolve() != saved_main.resolve()):
            raise ValueError("P11 did not attest the actual saved-root reopen")
        if _one_file(edited) != prepared["edited_identity"] or sha(saved_main) != sha(edited):
            raise ValueError("P11 did not preserve this single-file fixture's bytes")
        saved_before = _one_file(saved_main)
        exported = service.export_keyword(str(saved_main))
        proof["export_result"] = exported
        remember_process(exported)
        export_dir, manifest = _job(service, exported)
        proof["export_job_id"] = manifest["job_id"]
        _engine(manifest)
        request = json.loads((export_dir / "request.json").read_text(encoding="utf8"))
        staged = export_dir / "input_data"
        staged_guard = access.root_guard((export_dir,))
        staged_guard(Path(request.get("model", "")))
        if (request.get("raw_keyword_tree") or "input_tree" in manifest
                or Path(request.get("model", "")).resolve() != staged.resolve()
                or not stat.S_ISREG(staged.lstat().st_mode) or staged.is_symlink()
                or getattr(staged.lstat(), "st_file_attributes", 0) & 0x400
                or sha(staged) != sha(saved_main) or staged.read_bytes() != saved_main.read_bytes()):
            raise ValueError("Export did not read a byte-identical standalone staged copy")
        readback = export_dir / "model.k"
        if (not stat.S_ISREG(readback.lstat().st_mode) or readback.is_symlink()
                or getattr(readback.lstat(), "st_file_attributes", 0) & 0x400
                or readback.resolve().parent != export_dir.resolve()):
            raise ValueError("Native export is not an owned regular keyword output")
        registered = [a for a in exported.get("artifacts", []) if a.get("kind") == "keyword"
                      and Path(a.get("path", "")) == readback]
        if len(registered) != 1 or registered[0].get("sha256") != sha(readback):
            raise ValueError("Native exported keyword differs from its registered artifact")
        proof.update(native_export_comparison(readback, prepared["spec"]["expected"]))
        if proof["differences"]:
            raise ValueError("Native Joint definition readback differs from hand-written expectations")
        if _one_file(saved_main) != saved_before or _one_file(edited) != prepared["edited_identity"]:
            raise ValueError("Saved/edited fixture changed during native export")
        proof.update(native_executed=True, status="passed", readback_sha256=sha(readback),
                     staged_input_sha256=sha(staged), saved_sha256=sha(saved_main),
                     joint_count=len(prepared["spec"]["expected"]["joints"]))
    except Exception as error:
        proof["error"] = dict(type=type(error).__name__, message=str(error))
        raise
    finally:
        guards = dict(original_unchanged=lambda: _one_file(source) == prepared["source_identity"],
                      edited_unchanged=lambda: _one_file(edited) == prepared["edited_identity"],
                      executable_unchanged=lambda: sha(executable) == binary_sha,
                      configuration_unchanged=lambda: sha(config) == config_sha)
        if saved_main is not None and saved_before is not None:
            guards["saved_unchanged"] = lambda: _one_file(saved_main) == saved_before
        def checkout_unchanged():
            after = execution_identity(ROOT)
            return (after["actual_git_head"] == identity["actual_git_head"]
                    and after["working_tree_dirty"] is False
                    and after["source_snapshot_sha256"] == identity["source_snapshot_sha256"])
        guards["checkout_unchanged"] = checkout_unchanged
        for name, check in guards.items():
            try:
                proof[name] = bool(check())
            except Exception as error:
                proof[name] = False
                proof.setdefault("guard_errors", {})[name] = str(error)
        if not all(proof[name] for name in guards):
            proof["status"] = "failed"
        (prepared["directory"] / "comparison.json").write_text(json.dumps(plain(proof), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8")
        if not all(proof[name] for name in guards):
            if "error" not in proof:
                raise ValueError("P12 source/executable/configuration identity guard failed")
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("pilot", "nine_types", "body_modes"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-native", action="store_true")
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--profile", choices=("4.13", "4.10"))
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT):
        parser.error("--output must be a fresh directory outside the checkout")
    if args.run_native:
        if args.executable is None or args.profile is None:
            parser.error("--run-native requires --executable and an explicit registered --profile")
        policy = require_installation(args.executable, version=args.profile)
        if policy["version_source"] != "file_version_resource":
            parser.error("Native fixture requires an identifiable executable file-version resource")
        require_capability(args.executable, "batch")
        identity = execution_identity(ROOT)
        if not identity["actual_git_head"] or identity["working_tree_dirty"] is not False:
            parser.error("Native fixture requires a clean actual Git checkout")
        capture_source_identity(identity)
        config = locate_config(args.executable, os.environ)
        if config is None:
            parser.error("An initialized native configuration is required")
        binary_sha, config_sha = sha(args.executable), sha(config)
    prepared = prepare_case(args.case, output, args.executable)
    if args.run_native:
        prepared_identity = execution_identity(ROOT, output)
        if (prepared_identity["actual_git_head"] != identity["actual_git_head"]
                or prepared_identity["working_tree_dirty"] is not False
                or prepared_identity["source_snapshot_sha256"] != identity["source_snapshot_sha256"]):
            raise ValueError("Checkout changed during offline fixture preparation; native launch refused")
        (output / "execution-context.json").write_text(json.dumps(prepared_identity, indent=2) + "\n", encoding="utf8")
        try:
            proof = verify_native(prepared, identity)
        finally:
            if sha(args.executable) != binary_sha or sha(config) != config_sha:
                raise ValueError("Native executable/configuration changed during fixture verification")
    else:
        proof = dict(status="passed", native_executed=False, scope="Offline Python creation/check only",
                     case=args.case, joints=len(prepared["spec"]["expected"]["joints"]))
    print(json.dumps(plain(proof), ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
