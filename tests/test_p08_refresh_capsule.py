"""Small synthetic source/stage receipts; never execution or replacement real evidence."""
import copy
import hashlib
import json

import pytest

from tools import contact_geometry_evidence as context
from tools import p08_refresh_capsule as gate


@pytest.fixture
def record(tmp_path, monkeypatch):
    def make(task="P05"):
        paths = gate.HOST_SOURCES if task in gate.HOST_TASKS else gate.PROGRAM_SOURCES if task == "P04" else gate.EMBEDDED_SOURCES
        contents = {path: b"# owned synthetic source\n" for path in paths}
        if task == "P04":
            contents["tools/verify_node_set_user_ids.py"] = b"PROGRAM = 'owned program\\n'\n"
        files = {path: hashlib.sha256(raw).hexdigest() for path, raw in contents.items()}
        snapshot = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        root = tmp_path / task
        for path, raw in contents.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        monkeypatch.setattr(gate, "_tracked", lambda *args: {path: "b" * 40 for path in paths})
        monkeypatch.setattr(gate, "_git", lambda root, command, locator: contents[locator.split(":", 1)[1]])
        sources = [dict(path=path, raw_sha256=files[path], git_blob_id="b" * 40,
                        sha256_lf=files[path]) for path in sorted(paths)]
        jobs = []
        for profile, roles in gate.NATIVE_ROLES.get(task, {}).items():
            for role, count in roles.items():
                for _ in range(count):
                    uid = f"{len(jobs)+1:032x}"
                    if task == "P04":
                        staged = {name: dict(phase="post_native_capture", sha256="c" * 64) for name in gate.PROGRAM_FILES}
                        staged["program.py"]["sha256_lf"] = hashlib.sha256(b"owned program\n").hexdigest()
                    else:
                        staged = {name: dict(source=origin, phase="post_native_capture", sha256=files[origin])
                                  for name, origin in gate.BRIDGE_SOURCES.items()}
                    job = dict(job_id=uid, profile=profile, role=role, manifest_action=role, engine_operation=role,
                               engine_job_id=uid, native_channel="python" if task == "P04" else "embedded_python",
                               actual_git_revision="a" * 40, source_snapshot_sha256=snapshot,
                               outer_executable_sha256="d" * 64, configuration_sha256="e" * 64,
                               argv_matches_profile=True, manifest_executable_matches_profile=True,
                               configuration_matches_profile=True, staged_files=staged)
                    if task == "P04":
                        job.update(program_source_sha256_lf=staged["program.py"]["sha256_lf"], contract_program_sha256="c" * 64)
                    jobs.append(job)
        capsule = dict(schema_version=1, task=task, actual_git_revision="a" * 40, working_tree_dirty=False,
                       source_snapshot_sha256=snapshot, source_files=files, source_after_files=copy.deepcopy(files),
                       source_after_snapshot_sha256=snapshot, runtime_sources=sources, native_jobs=jobs,
                       profiles={profile: dict(outer_executable_sha256="d" * 64, configuration_sha256="e" * 64,
                                              configuration_source_kind="immutable_private_snapshot")
                                 for profile in gate.NATIVE_ROLES.get(task, {})})
        data = dict(actual_git_revision="a" * 40, source_snapshot_sha256=snapshot, working_tree_dirty=False,
                    native_executed=task not in gate.HOST_TASKS, p08_refresh_capsule=capsule)
        return root, data
    return make


@pytest.mark.parametrize("task", ["P03", "P06_identity", "P06_geometry", "P04", "P05", "P12", "P10"])
def test_each_role_admits_only_its_recorded_synthetic_contract(record, task):
    root, data = record(task)
    gate.validate_capsule(data, task, root)
    if task == "P04":
        assert set(data["p08_refresh_capsule"]["native_jobs"][0]["staged_files"]) == gate.PROGRAM_FILES


@pytest.mark.parametrize("fault", ["missing", "source_missing", "raw", "git", "lf", "current", "snapshot", "revision",
    "role", "channel", "uuid", "count", "measure", "stage_missing", "stage_hash", "stage_after", "escape",
    "source_after", "exe", "config", "phase", "duplicate_job"])
