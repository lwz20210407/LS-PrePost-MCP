"""I01: a process result cannot substitute for domain verification."""

import json

import pytest

from ls_prepost_mcp.core.contracts import CheckResult, JobResult
from ls_prepost_mcp.runner import record_batch_result


def outcome(directory, **changes):
    return JobResult(**dict(operation="inspect", job_id=directory.name,
                           status="unverified", **changes))


def test_boundary_preserves_warnings_checks_and_unverified_status(tmp_path):
    result = outcome(tmp_path, warnings=["Precision is limited"],
                     checks=[CheckResult(name="transport", status="passed")])
    manifest = dict(action="inspect", job_id=tmp_path.name, status="running", warnings=["Caller warning"])
    record_batch_result(result, manifest, tmp_path)
    assert manifest["status"] == "running"
    assert manifest["warnings"] == ["Caller warning", "Precision is limited"]
    assert manifest["engine_result"]["checks"][0]["status"] == "passed"
    assert manifest["process"]["engine_status"] == "unverified"
    assert json.loads((tmp_path / "engine-result.json").read_text()) == result.model_dump(mode="json")


@pytest.mark.parametrize("status,extra,message", [
    ("failed", dict(error={"message": "Native parser rejected input", "code": 42}), "parser rejected"),
    ("partial", dict(warnings=["Timed out after output"], data={"output": "partial"}), "Timed out"),
    ("unverified", dict(error={"message": "Receipt uncertain"}), "Receipt uncertain"),
    ("unverified", dict(checks=[CheckResult(name="output", status="missing")]), "checks: missing"),
    ("succeeded", dict(checks=[CheckResult(name="identity", status="failed")]), "checks: failed"),
    ("unverified", dict(stage="preparation"), "not execution evidence"),
])
def test_boundary_rejects_incomplete_execution_and_preserves_evidence(tmp_path, status, extra, message):
    result = JobResult(operation="inspect", job_id=tmp_path.name, status=status, **extra)
    manifest = dict(action="inspect", job_id=tmp_path.name)
    with pytest.raises(RuntimeError, match=message):
        record_batch_result(result, manifest, tmp_path)
    saved = JobResult.model_validate_json((tmp_path / "engine-result.json").read_bytes())
    assert saved == result
    assert "status" not in manifest


@pytest.mark.parametrize("changes", [dict(job_id="another-job"), dict(operation="another-operation")])
def test_boundary_rejects_uncorrelated_result_before_publishing(tmp_path, changes):
    result = JobResult(**(dict(operation="inspect", job_id=tmp_path.name, status="unverified") | changes))
    with pytest.raises(ValueError, match="different job or operation"):
        record_batch_result(result, dict(action="inspect", job_id=tmp_path.name), tmp_path)
    assert not (tmp_path / "engine-result.json").exists()


def test_legacy_dictionary_cannot_bypass_typed_boundary(tmp_path):
    with pytest.raises(TypeError, match="must return JobResult"):
        record_batch_result(dict(returncode=0), dict(action="inspect", job_id=tmp_path.name), tmp_path)
