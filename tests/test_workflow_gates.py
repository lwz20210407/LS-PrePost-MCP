import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.outcomes import normalize_outcome
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.workflow_checks import evaluate_checks, evaluate_gate, validate_checks


def recipe(service, first, after=True, defaults=None):
    steps = [dict(id="check", **first)]
    if after:
        steps.append(dict(id="export", action="process_curve", arguments={}))
    return service.create_workflow("Quality gate acceptance", steps, defaults)["artifacts"][0]["path"]


@pytest.mark.parametrize(
    "value,verdict",
    [(True, "passed"), (False, "failed"), (None, "not_applicable"), (1, "invalid"), ("true", "invalid")],
)
def test_execution_success_does_not_imply_check_pass(value, verdict):
    result = dict(status="succeeded", verification=dict(passed_checks=value, solver_validated=False))
    outcome = normalize_outcome("check_gui_shell_quality", result)
    assert outcome.execution_accepted and outcome.check_status == verdict
    assert evaluate_gate(outcome, result, [])["passed"] is (value is True)


def test_missing_verdict_and_unverified_execution_are_never_implicitly_true():
    result = dict(status="succeeded")
    outcome = normalize_outcome("check_gui_keywords", result)
    assert outcome.check_status == "missing" and not evaluate_gate(outcome, result, [])["passed"]
    for status in (None, True, "running", "timeout", "completed_unverified", "prepared", "nonsense"):
        result = dict(status=status)
        assert not evaluate_gate(normalize_outcome("inspect_model", result), result, [], "report_only")[
            "passed"
        ]
    assert normalize_outcome("prepare_native_program", dict(status="prepared")).execution_accepted
    assert not normalize_outcome("prepare_native_program", dict(status="succeeded")).execution_accepted


def test_predicates_do_not_coerce_booleans_nulls_missing_data_or_nonfinite_numbers():
    for actual in (True, None, "0", float("nan"), float("inf"), []):
        report = evaluate_checks({"value": actual}, [dict(path=["value"], operator="le", value=0)])[0]
        assert not report["passed"]
        json.dumps(report, allow_nan=False)
    assert not evaluate_checks({"value": 1}, [dict(path=["value"], operator="eq", value=True)])[0]["passed"]
    assert evaluate_checks({"value": 1.0}, [dict(path=["value"], operator="eq", value=1)])[0]["passed"]
    assert not evaluate_checks({}, [dict(path=["missing"], operator="is_null")])[0]["passed"]
    assert evaluate_checks({"value": None}, [dict(path=["value"], operator="is_null")])[0]["passed"]


@pytest.mark.parametrize(
    "check",
    [
        dict(path=[], operator="is_true"),
        dict(path=["x", True], operator="is_true"),
        dict(path=["x", -1], operator="is_true"),
        dict(path=["x"], operator="le", value=True),
        dict(path=["x"], operator="eq", value=float("nan")),
        dict(path=["x"], operator="is_true", value=True),
        dict(path=["x"], operator="python", value="exit()"),
        dict(path=["x"], operator="eq", value={"$result": "other", "path": []}),
    ],
)
def test_invalid_predicates_are_rejected_before_dispatch(check):
    with pytest.raises(ValueError):
        validate_checks([check])


def test_failed_native_verdict_preserves_report_checkpoint_and_skips_following_action(tmp_path, monkeypatch):
    s = Service(Settings(tmp_path))
    called = []
    checkpoint = tmp_path / "baseline.k"
    checkpoint.write_text("*KEYWORD\n*END\n")
    native_report = tmp_path / "native-check.txt"
    native_report.write_text("Synthetic report: two failed shells")
    original = dict(
        status="succeeded",
        baseline_checkpoint=str(checkpoint),
        verification=dict(passed_checks=False, backend="lsprepost-native-model-checking"),
        artifacts=[dict(path=str(native_report))],
    )
    monkeypatch.setattr(s, "check_gui_shell_quality", lambda **kw: original)
    monkeypatch.setattr(s, "process_curve", lambda **kw: called.append("export"))
    path = recipe(s, dict(action="check_gui_shell_quality", arguments={}))
    result = s.run_workflow(path, session_id="synthetic-session")
    assert result["status"] == "failed" and not called
    data = result["data"]
    assert data["completed_steps"] == 0 and data["attempted_steps"] == 1
    assert data["failed_step"] == "check" and data["failure_phase"] == "quality_gate"
    assert data["skipped_steps"] == ["export"]
    assert data["steps"]["check"] == original and original["status"] == "succeeded"
    assert data["baseline_checkpoints"]["check"] == str(checkpoint)
    assert not data["automatic_replay"] and not data["automatic_rollback"]
    assert native_report.exists() and checkpoint.exists()
    assert {Path(a["path"]).name for a in result["artifacts"]} == {
        "steps.json",
        "outcomes.json",
        "gates.json",
    }
    assert s.read_job(result["job_id"])["data"]["gates"]["check"]["passed"] is False


