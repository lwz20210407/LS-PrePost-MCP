"""Fake recorded jobs and source/profile admission only; no C++/GUI process."""
import copy
import hashlib
import json
import stat

import pytest

from tools import verify_p08_mesh_roundtrip as verifier


def profile(tmp_path):
    return dict(executable_path=str((tmp_path / "native.exe").resolve()), source=str((tmp_path / "readonly.conf").resolve()),
                executable=dict(size=120, mtime_ns=123, sha256="a" * 64), configuration=dict(sha256="b" * 64))


def manifest(tmp_path, action="gui_mesh_state"):
    selected = profile(tmp_path)
    uid = "1" * 32
    process = dict(pid=1234, returncode=0, timed_out=False, graphics=False, launch_mode="c", process_isolation="windows_job",
        argv=[selected["executable_path"], "c=commands.cfile", "-nographics"],
        configuration=dict(source=selected["source"], source_sha256="b" * 64, source_modified=False))
    return dict(job_id=uid, action=action, status="succeeded", native_channel="embedded_python", execution_mode="nographics",
        executable=dict(path=selected["executable_path"], **selected["executable"]),
        engine_result=dict(job_id=uid, operation=action, backend="lsprepost", stage="execution", status="unverified",
                           error=None, checks=[], data=process))


@pytest.mark.parametrize("action", ["gui_mesh_state", "export_keyword"])
def test_each_planned_job_binds_exact_role_and_executable(tmp_path, action):
    result = verifier.validate_job_binding(manifest(tmp_path, action), action, profile(tmp_path))
    assert result["expected_action"] == action and result["per_job_full_sha256"]
    assert result["os_process_creation_time"] == "not_continuously_observed"


@pytest.mark.parametrize("change", ["role", "argv_exe", "manifest_exe", "size", "mtime", "hash", "undocumented_null",
    "config_path", "config_hash", "config_modified", "job_object", "graphics", "visible_argv", "runc", "timeout",
    "missing_timeout", "rc", "pid_bool", "engine_uuid", "session", "native_channel"])
def test_wrong_role_exe_profile_or_execution_cannot_admit(tmp_path, change):
    job = manifest(tmp_path)
    process = job["engine_result"]["data"]
    if change == "role":
        job["action"] = job["engine_result"]["operation"] = "export_keyword"
    elif change == "argv_exe":
        process["argv"][0] = str(tmp_path / "another.exe")
    elif change == "manifest_exe":
        job["executable"]["path"] = str(tmp_path / "another.exe")
    elif change == "size":
        job["executable"]["size"] += 1
    elif change == "mtime":
        job["executable"]["mtime_ns"] += 1
    elif change == "hash":
        job["executable"]["sha256"] = "c" * 64
    elif change == "undocumented_null":
        job["executable"]["sha256"] = None
    elif change == "config_path":
        process["configuration"]["source"] = str(tmp_path / "global.conf")
    elif change == "config_hash":
        process["configuration"]["source_sha256"] = "c" * 64
    elif change == "config_modified":
        process["configuration"]["source_modified"] = True
    elif change == "job_object":
        process["process_isolation"] = "process_only"
    elif change == "graphics":
        process["graphics"] = True
    elif change == "visible_argv":
        process["argv"].append("w=1024x768")
    elif change == "runc":
        process["launch_mode"] = "runc"
    elif change == "timeout":
        process["timed_out"] = True
    elif change == "missing_timeout":
        del process["timed_out"]
    elif change == "rc":
        process["returncode"] = 1
    elif change == "pid_bool":
        process["pid"] = True
    elif change == "engine_uuid":
        job["engine_result"]["job_id"] = "2" * 32
    elif change == "session":
        job["session_id"] = "forbidden"
    else:
        job["native_channel"] = "session"
    with pytest.raises(ValueError):
        verifier.validate_job_binding(job, "gui_mesh_state", profile(tmp_path))


