"""Active P05/P12 evidence binds captured Git objects; old runs remain historical."""
import hashlib
import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path

import pytest

from tests import test_joint_readback_evidence as joint_gate
from tools import verify_p05_boundary_roundtrip as verifier
from tools.contact_geometry_evidence import read_evidence

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "docs/decisions/evidence/p05-boundary-readback"
EVIDENCE = FOLDER / "evidence.json"
P12 = ROOT / "docs/decisions/evidence/p12-joint-readback/evidence.json"


@lru_cache(maxsize=None)
def _tree(revision):
    text = subprocess.check_output(["git", "ls-tree", "-r", revision, "--", *verifier.CAPTURE_SOURCE_PATHS],
                                   cwd=ROOT, text=True, timeout=10)
    return {line.split("\t", 1)[1]: line.split("\t", 1)[0].split()[2] for line in text.splitlines()}


def _blob(revision, path):
    return _tree(revision)[path]


def _source_identity(checkpoint, *, current=True):
    sources = checkpoint["capture_source_identity"]
    declared = set(joint_gate._declared_capture_paths(checkpoint["actual_git_revision"], "tools/verify_p05_boundary_roundtrip.py"))
    assert set(sources) == declared
    if current:
        assert declared == set(verifier.CAPTURE_SOURCE_PATHS) and len(declared) == 43
        assert "post_capture_dependency_identity" not in checkpoint
    else:
        assert len(declared) == 41
    for path, item in sources.items():
        assert re.fullmatch(r"[0-9a-f]{64}", item["captured_file_sha256"])
        assert _blob(checkpoint["actual_git_revision"], path) == item["git_blob_id"]
        if current:
            assert _blob("HEAD", path) == item["git_blob_id"], path
    return sources


def _active(data, *, current=True):
    assert data["status"] == "partial" and data["verification_level"] == "L2"
    checkpoint = data["source_checkpoints"][data["active_source_checkpoint"]]
    assert checkpoint["id"] == data["active_source_checkpoint"] and checkpoint["working_tree_dirty"] is False
    sources = _source_identity(checkpoint, current=current)
    selected = [row for row in data["native_captures"] if row["id"] in data["active_run_ids"]]
    assert len(selected) == len(set(data["active_run_ids"])) == 2
    assert {row["profile"]["version"] for row in selected} == {"4.13", "4.10"}
    for row in selected:
        assert row["actual_git_revision"] == checkpoint["actual_git_revision"]
        assert row["capture_source_identity"] == sources and row["source_snapshot_sha256"] == checkpoint["source_snapshot_sha256"]
        assert row["working_tree_dirty"] is False and row["status"] == "passed" and row["native_executed"] is True
        assert row["boundary_count"] == 9 and row["semantic_differences"] == []
        assert row["typed_boundary_recognition"] == "unverified" and row["physical_response"] == "not_run"
        assert row["general_ITS_semantics"] == "unverified"
        assert all(value is True for value in row["identity_guards"].values())
        assert row["saved_and_staged_bytes_equal"] and row["single_file_saved_tree_reopen"]
        assert row["saved_sha256"] == row["staged_input_sha256"]
        assert row["native_export_bytes_equal_to_saved_claimed"] is False
        assert len(row["processes"]) == len({p["job_id"] for p in row["processes"]}) == 3
        for process in row["processes"]:
            assert type(process["pid"]) is int and process["pid"] > 0
            assert process["returncode"] == 0 and process["timed_out"] is False and process["graphics"] is False
            assert process["nographics"] and process["process_isolation"] == "windows_job"
        joint_gate._configuration(row)
        replay = verifier.native_projection_comparison(row["native_definition_projection"], verifier.fixture(),
                                                       row["native_metadata"], row["executable_sha256"])
        assert replay["differences"] == []
        for key in ("strict_card_differences", "documented_default_writes", "observed_representation",
                    "source_definition_projection", "native_expected_projection"):
            assert row[key] == replay[key]
        assert len(row["strict_card_differences"]) == 59
        assert len(row["documented_default_writes"]) == 37 and len(row["observed_representation"]) == 6
        if row["profile"]["version"] == "4.10":
            assert row["profile"]["resource_conflict"] is True and row["profile"]["policy"] == "regression_subset"
            assert row["profile"]["fixed_file_version"] == "4.9.0.1"
    return selected


def test_actual_active_boundary_evidence_matches_all_current_portable_source_blobs():
    _active(read_evidence("P05"))


@pytest.mark.parametrize("path", verifier.CAPTURE_SOURCE_PATHS)
def test_boundary_current43_source_drift_is_rejected(current43_checkpoint, monkeypatch, path):
    checkpoint, blobs = current43_checkpoint
    monkeypatch.setattr(__import__(__name__, fromlist=["_blob"]), "_blob",
                        lambda revision, item: "0" * 40 if revision == "HEAD" and item == path else blobs[item])
    with pytest.raises(AssertionError):
        _source_identity(checkpoint)


@pytest.mark.parametrize("fault", ["private_bytes", "process_source", "passive_as_input", "semantic", "observed_ITS", "wall_id"])
def test_boundary_evidence_cannot_hide_input_or_definition_changes(fault):
    data = json.loads(EVIDENCE.read_text(encoding="utf8"))
    row = data["native_captures"][0]
    if fault == "private_bytes":
        row["private_configuration_input_guards"]["inputs"]["4.13"]["after"]["sha256"] = "0" * 64
    elif fault == "process_source":
        row["processes"][0]["configuration_input"]["source_sha256"] = "0" * 64
    elif fault == "passive_as_input":
        row["global_environment_observation"]["required_input"] = True
    elif fault == "semantic":
        row["semantic_differences"] = [dict(field="unexpected", actual=1)]
    elif fault == "observed_ITS":
        row["native_metadata"]["set_its"]["definition.node_sets.101.header.its"]["raw_token"] = "+1"
    else:
        row["native_definition_projection"]["boundaries"]["*RIGIDWALL_PLANAR_ID"]["id"] = 2
    with pytest.raises(AssertionError):
        _active(data, current=False)