def test_report_only_is_explicit_and_still_enforces_user_thresholds(tmp_path, monkeypatch):
    s = Service(Settings(tmp_path))
    called = []
    monkeypatch.setattr(
        s,
        "check_gui_keywords",
        lambda **kw: dict(
            status="succeeded", verification=dict(passed_checks=False, totals=dict(warning=2, error=0))
        ),
    )
    monkeypatch.setattr(s, "process_curve", lambda **kw: called.append("export") or dict(status="succeeded"))
    definition = dict(
        action="check_gui_keywords",
        arguments={},
        quality_policy="report_only",
        checks=[
            dict(path=["verification", "totals", "warning"], operator="le", value={"$param": "warnings"}),
            dict(path=["verification", "totals", "error"], operator="eq", value=0),
        ],
    )
    path = recipe(s, definition, defaults=dict(warnings=2))
    assert s.run_workflow(path, session_id="synthetic-session")["status"] == "succeeded"
    assert called == ["export"]
    called.clear()
    result = s.run_workflow(path, dict(warnings=0), session_id="synthetic-session")
    assert result["status"] == "failed" and not called
    assert result["data"]["gates"]["check"]["report_only"]
    assert "explicit_check_failed" in result["data"]["gates"]["check"]["reasons"]


def test_all_threshold_parameters_validate_before_any_action(tmp_path, monkeypatch):
    s = Service(Settings(tmp_path))
    called = []
    monkeypatch.setattr(s, "process_curve", lambda **kw: called.append(1))
    made = s.create_workflow(
        "Preflight",
        [
            dict(id="first", action="process_curve", arguments={}),
            dict(
                id="second",
                action="process_curve",
                arguments={},
                checks=[dict(path=["data", "peak"], operator="le", value={"$param": "limit"})],
            ),
        ],
    )
    for parameters in ({}, {"limit": None}, {"limit": True}, {"limit": "zero"}, {"limit": float("inf")}):
        with pytest.raises(ValueError):
            s.run_workflow(made["artifacts"][0]["path"], parameters)
    assert not called


@pytest.mark.parametrize(
    "bad_result", [None, [], {"data": {}}, {"status": "succeeded", "data": {"x": float("nan")}}]
)
def test_bad_operation_results_stop_and_leave_readable_failure_evidence(tmp_path, monkeypatch, bad_result):
    s = Service(Settings(tmp_path))
    called = []
    monkeypatch.setattr(s, "inspect_model", lambda **kw: bad_result)
    monkeypatch.setattr(s, "process_curve", lambda **kw: called.append(1))
    result = s.run_workflow(recipe(s, dict(action="inspect_model", arguments={})))
    assert result["status"] == "failed" and not called
    assert result["data"]["failure_phase"] == "execution"
    assert Path(result["job_directory"], "job.json").is_file()


def test_preparation_is_an_accepted_distinct_stage_and_unknown_verdict_can_be_required(tmp_path, monkeypatch):
    s = Service(Settings(tmp_path))
    monkeypatch.setattr(
        s, "prepare_native_program", lambda **kw: dict(status="prepared", data={"sha256": "example"})
    )
    path = recipe(s, dict(action="prepare_native_program", arguments={}), False)
    result = s.run_workflow(path)
    assert result["status"] == "succeeded"
    assert result["data"]["outcomes"]["check"]["stage"] == "preparation"
    assert result["data"]["outcomes"]["check"]["check_status"] == "not_reported"
    path = recipe(
        s, dict(action="prepare_native_program", arguments={}, quality_policy="require_pass"), False
    )
    assert s.run_workflow(path)["status"] == "failed"


def test_threshold_parameterization_retains_policy_and_provenance(tmp_path):
    s = Service(Settings(tmp_path))
    path = recipe(
        s,
        dict(
            action="inspect_model",
            arguments={},
            quality_policy="report_only",
            checks=[dict(path=["data", "count"], operator="ge", value=2)],
        ),
        False,
    )
    template = s.parameterize_workflow(
        path, [dict(step_id="check", section="checks", path=[0, "value"], parameter="minimum")]
    )
    definition = json.loads(Path(template["artifacts"][0]["path"]).read_text())
    assert definition["defaults"] == {"minimum": 2}
    assert definition["steps"][0]["quality_policy"] == "report_only"
    assert definition["steps"][0]["checks"][0]["value"] == {"$param": "minimum"}


def test_real_deck_quality_gate_blocks_export_without_native_software(tmp_path, monkeypatch):
    pytest.importorskip("ansys.dyna.core")
    source = tmp_path / "collapsed.k"
    source.write_text(
        "*KEYWORD\n*NODE\n1,0,0,0\n2,0,0,0\n3,1,1,0\n4,0,1,0\n*ELEMENT_SHELL\n1,1,1,2,3,4\n*END\n"
    )
    original = source.read_bytes()
    s = Service(Settings(tmp_path))
    called = []
    monkeypatch.setattr(s, "process_curve", lambda **kw: called.append("export"))
    result = s.run_workflow(
        recipe(s, dict(action="inspect_mesh_quality", arguments=dict(model=str(source), units="mm")))
    )
    assert result["status"] == "failed" and not called
    assert result["data"]["outcomes"]["check"]["backend"] == "pydyna+geometry-math"
    assert result["data"]["steps"]["check"]["data"]["valid_within_scope"] is False
    assert source.read_bytes() == original
