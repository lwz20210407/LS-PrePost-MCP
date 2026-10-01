"""Shared workflow-boundary outcome contract; execution and check verdicts are separate."""

from dataclasses import asdict, dataclass

CHECK_PATHS = {
    "check_gui_shell_quality": ("verification", "passed_checks"),
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


@dataclass(frozen=True)
class OperationOutcome:
    action: str
    execution_status: str
    execution_accepted: bool
    stage: str
    check_status: str
    check_path: tuple | None
    backend: str | None
    scope: str | None

    def to_dict(self):
        return asdict(self)


def normalize_outcome(action, result):
    """Project existing results without overwriting them or inferring physical validity."""
    status = result.get("status") if isinstance(result, dict) else None
    status = status if isinstance(status, str) else "missing_or_invalid"
    prepared = action in PREPARATION_ACTIONS
    path = CHECK_PATHS.get(action)
    check = "not_reported"
    if path is not None:
        try:
            value = result_value(result, path)
            check = (
                "passed"
                if value is True
                else "failed"
                if value is False
                else "not_applicable"
                if value is None
                else "invalid"
            )
        except KeyError:
            check = "missing"

    def metadata(name):
        for candidate in (("verification", name), ("data", name), (name,)):
            try:
                value = result_value(result, candidate)
                if isinstance(value, str):
                    return value
            except KeyError:
                pass
        return None

    return OperationOutcome(
        action,
        status,
        status == ("prepared" if prepared else "succeeded"),
        "preparation" if prepared else "execution",
        check,
        path,
        metadata("backend"),
        metadata("scope"),
    )