def test_failed_first_native_attempt_and_analysis_are_not_promoted_to_success():
    data = json.loads(EVIDENCE.read_text(encoding="utf8"))
    failed = data["failed_history"][0]
    assert failed["status"] == "failed" and failed["strict_differences"] is None
    assert failed["actual_git_revision"] == "8e247c16c05e099b49d31fc6300789f7a4cf7807"
    assert len(failed["processes"]) == 3 and failed["error"]["type"] == "ValueError"
    assert data["analysis_only"][0]["native_execution"] is False
    assert failed["id"] not in data["active_run_ids"]


def test_report_hash_and_compact_public_metadata_have_no_private_paths():
    raw = EVIDENCE.read_text(encoding="utf8")
    data = json.loads(raw)
    report = (FOLDER / data["report"]).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(report).hexdigest() == data["report_sha256_lf"]
    assert len(raw.encode()) < 512 * 1024 and re.search(r"[A-Za-z]:[\\/]|\\\\[^\\]+\\", raw) is None
    assert data["internal_readonly_audit"]["independent_external_review"] is False


def test_historical_joint_selection_keeps_its_actual_explicit41_without_backfill():
    data = json.loads(P12.read_text(encoding="utf8"))
    checkpoint = data["source_checkpoints"][data["active_source_checkpoint"]]
    assert checkpoint["actual_git_revision"] == "3da18f1f924ac499aa66dc49675d25280a855f54"
    assert len(checkpoint["capture_source_identity"]) == 41 and "post_capture_dependency_identity" not in checkpoint
    assert "src/ls_prepost_mcp/domain/model/loads.py" in checkpoint["capture_source_identity"]
    assert len(joint_gate._active(data, current=False)) == 6


@pytest.mark.parametrize("path", ["src/ls_prepost_mcp/domain/model/loads.py", "tools/verify_p12_joint_roundtrip.py",
                                  "tests/data/p12-roundtrip-fixtures.json", "src/ls_prepost_mcp/domain/model/matching.py"])
def test_historical_joint41_rejects_changed_recorded_source(monkeypatch, path):
    original = joint_gate._blob
    monkeypatch.setattr(joint_gate, "_blob", lambda revision, item: "0" * 40
                        if revision == "3da18f1f924ac499aa66dc49675d25280a855f54" and item == path else original(revision, item))
    with pytest.raises(AssertionError):
        joint_gate._active(json.loads(P12.read_text(encoding="utf8")), current=False)


def test_joint_old_capture_objects_and_checkpoints_remain_identical_to_pre_curation_git():
    old = json.loads(subprocess.check_output(["git", "show", "3da18f1:" + str(P12.relative_to(ROOT)).replace("\\", "/")],
                                            cwd=ROOT, text=True, encoding="utf8", timeout=10))
    current = json.loads(P12.read_text(encoding="utf8"))
    runs = {row["id"]: row for row in current["native_captures"]}
    for row in old["native_captures"]:
        assert runs[row["id"]] == row
    for key, value in old["source_checkpoints"].items():
        assert current["source_checkpoints"][key] == value
    assert len(current["native_captures"]) == len(old["native_captures"]) + 6


@pytest.fixture
def current43_checkpoint(monkeypatch):
    """Source-policy unit fixture only; never published as an actual capture."""
    data = read_evidence("P05", historical=True)
    checkpoint = data["source_checkpoints"][data["active_source_checkpoint"]]
    checkpoint["actual_git_revision"] = "f" * 40
    for name in ("contact_report", "contact"):
        checkpoint["capture_source_identity"][f"src/ls_prepost_mcp/domain/model/{name}.py"] = {
            "git_blob_id": "b" * 40, "captured_file_sha256": "c" * 64}
    blobs = {path: item["git_blob_id"] for path, item in checkpoint["capture_source_identity"].items()}
    monkeypatch.setattr(__import__(__name__, fromlist=["_blob"]), "_blob", lambda revision, path: blobs[path])
    monkeypatch.setattr(joint_gate, "_declared_capture_paths", lambda *args: verifier.CAPTURE_SOURCE_PATHS)
    return checkpoint, blobs


@pytest.mark.parametrize("name", ["contact_report", "contact"])
def test_boundary_current43_cannot_omit_either_contact_helper(current43_checkpoint, name):
    checkpoint, _ = current43_checkpoint
    assert len(_source_identity(checkpoint)) == 43
    path = f"src/ls_prepost_mcp/domain/model/{name}.py"
    checkpoint["post_capture_dependency_identity"] = {path: checkpoint["capture_source_identity"].pop(path)}
    with pytest.raises(AssertionError):
        _source_identity(checkpoint)


def test_historical_boundary41_validates_but_cannot_substitute_for_current43():
    data = read_evidence("P05", historical=True)
    assert len(_active(data, current=False)) == 2
    checkpoint = data["source_checkpoints"][data["active_source_checkpoint"]]
    with pytest.raises(AssertionError):
        _source_identity(checkpoint)
