"""P10 owned explicit-field definition readback; offline by default, never a solver test."""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import stat
import subprocess
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model import KeywordDeck, access, preflight_includes
from ls_prepost_mcp.engine.environment import locate_config
from ls_prepost_mcp.native.versions import require_capability, require_installation
from ls_prepost_mcp.service import Service
from tools import verify_p05_boundary_roundtrip as shared
from tools.native_regression import execution_identity
from tools.probe_node_set_ids_native import native_processes

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/data/p10-control-roundtrip.json"
# This verifier reuses P05's existing-API artifact guards, not a second native runner.
PRODUCT_PATHS = tuple(dict.fromkeys((*shared.PRODUCT_PATHS,
    "src/ls_prepost_mcp/domain/model/controls.py", "src/ls_prepost_mcp/domain/model/materials.py",
    "src/ls_prepost_mcp/model_recipes.py", "src/ls_prepost_mcp/data/model_recipes.json",
    "src/ls_prepost_mcp/automation/recipes.py", "src/ls_prepost_mcp/core/validation.py",
    "src/ls_prepost_mcp/core/contracts.py")))
CAPTURE_SOURCE_PATHS = PRODUCT_PATHS + (
    "tools/verify_p10_control_roundtrip.py", "tools/verify_p05_boundary_roundtrip.py",
    "tools/native_regression.py", "tools/probe_node_set_ids_native.py",
    "tests/data/p10-control-roundtrip.json", "tests/test_control_roundtrip_contract.py", "pyproject.toml", "uv.lock",
)
ATOL, RTOL = 1e-13, 1e-8


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf8"))


def recipe_parameters(spec=None):
    """Explicit caller input for model:control-output; never derive an oracle from readback."""
    spec = fixture() if spec is None else spec
    values = dict(units=spec["units"])
    for operation in spec["operations"]:
        name = operation["recipe"]
        if operation["op"] != "set_control" or name in values or operation.get("units") != spec["units"]:
            raise ValueError("The owned bundle needs unique explicit set_control inputs and units")
        values[name] = copy.deepcopy(operation["params"])
    if set(values) != {"units", "termination", "timestep", "hourglass", "energy", "d3plot", "ascii"}:
        raise ValueError("The owned eight-card bundle requires all six explicit components")
    return values


def source_identity(identity):
    captured = identity.get("source_files", {})
    if not isinstance(captured, dict):
        raise ValueError("Missing required capture source hashes")
    for path in CAPTURE_SOURCE_PATHS:
        value = captured.get(path)
        if (not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
                or not (ROOT / path).is_file() or shared.sha(ROOT / path) != value):
            raise ValueError("Missing or changed required capture source: " + path)
    revision = identity.get("actual_git_head", "")
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("Missing committed capture source revision")
    rows = subprocess.check_output(["git", "ls-tree", "-r", revision, "--", *CAPTURE_SOURCE_PATHS], cwd=ROOT, text=True, timeout=20)
    blobs = {line.split("\t", 1)[1]: line.split("\t", 1)[0].split()[2] for line in rows.splitlines()}
    if set(CAPTURE_SOURCE_PATHS) != set(blobs):
        raise ValueError("Required capture sources must exist in the actual committed revision")
    return {path: dict(git_blob_id=blobs[path], captured_file_sha256=captured[path]) for path in CAPTURE_SOURCE_PATHS}


