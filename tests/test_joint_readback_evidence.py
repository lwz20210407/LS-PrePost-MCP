"""Only selected immutable native runs must match the current portable source blobs."""

import copy
import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path

import pytest

from tools.verify_p12_joint_roundtrip import CAPTURE_SOURCE_PATHS

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/decisions/evidence/p12-joint-readback/evidence.json"


@lru_cache(maxsize=None)
def _tree(revision):
    rows = subprocess.check_output(["git", "ls-tree", "-r", revision, "--", *CAPTURE_SOURCE_PATHS],
                                   cwd=ROOT, text=True, timeout=10)
    return {line.split("\t", 1)[1]: line.split("\t", 1)[0].split()[2] for line in rows.splitlines()}


def _blob(revision, path):
    return _tree(revision)[path]


def _configuration(run):
    kind = run.get("source_kind", "legacy_live_global_profile")
    if kind == "immutable_private_snapshot":
        guard = run.get("private_configuration_input_guards")
        assert isinstance(guard, dict) and guard["source_kind"] == kind
        assert guard["selected_version"] == run["profile"]["version"]
        inputs = guard["inputs"]
        assert set(inputs) == {"4.13", "4.10"}
        for version, item in inputs.items():
            assert item["source_kind"] == kind and item["version"] == version and item["readonly_origin"]
            assert item["full_before_after_bytes_identity_verified"]
            assert item["before"] == item["after"]
            assert set(item["before"]) == {"sha256", "bytes", "mtime_ns", "device", "inode"}
        selected = inputs[guard["selected_version"]]
        assert guard["selected_input_id"] == selected["input_id"]
        assert run["selected_configuration_sha256"] == selected["before"]["sha256"]
        assert guard["source_and_public_tree_unchanged"] and guard["executable_fingerprints_unchanged"]
        assert guard["no_native_processes_after_step"]
        for process in run["processes"]:
            source = process["configuration_input"]
            assert source["source_kind"] == kind and source["version"] == guard["selected_version"]
            assert source["input_id"] == selected["input_id"] and source["source_sha256"] == selected["before"]["sha256"]
            assert source["manifest_source_matches_selected_snapshot"] is True and source["source_modified"] is False
        observation = run["global_environment_observation"]
        assert observation["source_kind"] == "passive_environment_observation"
        assert observation["required_input"] is False and observation["isolation_proven"] is False
    else:
        assert kind == "legacy_live_global_profile"
        guard = run.get("global_configuration_guards")
        assert isinstance(guard, dict) and guard["before"]
        assert set(guard["before"]) == set(guard["after"])
        for version, before in guard["before"].items():
            after = guard["after"][version]
            assert after["bytes_equal_before"] and all(after[k] == before[k] for k in ("sha256", "size", "mtime_ns"))


def _active(data):
    checkpoint = data["source_checkpoints"][data["active_source_checkpoint"]]
    sources = checkpoint["capture_source_identity"]
    assert set(sources) == set(CAPTURE_SOURCE_PATHS)
    assert "src/ls_prepost_mcp/domain/model/matching.py" in sources
    assert "src/ls_prepost_mcp/domain/model/_identity.py" in sources
    for path, identity in sources.items():
        assert re.fullmatch(r"[0-9a-f]{64}", identity["captured_file_sha256"])
        assert _blob(checkpoint["actual_git_revision"], path) == identity["git_blob_id"]
        assert _blob("HEAD", path) == identity["git_blob_id"], path
    identifiers = data["active_run_ids"]
    assert len(identifiers) == len(set(identifiers)) == 6
    runs = {run["id"]: run for run in data["native_captures"]}
    selected = [runs[identifier] for identifier in identifiers]
    assert {(run["profile"]["version"], run["case"]) for run in selected} == {
        (version, case) for version in ("4.13", "4.10") for case in ("pilot", "nine_types", "body_modes")}
    for run in selected:
        assert run["actual_git_revision"] == checkpoint["actual_git_revision"]
        assert run["source_snapshot_sha256"] == checkpoint["source_snapshot_sha256"]
        assert run["capture_source_identity"] == sources
        assert run["status"] == "passed" and run["working_tree_dirty"] is False
        assert run["native_executed"] is True and run["semantic_differences"] == []
        assert all(run["identity_guards"].values())
        assert run["typed_joint_recognition"] == "unverified" and run["motion_verification"] == "not_run"
        assert len(run["processes"]) == 3
        assert all(p["returncode"] == 0 and p["timed_out"] is False and p["graphics"] is False
                   and p["nographics"] and type(p["pid"]) is int and p["pid"] > 0 for p in run["processes"])
        _configuration(run)
        strict, normalizations = run["strict_card_differences"], run["format_normalizations"]
        assert [item["field"] for item in strict] == [item["field"] for item in normalizations]
        assert len(strict) <= 2
        for item in normalizations:
            assert run["case"] == "nine_types" and item["field"] in ("Joint 908.r1", "Joint 909.r1")
            assert item["rule"] == "native_motor_type0_inapplicable_r1_zero_fill"
            assert item["expected"] is None and type(item["actual"]) in (int, float) and item["actual"] == 0
    return selected