def test_large_exe_stat_only_is_distinct_from_outer_full_hash(tmp_path):
    job, selected = manifest(tmp_path), profile(tmp_path)
    job["executable"].update(size=100 * 1024 * 1024, sha256=None, hash_note="Files over 64 MiB use size/mtime identity in this release")
    selected["executable"]["size"] = job["executable"]["size"]
    actual = verifier.validate_job_binding(job, "gui_mesh_state", selected)
    assert actual["per_job_full_sha256"] is False and actual["outer_full_sha256"] == "a" * 64


def test_typed_and_export_roles_need_two_distinct_jobs(tmp_path):
    typed, exported = manifest(tmp_path), manifest(tmp_path, "export_keyword")
    with pytest.raises(ValueError, match="distinct owned job UUIDs"):
        verifier.validate_job_pair(typed, exported, profile(tmp_path))
    exported["job_id"] = exported["engine_result"]["job_id"] = "2" * 32
    result = verifier.validate_job_pair(typed, exported, profile(tmp_path))
    assert result["record_validation_only"] is True and len(result["bindings"]) == 2


def typed_observation(case):
    expected = case["expected"]
    return dict(nodes=copy.deepcopy(expected["nodes"]),
        elements=[dict(type=r["kind"], id=r["id"], nodes=list(r["nodes"])) for r in expected["elements"]],
        counts=dict(nodes=len(expected["nodes"]), elements=len(expected["elements"])),
        part_ids=[r["id"] for r in expected["parts"]],
        part_elements={str(p["id"]): [r["id"] for r in expected["elements"] if r["pid"] == p["id"]] for p in expected["parts"]})


@pytest.mark.parametrize("case_id", verifier.CASE_IDS)
def test_fake_typed_data_matches_hand_oracle_by_uid_not_array_position(case_id):
    case = verifier.case_spec(case_id)
    data = typed_observation(case)
    data["nodes"].reverse()
    data["elements"].reverse()
    assert verifier.compare_typed(data, case) == []


@pytest.mark.parametrize("change", ["unselected_coordinate", "selected_coordinate", "internal_ids", "unselected_connection",
    "membership", "internal_parts", "count", "duplicate", "uid_bool", "coordinate_bool", "part_bool"])
def test_corrupted_typed_observation_never_passes(change):
    case = verifier.case_spec("translate")
    data = typed_observation(case)
    if change == "unselected_coordinate":
        data["nodes"][0][1] += 1e-12
    elif change == "selected_coordinate":
        data["nodes"][-1][1] += .01
    elif change == "internal_ids":
        data["nodes"][-1][0] = 16
    elif change == "unselected_connection":
        data["elements"][0]["nodes"].reverse()
    elif change == "membership":
        data["part_elements"] = {"1": [11, 22], "2": []}
    elif change == "internal_parts":
        data["part_ids"] = [1, 2]
    elif change == "count":
        data["counts"]["nodes"] += 1
    elif change == "duplicate":
        data["nodes"].append(copy.deepcopy(data["nodes"][0]))
    elif change == "uid_bool":
        data["nodes"][0][0] = True
    elif change == "coordinate_bool":
        data["nodes"][-1][1] = True
    else:
        data["part_ids"][0] = True
    try:
        differences = verifier.compare_typed(data, case)
    except ValueError:
        return
    assert differences


def test_visibility_or_selection_observations_are_not_geometry_pass_criteria():
    case = verifier.case_spec("translate")
    data = typed_observation(case)
    data.update(part_visibility={"13": True, "29": True}, selection_ids=[11, 22], selection_types=None)
    assert verifier.compare_typed(data, case) == []
    data["nodes"][0][1] += .01
    assert verifier.compare_typed(data, case)


