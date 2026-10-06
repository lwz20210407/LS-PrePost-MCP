"""I02 review regressions: preserve legacy failures at the contract boundary."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.outcomes import normalize_outcome
from ls_prepost_mcp.workflow_checks import evaluate_gate


@pytest.mark.parametrize("error", [None, {}, {"code": 1}, {"message": ""},
                                  {"message": " \t\n"}, {"message": 7}, {"message": False}])
def test_failed_contract_requires_nonempty_string_message(error):
    with pytest.raises(ValidationError, match="nonempty message"):
        JobResult(operation="inspect_model", status="failed", error=error)


@pytest.mark.parametrize("action,payload,message", [
    ("export_gui_field_animation", dict(restoration_error="Blank flags not restored", artifacts=[]),
     "Blank flags not restored"),
    ("export_gui_animation", dict(restoration_error="State not restored"), "State not restored"),
    ("restart_gui_session", dict(restoration=dict(status="failed", error=dict(message="Cannot reopen checkpoint"))),
     "Cannot reopen checkpoint"),
    ("inspect_model", dict(reason="Source changed"), "Source changed"),
    ("inspect_model", dict(error="Legacy string error"), "Legacy string error"),
    ("inspect_model", dict(error=dict(message="", code=7), reason="Diagnostic retained"), "Diagnostic retained"),
    ("inspect_model", {}, "Legacy operation reported failure without a diagnostic"),
])
def test_legacy_failures_keep_verdict_and_diagnostic_without_mutation(action, payload, message):
    raw = dict(status="failed", **payload)
    original = deepcopy(raw)
    result = normalize_outcome(action, raw)
    assert result.status == "failed"
    assert result.error["message"] == message
    assert result.comparison_data == raw == original
    assert not result.execution_accepted
    assert not evaluate_gate(result, [])["passed"]
    if isinstance(payload.get("error"), dict) and "code" in payload["error"]:
        assert result.error["code"] == payload["error"]["code"]


def test_valid_existing_error_and_warning_are_preserved():
    raw = dict(status="failed", error=dict(type="NativeError", message="Original cause"),
               warnings=["Original warning"], restoration_error="Additional restoration failure")
    result = normalize_outcome("inspect_model", raw)
    assert result.error == raw["error"]
    assert result.warnings == ("Original warning",)
    assert result.comparison_data["restoration_error"] == "Additional restoration failure"


@pytest.mark.parametrize("payload,message", [
    (dict(checks=[dict(name="mises_image", status="failed", reason="Image export failed")],
          artifacts=[dict(path="curve.csv", kind="csv")]), "Image export failed"),
    (dict(reason="Only one component exported", data=dict(components=1)), "Only one component exported"),
    (dict(data=dict(components=1)), "Legacy operation reported partial completion"),
])
def test_partial_result_recovers_warning_but_does_not_pass_workflow(payload, message):
    raw = dict(status="partial", **payload)
    original = deepcopy(raw)
    result = normalize_outcome("native_batch", raw)
    assert result.status == "partial"
    assert message in result.warnings[0]
    assert not evaluate_gate(result, [])["passed"]
    assert result.comparison_data == raw == original


def test_partial_without_any_output_remains_unverified():
    result = normalize_outcome("native_batch", dict(status="partial", reason="No outputs"))
    assert result.status == "unverified"
    assert result.error["type"] == "LegacyContractError"


def test_canonical_invalid_failure_is_not_repaired_as_legacy():
    with pytest.raises(ValidationError, match="nonempty message"):
        normalize_outcome("inspect_model", dict(contract="JobResult/v1", operation="inspect_model",
                                                status="failed",
                                                error=dict(message="")))


def test_preparation_failure_keeps_preparation_stage():
    result = normalize_outcome("prepare_native_program", dict(status="failed", reason="Invalid source"))
    assert result.stage == "preparation" and result.status == "failed"
    assert not result.execution_accepted


@pytest.mark.parametrize("legacy", [
    dict(status="failed", restoration_error="Original scene not restored"),
    dict(status="partial", data=dict(exported=1), checks=[dict(status="failed", reason="Image missing")]),
])
def test_workflow_preserves_legacy_verdict_and_stops_before_next_operation(tmp_path, monkeypatch, legacy):
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.service import Service

    service = Service(Settings(tmp_path))
    observed = []
    monkeypatch.setattr(service, "inspect_model", lambda **kwargs: deepcopy(legacy))
    monkeypatch.setattr(service, "process_curve", lambda **kwargs: observed.append(kwargs))
    workflow = service.create_workflow("Legacy failure", [
        dict(id="first", action="inspect_model", arguments={}),
        dict(id="next", action="process_curve", arguments={}),
    ])["artifacts"][0]["path"]
    result = service.run_workflow(workflow)
    assert result["status"] == "failed"
    assert observed == []
    assert result["data"]["steps"]["first"]["status"] == legacy["status"]