def test_new_current_rejects_missing_stale_or_wrong_runtime_records(record, fault):
    root, data = record()
    capsule = data["p08_refresh_capsule"]
    job = capsule["native_jobs"][0]
    source = capsule["runtime_sources"][0]
    if fault == "missing":
        del data["p08_refresh_capsule"]
    elif fault == "source_missing":
        capsule["runtime_sources"].pop()
    elif fault in {"raw", "git", "lf"}:
        source[{"raw": "raw_sha256", "git": "git_blob_id", "lf": "sha256_lf"}[fault]] = "0" * (40 if fault == "git" else 64)
    elif fault == "current":
        (root / source["path"]).write_bytes(b"changed current code\n")
    elif fault == "snapshot":
        capsule["source_snapshot_sha256"] = "0" * 64
    elif fault == "revision":
        capsule["actual_git_revision"] = "0" * 40
    elif fault in {"role", "channel", "uuid"}:
        job[{"role": "manifest_action", "channel": "native_channel", "uuid": "engine_job_id"}[fault]] = "wrong"
    elif fault == "count":
        capsule["native_jobs"].pop()
    elif fault == "measure":
        job["measured_before_native"] = True
    elif fault == "stage_missing":
        job["staged_files"].pop("bridge.py")
    elif fault == "stage_hash":
        job["staged_files"]["bridge.py"]["sha256"] = "0" * 64
    elif fault == "stage_after":
        job["staged_files"]["bridge.py"]["post_capture_reread_sha256"] = "0" * 64
    elif fault == "source_after":
        capsule["source_after_files"][source["path"]] = "0" * 64
    elif fault == "exe":
        job["outer_executable_sha256"] = "0" * 64
    elif fault == "config":
        job["configuration_sha256"] = "0" * 64
    elif fault == "phase":
        job["staged_files"]["bridge.py"]["phase"] = "pre_execution"
    elif fault == "duplicate_job":
        capsule["native_jobs"][1]["job_id"] = job["job_id"]
    else:
        source["path"] = "../outside.py"
    with pytest.raises(ValueError, match="capsule"):
        gate.validate_capsule(data, "P05", root)


@pytest.mark.parametrize("fault", ["program", "contract", "bridge"])
def test_program_route_is_bound_to_captured_program_and_never_uses_bridge_fallback(record, fault):
    root, data = record("P04")
    job = data["p08_refresh_capsule"]["native_jobs"][0]
    if fault == "program":
        job["program_source_sha256_lf"] = "0" * 64
    elif fault == "contract":
        job["contract_program_sha256"] = "0" * 64
    else:
        job["staged_files"] = {"bridge.py": dict(phase="post_native_capture", sha256="c" * 64)}
    with pytest.raises(ValueError, match="capsule"):
        gate.validate_capsule(data, "P04", root)


def test_selector_can_leave_old_topic_but_not_evidence_root_or_fall_back_to_old_record(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    evidence_root = root / "docs/decisions/evidence"
    index = evidence_root / "contact-geometry-refresh/context.json"
    index.parent.mkdir(parents=True)
    target = evidence_root / "p08-source-refresh/p10/evidence.json"
    target.parent.mkdir(parents=True)
    old = evidence_root / "p10-control-output/evidence.json"
    old.parent.mkdir()
    old.write_text("{}", encoding="utf8")
    selection = dict(current={"P10": dict(path=target.relative_to(root).as_posix())})
    index.write_text(json.dumps(selection), encoding="utf8")
    monkeypatch.setattr(context, "ROOT", root)
    monkeypatch.setattr(context, "INDEX", index)
    assert context.evidence_path("P10") == target
    with pytest.raises(FileNotFoundError):
        context.read_evidence("P10")
    target.write_text("{}", encoding="utf8")  # Copying an old capture cannot admit a new current.
    with pytest.raises(ValueError, match="missing new capture-time capsule"):
        context.read_evidence("P10")
    selection["current"]["P10"]["path"] = "../outside.json"
    index.write_text(json.dumps(selection), encoding="utf8")
    with pytest.raises(AssertionError):
        context.evidence_path("P10")


def test_runtime_contracts_reference_real_project_sources():
    paths = gate.HOST_SOURCES | gate.EMBEDDED_SOURCES | gate.PROGRAM_SOURCES
    assert all((context.ROOT / path).is_file() for path in paths)