def test_selected_joint_captures_bind_current_products_and_preserve_profile_facts():
    data = json.loads(EVIDENCE.read_text(encoding="utf8"))
    runs = _active(data)
    for run in runs:
        if run["profile"]["version"] == "4.10":
            assert run["profile"]["policy"] == "regression_subset"
            assert run["profile"]["file_version"] == run["profile"]["product_version"] == "4.10.0.1"
            assert run["profile"]["fixed_file_version"] == "4.9.0.1"
            assert run["profile"]["resource_conflict"] is True
    assert data["status"] == "partial" and not data["current_native_validation"]["task_acceptance_complete"]


def test_inactive_history_keeps_its_original_identity_without_matching_current_source():
    data = json.loads(EVIDENCE.read_text(encoding="utf8"))
    old = next(run for run in data["native_captures"] if run["id"] not in data["active_run_ids"])
    revision = old["actual_git_revision"]
    old["source_identity"] = {"intentionally_not_current": True}  # inactive objects do not drive the gate
    _active(data)
    assert old["actual_git_revision"] == revision


def test_changed_active_matching_blob_is_rejected_even_if_every_run_repeats_it():
    data = json.loads(EVIDENCE.read_text(encoding="utf8"))
    path = "src/ls_prepost_mcp/domain/model/matching.py"
    data["source_checkpoints"][data["active_source_checkpoint"]]["capture_source_identity"][path]["git_blob_id"] = "0" * 40
    for run in data["native_captures"]:
        if run["id"] in data["active_run_ids"]:
            run["capture_source_identity"][path]["git_blob_id"] = "0" * 40
    with pytest.raises(AssertionError):
        _active(data)


def test_active_source_gate_uses_git_objects_not_platform_worktree_hashes(monkeypatch):
    data = copy.deepcopy(json.loads(EVIDENCE.read_text(encoding="utf8")))
    # Raw Windows capture hashes remain evidence; CI must not rehash LF checkout bytes as if they were that capture.
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("Portable source gate must use Git blobs"))
    _active(data)


def test_private_inputs_stable_with_changed_passive_globals_remain_valid():
    data = copy.deepcopy(json.loads(EVIDENCE.read_text(encoding="utf8")))
    for run in data["native_captures"]:
        if run["id"] in data["active_run_ids"]:
            assert run["source_kind"] == "immutable_private_snapshot"
            observation = run["global_environment_observation"]
            observation["after"] = copy.deepcopy(observation["before"])
            observation["after"]["4.10"]["sha256"] = "0" * 64
    _active(data)


def test_changed_private_input_is_refused_even_when_passive_globals_are_stable():
    data = copy.deepcopy(json.loads(EVIDENCE.read_text(encoding="utf8")))
    run = next(row for row in data["native_captures"] if row["id"] in data["active_run_ids"])
    observation = run["global_environment_observation"]
    observation["after"] = copy.deepcopy(observation["before"])
    run["private_configuration_input_guards"]["inputs"]["4.13"]["after"]["sha256"] = "0" * 64
    with pytest.raises(AssertionError):
        _active(data)


def test_legacy_live_context_still_rejects_changed_global_configuration_inputs():
    data = json.loads(EVIDENCE.read_text(encoding="utf8"))
    run = copy.deepcopy(next(row for row in data["native_captures"] if row.get("global_configuration_guards")))
    version = next(iter(run["global_configuration_guards"]["before"]))
    run["global_configuration_guards"]["after"][version]["sha256"] = "0" * 64
    with pytest.raises(AssertionError):
        _configuration(run)
