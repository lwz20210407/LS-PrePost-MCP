"""Bounded declarative result predicates. No Python/eval or implicit truthiness."""

import math

from .outcomes import result_value

UNARY = {"is_true", "is_false", "is_null", "not_null"}
BINARY = {"eq", "ne", "lt", "le", "gt", "ge"}
POLICIES = {"auto", "require_pass", "report_only"}


def scalar(value):
    return value is None or type(value) in (bool, str, int) or (type(value) is float and math.isfinite(value))


def validate_checks(checks, *, allow_parameters=True):
    if not isinstance(checks, list) or len(checks) > 32:
        raise ValueError("checks must be a list of at most 32 conditions")
    for check in checks:
        if not isinstance(check, dict) or set(check) - {"path", "operator", "value", "label"}:
            raise ValueError("Unknown check definition fields")
        path, operator = check.get("path"), check.get("operator")
        if (
            not isinstance(path, list)
            or not 1 <= len(path) <= 16
            or any(not (isinstance(k, str) and k or type(k) is int and k >= 0) for k in path)
        ):
            raise ValueError("Check path requires 1..16 nonempty keys/nonnegative indexes")
        if not isinstance(operator, str) or operator not in UNARY | BINARY:
            raise ValueError("Unsupported check operator")
        if "label" in check and (not isinstance(check["label"], str) or not 1 <= len(check["label"]) <= 160):
            raise ValueError("Check label must contain 1..160 characters")
        if operator in UNARY:
            if "value" in check:
                raise ValueError("Unary checks do not accept a comparison value")
            continue
        if "value" not in check:
            raise ValueError("Comparison check requires value")
        value = check["value"]
        if isinstance(value, dict) and allow_parameters:
            if set(value) == {"$param"} and isinstance(value["$param"], str) and value["$param"]:
                continue
        if not scalar(value):
            raise ValueError("Comparison value must be a finite JSON scalar or a parameter binding")
        if operator in {"lt", "le", "gt", "ge"} and type(value) not in (int, float):
            raise ValueError("Ordered comparison requires a numeric threshold, not a boolean")


def evaluate_checks(result, checks):
    validate_checks(checks, allow_parameters=False)
    evaluations = []
    for check in checks:
        report = dict(path=check["path"], operator=check["operator"], passed=False)
        if "label" in check:
            report["label"] = check["label"]
        if "value" in check:
            report["expected"] = check["value"]
        try:
            actual = result_value(result, check["path"])
        except KeyError:
            report["reason"] = "missing_result_path"
            evaluations.append(report)
            continue
        op, expected = check["operator"], check.get("value")
        if not scalar(actual):
            report.update(reason="non_scalar_or_nonfinite_result", observed_type=type(actual).__name__)
        else:
            report["observed"] = actual
            if op in UNARY:
                report["passed"] = {
                    "is_true": actual is True,
                    "is_false": actual is False,
                    "is_null": actual is None,
                    "not_null": actual is not None,
                }[op]
            elif op in ("eq", "ne"):
                compatible = type(actual) is type(expected) or (
                    type(actual) in (int, float) and type(expected) in (int, float)
                )
                if not compatible:
                    report["reason"] = "incompatible_comparison_types"
                else:
                    report["passed"] = actual == expected if op == "eq" else actual != expected
            elif type(actual) not in (int, float):
                report["reason"] = "ordered_comparison_requires_numeric_result"
            else:
                report["passed"] = {
                    "lt": actual < expected,
                    "le": actual <= expected,
                    "gt": actual > expected,
                    "ge": actual >= expected,
                }[op]
            if not report["passed"] and "reason" not in report:
                report["reason"] = "predicate_not_satisfied"
        evaluations.append(report)
    return evaluations


def evaluate_gate(outcome, result, checks, policy="auto"):
    if policy not in POLICIES:
        raise ValueError("Unknown quality policy")
    required = policy == "require_pass" or (policy == "auto" and outcome.check_path is not None)
    predicates = evaluate_checks(result, checks)
    reasons = []
    if not outcome.execution_accepted:
        reasons.append("execution_status_not_accepted")
    if required and outcome.check_status != "passed":
        reasons.append("quality_verdict_" + outcome.check_status)
    if any(not predicate["passed"] for predicate in predicates):
        reasons.append("explicit_check_failed")
    return dict(
        passed=not reasons,
        quality_policy=policy,
        quality_required=required,
        quality_verdict=outcome.check_status,
        checks=predicates,
        reasons=reasons,
        report_only=policy == "report_only",
    )
