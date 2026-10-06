"""Shared workflow-boundary outcome contract; execution and check verdicts are separate."""

from pydantic import ValidationError

from .core.contracts import Artifact, CheckResult, JobResult

CHECK_PATHS = {
    "check_gui_shell_quality": ("verification", "passed_checks"),
    "check_gui_solid_quality": ("verification", "passed_checks"),
    "check_gui_keywords": ("verification", "passed_checks"),
    "inspect_gui_mesh_quality": ("data", "valid_within_scope"),
    "inspect_mesh_quality": ("data", "valid_within_scope"),
    "validate_model_references": ("data", "valid_within_scope"),
}
PREPARATION_ACTIONS = {"prepare_native_program"}


def result_value(result, path):
    """Strict JSON traversal: booleans/negative indexes never act as array indexes."""
    value = result
    for key in path:
        if isinstance(value, dict) and isinstance(key, str):
            value = value[key]
        elif isinstance(value, list) and type(key) is int and 0 <= key < len(value):
            value = value[key]
        else:
            raise KeyError("Result path is missing or has an incompatible type")
    return value


def normalize_outcome(action, result) -> JobResult:
    """Convert legacy envelopes once at the operation boundary, not in gates."""
    if isinstance(result, dict) and result.get("contract") == "JobResult/v1":
        result = JobResult.model_validate(result)
    if isinstance(result, JobResult):
        job = JobResult.model_validate(result)
        if job.operation != action:
            raise ValueError("JobResult operation does not match dispatched action")
        expected_stage = "preparation" if action in PREPARATION_ACTIONS else "execution"
        if job.stage != expected_stage:
            raise ValueError("JobResult stage does not match dispatched action")
        if action in CHECK_PATHS and not any(check.name == "quality" for check in job.checks):
            job = JobResult.model_validate(
                {
                    **job.model_dump(),
                    "checks": (
                        *job.checks,
                        CheckResult(name="quality", status="missing", source_path=CHECK_PATHS[action]),
                    ),
                }
            )
        return job
    raw = result if isinstance(result, dict) else {}
    legacy_status = raw.get("status")
    prepared = action in PREPARATION_ACTIONS
    status = (
        legacy_status
        if isinstance(legacy_status, str)
        and legacy_status in {"succeeded", "failed", "partial", "unverified"}
        else "unverified"
    )
    if prepared:
        status = (
            "succeeded"
            if legacy_status == "prepared"
            else "failed"
            if legacy_status == "failed"
            else "unverified"
        )
    path = CHECK_PATHS.get(action)
    checks = []
    if path is not None:
        try:
            value = result_value(raw, path)
            verdict = (
                "passed"
                if value is True
                else "failed"
                if value is False
                else "not_applicable"
                if value is None
                else "invalid"
            )
        except KeyError:
            verdict = "missing"
        checks.append(CheckResult(name="quality", status=verdict, source_path=path))

    def metadata(name):
        for candidate in (("verification", name), ("data", name), (name,)):
            try:
                value = result_value(raw, candidate)
                if isinstance(value, str) and value.strip():
                    return value
            except KeyError:
                pass
        return None

    try:
        artifacts = []
        for artifact in raw.get("artifacts", []):
            sha, size = artifact.get("sha256"), artifact.get("size")
            artifacts.append(
                Artifact(
                    path=artifact["path"],
                    kind=artifact.get("kind", "unknown"),
                    sha256=sha,
                    size_bytes=size,
                    verification="verified"
                    if artifact.get("validated") is True and sha is not None and size is not None
                    else "unverified",
                    metadata={
                        key: value
                        for key, value in artifact.items()
                        if key not in {"path", "kind", "sha256", "size"}
                    },
                )
            )
        return JobResult(
            operation=action,
            status=status,
            stage="preparation" if prepared else "execution",
            job_id=raw.get("job_id"),
            backend=metadata("backend"),
            scope=metadata("scope"),
            data={} if raw.get("data") is None else raw["data"],
            artifacts=artifacts,
            checks=checks,
            warnings=raw.get("warnings", []),
            error=raw.get("error"),
            comparison_data=raw,
        )
    except (ValidationError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return JobResult(
            operation=action,
            status="unverified",
            checks=checks,
            comparison_data=raw,
            warnings=["Legacy result does not satisfy JobResult"],
            error=dict(type="LegacyContractError", message=str(exc)),
        )


def describe_outcome(result: JobResult):
    """Keep the existing outcomes.json projection while gates use JobResult."""
    legacy = result.comparison_data
    status = result.status if legacy is None else legacy.get("status")
    return dict(
        action=result.operation,
        execution_status=status if isinstance(status, str) else "missing_or_invalid",
        execution_accepted=result.execution_accepted,
        stage=result.stage,
        check_status=result.check_status,
        check_path=result.checks[0].source_path if result.checks else None,
        backend=result.backend,
        scope=result.scope,
    )