@pytest.mark.parametrize("identity", [None, {}, {"actual_git_head": "a" * 40, "working_tree_dirty": True}])
def test_unadmitted_source_fails_before_private_profiles_or_output(tmp_path, monkeypatch, identity):
    monkeypatch.setattr(verifier, "execution_identity", lambda *a: identity or {})
    with pytest.raises(ValueError, match="Source admission"):
        verifier.main(["--output", str(tmp_path / "never"), "--expected-head", "a" * 40,
                       "--expected-source-snapshot", "b" * 64])
    assert not (tmp_path / "never").exists()


def test_dual_private_profiles_require_full_expected_hashes_and_readonly(tmp_path, monkeypatch):
    inputs = {}
    for version in ("4.13", "4.10"):
        folder = tmp_path / version
        folder.mkdir()
        exe, cfg = folder / "fake.exe", folder / "lsppconf"
        exe.write_bytes(b"fake executable, never started")
        cfg.write_bytes(b"synthetic initialized preferences")
        cfg.chmod(stat.S_IREAD)
        inputs[version] = dict(executable=str(exe), source=str(cfg), executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
                               source_sha256=hashlib.sha256(cfg.read_bytes()).hexdigest())
    monkeypatch.setattr(verifier, "require_installation", lambda *a, **kw: dict(version_source="file_version_resource"))
    monkeypatch.setattr(verifier, "require_capability", lambda *a: None)
    result = verifier.profile_inputs_identity(inputs)
    assert set(result) == {"4.13", "4.10"} and all(r["configuration"]["readonly"] for r in result.values())
    inputs["4.10"]["source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="full SHA"):
        verifier.profile_inputs_identity(inputs)


def test_staged_bridge_and_native_helpers_must_match_admitted_bytes(tmp_path):
    sources = {}
    for name, origin in verifier.BRIDGE_SOURCES.items():
        path = tmp_path / name
        path.write_bytes(b"admitted staged source")
        sources[origin] = dict(captured_file_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    verifier.validate_staged_bridge(tmp_path, sources)
    (tmp_path / "bridge.py").write_bytes(b"changed bridge")
    with pytest.raises(ValueError, match="Staged bridge/helper"):
        verifier.validate_staged_bridge(tmp_path, sources)


def test_pinned_source_requires_complete_current_files_and_git_objects(tmp_path, monkeypatch):
    paths = ("src/code.py", "tools/producer.py")
    for relative in paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"registered source\n")
    captured = {p: hashlib.sha256((tmp_path / p).read_bytes()).hexdigest() for p in paths}
    identity = dict(actual_git_head="a" * 40, working_tree_dirty=False, source_files=captured,
        source_snapshot_sha256=hashlib.sha256(json.dumps(captured, sort_keys=True).encode()).hexdigest())
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    monkeypatch.setattr(verifier, "CAPTURE_SOURCE_PATHS", paths)
    monkeypatch.setattr(verifier, "execution_identity", lambda *a: copy.deepcopy(identity))
    rows = "".join("100644 blob " + "b" * 40 + "\t" + p + "\n" for p in paths)
    monkeypatch.setattr(verifier.subprocess, "check_output", lambda *a, **kw: rows)
    assert set(verifier.source_identity(identity, "a" * 40, identity["source_snapshot_sha256"])) == set(paths)
    with pytest.raises(ValueError, match="explicitly pinned"):
        verifier.source_identity(identity, "c" * 40)
    (tmp_path / paths[0]).write_bytes(b"source changed\n")
    with pytest.raises(ValueError, match="changed required source"):
        verifier.source_identity(identity)


def test_declared_products_producer_fixture_and_tests_are_real_unique_sources():
    assert len(verifier.CAPTURE_SOURCE_PATHS) == len(set(verifier.CAPTURE_SOURCE_PATHS))
    assert all((verifier.ROOT / p).is_file() for p in verifier.CAPTURE_SOURCE_PATHS)
    assert set(verifier.BRIDGE_SOURCES.values()) <= set(verifier.PRODUCT_PATHS)