def snapshot(path):
    """Existing guarded AST/named fields only; complete control observations keep blanks and raw tokens."""
    path = Path(path).absolute()
    guard = access.root_guard((path.parent,))
    with access.confined(guard):
        guard(path)
        shared._regular(path)
        preflight = preflight_includes(path)
        if not preflight["ok"] or preflight["references"] or len(preflight["files"]) != 1:
            raise ValueError("P10 readback requires an owned standalone single file")
        deck = KeywordDeck.load(path)
        result = dict(controls={}, nodes={}, solids={}, parts={}, sections={}, materials={})
        for block in deck.iter_blocks():
            name = block.name
            if name.startswith(("*CONTROL_", "*DATABASE_")):
                if name in result["controls"] or block.keyword.flag or block.keyword.extra:
                    raise ValueError("Duplicate or unverified control keyword options: " + name)
                fields, raw = {}, {}
                for info in deck.layout(block).fields:
                    if info.name in fields:
                        raise ValueError("Ambiguous control field: " + info.name)
                    value = deck.get(block, info.name, card=info.card)
                    fields[info.name], raw[info.name] = value.value, value.raw
                result["controls"][name] = dict(fields=fields, raw_fields=raw, raw_lines=list(block.lines))
            elif name == "*NODE":
                for row in shared._rows(deck, block):
                    shared._unique(result["nodes"], str(row["nid"]), [row[key] for key in ("x", "y", "z")])
            elif name == "*ELEMENT_SOLID":
                for row in shared._rows(deck, block):
                    shared._unique(result["solids"], str(row["eid"]), dict(pid=row["pid"], nodes=[row[f"n{i}"] for i in range(1, 9)]))
            elif name == "*PART":
                for row in shared._rows(deck, block):
                    shared._unique(result["parts"], str(row["pid"]), dict(secid=row["secid"], mid=row["mid"]))
            elif name == "*SECTION_SOLID":
                shared._unique(result["sections"], str(deck.get(block, "secid").value), dict(elform=deck.get(block, "elform").value))
            elif name == "*MAT_ELASTIC":
                shared._unique(result["materials"], str(deck.get(block, "mid").value),
                               dict(keyword=name, **{key: deck.get(block, key).value for key in ("ro", "e", "pr")}))
            elif name not in ("*KEYWORD", "*TITLE", "*END"):
                raise ValueError("Unverified fixture keyword: " + name)
        references = deck.references()
        result["references"] = dict(dangling=references.dangling_count, duplicates=len(references.duplicates()))
        return result


def projection_differences(actual, spec):
    """Only handwritten caller fields are expectations; every other native value stays an observation."""
    differences = []

    def compare(value, expected, label):
        if isinstance(expected, dict):
            if not isinstance(value, dict) or set(value) != set(expected):
                differences.append(dict(field=label, expected=expected, actual=value))
            else:
                for key in expected:
                    compare(value[key], expected[key], label + "." + key)
        elif isinstance(expected, list):
            if not isinstance(value, list) or len(value) != len(expected):
                differences.append(dict(field=label, expected=expected, actual=value))
            else:
                for i, item in enumerate(expected):
                    compare(value[i], item, label + "." + str(i))
        elif isinstance(expected, (int, float)):
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not math.isclose(value, expected, rel_tol=RTOL, abs_tol=ATOL)):
                differences.append(dict(field=label, expected=expected, actual=value))
        elif value != expected:
            differences.append(dict(field=label, expected=expected, actual=value))

    for keyword, fields in spec["expected"]["controls"].items():
        observed = actual["controls"].get(keyword, {}).get("fields", {})
        for field, expected in fields.items():
            compare(observed.get(field), expected, keyword + "." + field)
    for key in ("nodes", "solids", "parts", "sections", "materials"):
        compare(actual[key], spec["expected"][key], key)
    compare(actual["references"], dict(dangling=0, duplicates=0), "references")
    return differences


def compare(path, spec):
    return projection_differences(snapshot(path), spec)


def prepare_case(directory, executable=None, *, spec=None, creation_mode="edit_keywords",
                 recipe_reference=None, recipe_parameters=None):
    """Base editing is offline prep; actual task-native verification requires the pinned recipe mode."""
    spec = copy.deepcopy(fixture() if spec is None else spec)
    if not spec.get("units") or any(item.get("units") != spec["units"] for item in spec["operations"]):
        raise ValueError("Every physical input needs the caller-declared units")
    if creation_mode not in ("edit_keywords", "recipe"):
        raise ValueError("Unknown creation mode")
    if creation_mode == "recipe":
        if not isinstance(recipe_reference, str) or re.fullmatch(r"model:[a-z][a-z0-9_-]{0,79}@[a-f0-9]{64}", recipe_reference) is None:
            raise ValueError("Recipe mode requires the explicitly pinned discovered model bundle reference")
        if not isinstance(recipe_parameters, dict) or recipe_parameters.get("units") != spec["units"]:
            raise ValueError("Recipe mode requires explicit parameters and the fixture unit system")
        if len(json.dumps(recipe_parameters, allow_nan=False).encode()) > 1024 * 1024:
            raise ValueError("Recipe parameters exceed the bounded input size")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    source = directory / "input/main.k"
    source.parent.mkdir()
    source.write_text(spec["source"], encoding="ascii", newline="\n")
    before = shared._one_file(source)
    service = Service(Settings(directory / "work", executable, (source.parent,), timeout=60))
    creation = (service.edit_keywords(str(source), spec["operations"]) if creation_mode == "edit_keywords" else
                service.run_recipe(recipe_reference, copy.deepcopy(recipe_parameters), model=str(source), file_type="keyword"))
    if creation.get("status") != "succeeded":
        raise ValueError("P10 input stage failed: " + str(creation.get("error")))
    if creation_mode == "recipe":
        metadata = creation.get("data", {}).get("recipe", {})
        if (creation.get("operation") != "run_recipe" or metadata.get("reference_policy") != "pinned"
                or metadata.get("reference") != recipe_reference or metadata.get("requested_reference") != recipe_reference):
            raise ValueError("Recipe result did not attest the requested pinned bundle")
    edited = Path(creation["data"]["main"])
    shared._job(service, creation)
    report = service.check_model(str(edited))
    differences = compare(edited, spec)
    if differences or report.get("status") != "succeeded" or report["data"]["errors"] or report["data"]["unchecked"]:
        raise ValueError("Offline P10 fixture differs from the independent oracle: " + str(differences or report))
    if shared._one_file(source) != before:
        raise ValueError("Original P10 source changed")
    return dict(directory=directory, source=source, source_identity=before, edited=edited,
                edited_identity=shared._one_file(edited), service=service, spec=spec, creation=creation,
                creation_mode=creation_mode, recipe_reference=recipe_reference)


