import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.gui_solid_quality import parse_solid_check, verified_failed_ids
from ls_prepost_mcp.outcomes import normalize_outcome
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.workflow_checks import evaluate_gate

COMMAND = "elemcheck solid aratio gt 1.5"
FAILED = (
    COMMAND
    + "\nNumber of elements larger than criteria: 1\nFailed elements accounted for 50.00% of the total solid elements\n"
)


def test_native_count_percent_and_capture_must_agree():
    report = parse_solid_check(FAILED, COMMAND, "gt", 2, True)
    assert report["violated_count"] == 1 and report["violated_percent"] == 50
    for text, comparison, count, enabled in [
        (FAILED, "lt", 2, True),
        (FAILED, "gt", 2, False),
        (FAILED, "gt", 1, True),
        (FAILED + FAILED, "gt", 2, True),
        (FAILED.replace("solid elements", "shell elements"), "gt", 2, True),
    ]:
        with pytest.raises(ValueError):
            parse_solid_check(text, COMMAND, comparison, count, enabled)


def test_empty_log_is_never_success_and_zero_requires_native_control_evidence():
    assert parse_solid_check(COMMAND + "\n", COMMAND, "gt", 2, False)["violated_count"] == 0
    for text, enabled in [
        ("", False),
        (COMMAND, True),
        (COMMAND, None),
        (COMMAND, 0),
        (COMMAND + "\ninvalid command\n", False),
    ]:
        with pytest.raises(ValueError):
            parse_solid_check(text, COMMAND, "gt", 2, enabled)


def test_solid_native_findings_are_automatic_workflow_gates():
    result = dict(status="succeeded", verification=dict(passed_checks=False))
    outcome = normalize_outcome("check_gui_solid_quality", result)
    assert outcome.execution_accepted and outcome.check_status == "failed"
    assert not evaluate_gate(outcome, result, [], "auto")["passed"]
    assert evaluate_gate(outcome, result, [], "report_only")["passed"]


@pytest.mark.parametrize(
    "checks",
    [
        [],
        [dict(metric="time_step", comparison="gt", threshold=0)],
        [dict(metric="volume", comparison="gt", threshold=True)],
        [dict(metric="minimum_angle", comparison="lt", threshold=181)],
        [dict(metric="aspect_ratio", comparison="gt", threshold=float("nan"))],
        [dict(metric="volume", comparison="ge", threshold=0)],
        [dict(metric="volume", comparison="gt", threshold=0)] * 2,
    ],
)
def test_invalid_criteria_fail_before_native_access(tmp_path, checks):
    with pytest.raises(ValueError):
        Service(Settings(tmp_path)).check_gui_solid_quality("absent", checks, "mm")
    assert not (tmp_path / "jobs").exists()


def test_captured_ids_are_true_unique_registry_ids_not_array_indexes():
    assert verified_failed_ids([507, 101], 2, {101, 507}) == [101, 507]
    for values, count in [([1, 2], 2), ([101, 101], 2), ([101], 2), ([True], 1), (None, 0)]:
        with pytest.raises(ValueError):
            verified_failed_ids(values, count, {101, 507})
