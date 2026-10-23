"""Review02 P1-2: required verification cannot accompany a successful job."""
import hashlib
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import CheckResult, JobResult
from ls_prepost_mcp.service import Service


@pytest.mark.parametrize("verdict,expected", [("failed", "failed"), ("invalid", "failed"), ("missing", "unverified")])
def test_required_check_cannot_leave_job_successful(verdict, expected):
    result = JobResult(operation="save", status="succeeded", data={"written": True},
                       checks=[CheckResult(name="saved_deck_reloads", status=verdict)])
    assert result.status == expected
    assert not result.execution_accepted
    assert result.error and "saved_deck_reloads" in result.error["message"]


def test_edit_keywords_failed_reload_cannot_publish_verified_artifacts(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.model import operations

    main = tmp_path / "main.k"
    main.write_bytes(b"*KEYWORD\n*NODE\n1,0,0,0\n*END\n")
    before = main.read_bytes()
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))

    def disconnected(source, edits, output_dir, **kwargs):
        directory = Path(output_dir)
        directory.mkdir(parents=True)
        output = directory / "main.k"
        output.write_bytes(b"*KEYWORD\n*INCLUDE\nmissing.k\n*END\n")
        return {"status": "succeeded", "written": True, "new_dangling": [], "save": {
            "files": [{"source": str(main), "dest": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                       "modified": True}], "main": str(output), "reload_warnings": ["Missing include 'missing.k'"]}}

    monkeypatch.setattr(operations, "edit_deck", disconnected)
    result = service.edit_keywords(str(main), [{"op": "insert", "text": "$ edit\n"}])
    assert result["status"] == "failed"
    assert result["error"] and "saved_deck_reloads" in result["error"]["message"]
    assert not any(a["verification"] == "verified" for a in result["artifacts"])
    manifest = json.loads((service.jobs.root / result["job_id"] / "job.json").read_text())
    assert manifest["status"] == "failed"
    assert main.read_bytes() == before


def test_diagnostic_quality_verdict_still_blocks_gate_without_claiming_execution_failure():
    from ls_prepost_mcp.outcomes import normalize_outcome
    from ls_prepost_mcp.workflow_checks import evaluate_gate

    result = normalize_outcome("check_gui_shell_quality", {
        "status": "succeeded", "verification": {"passed_checks": False}})
    assert result.check_status == "failed" and result.execution_accepted
    assert not evaluate_gate(result, [])["passed"]


def test_required_check_normalization_does_not_mutate_the_input_or_lose_cause():
    original = {"operation": "save", "status": "partial", "data": {"written": True},
                "checks": [{"name": "reload", "status": "failed"}],
                "error": {"message": "native parser failed", "code": 12}}
    before = json.dumps(original, sort_keys=True)
    result = JobResult.model_validate(original)
    assert result.status == "failed"
    assert result.error["cause"] == original["error"]
    assert json.dumps(original, sort_keys=True) == before


def test_diagnostic_check_flag_is_strict_and_cannot_hide_gate_failure():
    from pydantic import ValidationError

    from ls_prepost_mcp.workflow_checks import evaluate_gate

    with pytest.raises(ValidationError):
        CheckResult(name="quality", status="failed", required="false")
    report = JobResult(operation="check", status="succeeded",
                       checks=[CheckResult(name="quality", status="failed", required=False)])
    assert report.status == "succeeded" and report.check_status == "failed"
    assert not evaluate_gate(report, [])["passed"]