def profile_inputs_identity(inputs):
    """Both explicit readonly private inputs and executables are monitored; no global-profile fallback."""
    if not isinstance(inputs, dict) or set(inputs) != {"4.13", "4.10"}:
        raise ValueError("Declare both registered private profile inputs")
    output = {}
    for version, item in inputs.items():
        executable, source = Path(item["executable"]), Path(item["source"])
        shared._regular(source)
        info = source.stat()
        readonly = bool(info.st_file_attributes & 1) if hasattr(info, "st_file_attributes") else not (info.st_mode & stat.S_IWUSR)
        if not readonly:
            raise ValueError("Private configuration origin must be readonly")
        policy = require_installation(executable, version=version)
        if policy["version_source"] != "file_version_resource":
            raise ValueError("Registered executable file-version resource is required")
        require_capability(executable, "batch")
        output[version] = dict(executable=shared._file_identity(executable), configuration=shared._file_identity(source),
            device=info.st_dev, inode=info.st_ino, readonly=True, profile=policy,
            directory_entries=sorted(path.name for path in source.parent.iterdir()))
    return output


def verify_native(prepared, identity, private_inputs):
    """At most save_model's two observations plus ordinary export: three existing-API jobs."""
    if not identity.get("actual_git_head") or identity.get("working_tree_dirty") is not False:
        raise ValueError("Native verification requires a clean actual Git identity")
    sources = source_identity(identity)
    creation = prepared.get("creation", {})
    recipe_metadata = creation.get("data", {}).get("recipe", {})
    if (prepared.get("creation_mode") != "recipe" or creation.get("operation") != "run_recipe"
            or recipe_metadata.get("reference_policy") != "pinned"
            or recipe_metadata.get("reference") != prepared.get("recipe_reference")
            or recipe_metadata.get("requested_reference") != prepared.get("recipe_reference")):
        raise ValueError("Task-native P10 verification requires actual pinned run_recipe creation")
    profiles = profile_inputs_identity(private_inputs)
    if native_processes():
        raise ValueError("Acquire the serial native lease before verification")
    service, edited, source = prepared["service"], prepared["edited"], prepared["source"]
    executable = service.settings.native_executable()
    selected = [version for version, item in private_inputs.items() if Path(item["executable"]).resolve() == executable.resolve()]
    if len(selected) != 1:
        raise ValueError("Selected executable must match exactly one declared profile")
    version = selected[0]
    explicit_source = os.environ.get("LSPP_CONFIG_SOURCE")
    if not explicit_source or Path(explicit_source).resolve() != Path(private_inputs[version]["source"]).resolve():
        raise ValueError("Set the explicit selected LSPP_CONFIG_SOURCE; global-profile fallback is refused")
    config = locate_config(executable, os.environ)
    if config is None or config.resolve() != Path(private_inputs[version]["source"]).resolve():
        raise ValueError("Selected configuration must be the explicit readonly private input")
    proof = dict(status="failed", native_executed=False, native_attempted=False, scope="P10 explicit control-field definition retention only",
        actual_git_revision=identity["actual_git_head"], working_tree_dirty=False, source_snapshot_sha256=identity["source_snapshot_sha256"],
        capture_source_identity=sources, profiles_before=profiles, native_job_ids=[], observations=[],
        typed_control_recognition="unverified", physical_response="not_run", units=prepared["spec"]["units"])
    proof.update(creation_mode="recipe", recipe_reference=prepared["recipe_reference"], creation=copy.deepcopy(creation))
    proof.update(selected_version=version, binary_profile=copy.deepcopy(profiles[version]["profile"]))
    saved_main, saved_before = None, None

    def process(job_id, expected_action):
        manifest = service.jobs.get(job_id)
        observed = (manifest.get("engine_result") or {}).get("data") or {}
        if type(observed.get("pid")) is int and observed["pid"] > 0:
            proof["native_executed"] = True
            proof["native_job_ids"].append(job_id)
            proof["observations"].append(copy.deepcopy(observed))
        shared._engine(manifest)
        if (manifest.get("action") != expected_action
                or manifest["engine_result"].get("operation") != expected_action):
            raise ValueError("Native job role differs from the expected API stage")
        argv = observed.get("argv")
        recorded_executable = manifest.get("executable") or {}
        recorded_path = recorded_executable.get("path")
        if (not isinstance(argv, list) or not argv or not isinstance(argv[0], str)
                or not isinstance(recorded_path, str) or Path(argv[0]).resolve() != executable.resolve()
                or Path(recorded_path).resolve() != executable.resolve()):
            raise ValueError("Native job executable differs from the selected profile")
        outer_executable = profiles[version]["executable"]
        if (any(recorded_executable.get(key) != outer_executable[key] for key in ("size", "mtime_ns"))
                or recorded_executable.get("sha256") not in (None, outer_executable["sha256"])):
            raise ValueError("Native executable manifest stat/hash does not bind the selected outer fingerprint")
        proof.setdefault("job_bindings", []).append(dict(job_id=job_id, expected_action=expected_action,
            manifest_action=manifest["action"], argv0=argv[0], executable=copy.deepcopy(recorded_executable),
            full_sha256_origin="Outer profile before/after; a stat-only per-job manifest is not a full per-job SHA"))
        if observed.get("process_isolation") != "windows_job":
            raise ValueError("Native process lacks recorded Windows Job isolation")
        configuration = observed.get("configuration", {})
        if (configuration.get("source_sha256") != profiles[version]["configuration"]["sha256"]
                or configuration.get("source_modified") is not False
                or Path(configuration.get("source", "")).resolve() != Path(private_inputs[version]["source"]).resolve()):
            raise ValueError("Native job used another configuration source")

    try:
        if (shared._one_file(source) != prepared["source_identity"]
                or shared._one_file(edited) != prepared["edited_identity"]):
            raise ValueError("Offline input namespace or bytes changed before native verification")
        if compare(edited, prepared["spec"]):
            raise ValueError("Edited input changed before native verification")
        proof["native_attempted"] = True
        saved = service.save_model(str(edited), expected_counts=dict(nodes=8, elements=1), expected_part_ids=[10])
        proof["save_model"] = saved
        observations = saved.get("data", {}).get("observations", {})
        for item in observations.values():
            process(item["job_id"], "inspect_model")
        save_dir, _ = shared._job(service, saved)
        if set(observations) != {"before_save", "after_reopen"}:
            raise ValueError("save_model lacks both required observations")
        saved_main = Path(saved["data"]["main"])
        access.root_guard((save_dir,))(saved_main)
        shared._regular(saved_main)
        opened = observations["after_reopen"].get("input_open") or {}
        if (opened.get("normalized") is not False or opened.get("load_name") != saved_main.name
                or Path(opened.get("cwd", "")).resolve() != saved_main.parent.resolve()
                or Path(opened.get("resolved_main", "")).resolve() != saved_main.resolve()):
            raise ValueError("save_model did not reopen the actual saved root")
        if saved_main.read_bytes() != edited.read_bytes():
            raise ValueError("Saved root changed explicit definitions or geometry bytes")
        saved_before = shared._one_file(saved_main)
        exported = service.export_keyword(str(saved_main))
        proof["export_result"] = exported
        if exported.get("job_id"):
            process(exported["job_id"], "export_keyword")
        export_dir, manifest = shared._job(service, exported)
        request = json.loads((export_dir / "request.json").read_text(encoding="utf8"))
        staged, readback = export_dir / "input_data", export_dir / "model.k"
        shared._regular(staged)
        shared._regular(readback)
        if (request.get("raw_keyword_tree") or "input_tree" in manifest
                or Path(request.get("model", "")).resolve() != staged.resolve() or staged.read_bytes() != saved_main.read_bytes()):
            raise ValueError("Ordinary export did not stage byte-identical saved input")
        artifacts = [item for item in exported.get("artifacts", []) if item.get("kind") == "keyword" and Path(item["path"]) == readback]
        if len(artifacts) != 1 or artifacts[0].get("sha256") != shared.sha(readback):
            raise ValueError("Readback lacks exact registered output artifact")
        actual = snapshot(readback)
        proof.update(native_observation=actual, explicit_expected=copy.deepcopy(prepared["spec"]["expected"]),
                     differences=projection_differences(actual, prepared["spec"]))
        if proof["differences"] or len(proof["native_job_ids"]) != 3 or len(set(proof["native_job_ids"])) != 3:
            raise ValueError("Readback differs or does not contain exactly three distinct native jobs")
        proof.update(status="passed", saved_sha256=shared.sha(saved_main), staged_input_sha256=shared.sha(staged),
                     readback_sha256=shared.sha(readback), control_count=len(actual["controls"]),
                     explicit_control_count=len(prepared["spec"]["expected"]["controls"]))
    except Exception as error:
        proof["error"] = dict(type=type(error).__name__, message=str(error))
        raise
    finally:
        def same_checkout():
            after = execution_identity(ROOT)
            proof["source_after"] = {key: after[key] for key in ("actual_git_head", "working_tree_dirty", "source_snapshot_sha256")}
            return (after["actual_git_head"] == identity["actual_git_head"] and after["working_tree_dirty"] is False
                    and after["source_snapshot_sha256"] == identity["source_snapshot_sha256"])

        def same_profiles():
            proof["profiles_after"] = profile_inputs_identity(private_inputs)
            return proof["profiles_after"] == profiles

        guards = dict(source_unchanged=lambda: shared._one_file(source) == prepared["source_identity"],
            edited_unchanged=lambda: shared._one_file(edited) == prepared["edited_identity"],
            profiles_unchanged=same_profiles,
            checkout_unchanged=same_checkout, no_native_processes_remain=lambda: not native_processes())
        if saved_main is not None and saved_before is not None:
            guards["saved_unchanged"] = lambda: shared._one_file(saved_main) == saved_before
        proof["guards"] = {}
        for name, check in guards.items():
            try:
                proof["guards"][name] = bool(check())
            except Exception as error:
                proof["guards"][name] = False
                proof.setdefault("guard_errors", {})[name] = str(error)
        if not all(proof["guards"].values()):
            proof["status"] = "failed"
        (prepared["directory"] / "comparison.json").write_text(json.dumps(shared._plain(proof), ensure_ascii=False,
            allow_nan=False, separators=(",", ":")) + "\n", encoding="utf8")
        if proof["status"] != "passed" and "error" not in proof:
            raise ValueError("P10 source/profile/namespace identity guard failed")
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-native", action="store_true")
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--profile", choices=("4.13", "4.10"))
    parser.add_argument("--private-inputs", type=Path)
    parser.add_argument("--creation-mode", choices=("edit_keywords", "recipe"), default="edit_keywords")
    parser.add_argument("--recipe-reference")
    parser.add_argument("--recipe-parameters", type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to(ROOT):
        parser.error("--output must be fresh and outside the checkout")
    identity, inputs = None, None
    parameters = json.loads(args.recipe_parameters.read_text(encoding="utf8")) if args.recipe_parameters else None
    if args.run_native:
        if args.creation_mode != "recipe":
            parser.error("Task-native mode requires --creation-mode recipe and a new pinned bundle reference")
        if args.executable is None or args.profile is None or args.private_inputs is None:
            parser.error("--run-native requires executable, registered profile and explicit two-profile private inputs")
        identity = execution_identity(ROOT)
        if identity["working_tree_dirty"] is not False:
            parser.error("Native mode requires a clean committed checkout")
        source_identity(identity)
        inputs = json.loads(args.private_inputs.read_text(encoding="utf8"))
        require_installation(args.executable, version=args.profile)
    prepared = prepare_case(args.output, args.executable, creation_mode=args.creation_mode,
                            recipe_reference=args.recipe_reference, recipe_parameters=parameters)
    if args.run_native:
        previous = os.environ.get("LSPP_CONFIG_SOURCE")
        os.environ["LSPP_CONFIG_SOURCE"] = inputs[args.profile]["source"]
        try:
            proof = verify_native(prepared, identity, inputs)
        finally:
            if previous is None:
                os.environ.pop("LSPP_CONFIG_SOURCE", None)
            else:
                os.environ["LSPP_CONFIG_SOURCE"] = previous
    else:
        proof = dict(status="passed", native_executed=False, units=prepared["spec"]["units"], control_count=8,
                     scope="Offline fixture and explicit-field contract only")
        (prepared["directory"] / "offline.json").write_text(json.dumps(proof) + "\n", encoding="utf8")
    print(json.dumps(shared._plain(proof), ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
