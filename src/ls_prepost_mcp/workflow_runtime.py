"""Shared operation routing and side-effect-free workflow planning.

Planning checks composition, not native support or engineering validity. The
same route is used by the executor so a preview cannot choose a different API.
"""

import inspect
import json
from dataclasses import dataclass
from typing import get_type_hints

from pydantic import TypeAdapter

from .operation_registry import WORKFLOW_ACTIONS, WORKFLOW_ALIASES, domain_for, resolve_operation
from .outcomes import CHECK_PATHS


@dataclass(frozen=True)
class DeferredValue:
    source: str


def has_deferred(value):
    if isinstance(value, DeferredValue):
        return True
    if isinstance(value, dict):
        return any(has_deferred(v) for v in value.values())
    return isinstance(value, list) and any(has_deferred(v) for v in value)


@dataclass(frozen=True)
class OperationRoute:
    action: str
    method: str
    kind: str
    implicit_arguments: tuple[str, ...] = ()

    def signature(self, service):
        signature = inspect.signature(getattr(service, self.method))
        return signature.replace(
            parameters=[p for name, p in signature.parameters.items() if name not in self.implicit_arguments]
        )

    def validate_arguments(self, service, arguments):
        forbidden = set(arguments) & set(self.implicit_arguments)
        if forbidden:
            raise ValueError("Arguments supplied by workflow context: " + ", ".join(sorted(forbidden)))
        bound = self.signature(service).bind(**arguments)
        hints = get_type_hints(getattr(service, self.method), include_extras=True)
        for key, value in bound.arguments.items():
            if key in hints and not has_deferred(value):
                # Validate without coercing values or invoking the operation.
                TypeAdapter(hints[key]).validate_python(value, strict=True)

    def execute(self, service, arguments, session_id):
        self.validate_arguments(service, arguments)
        if self.kind == "session_native":
            return service.gui_session_action(session_id, self.action, arguments)
        if self.kind == "session":
            return getattr(service, self.method)(session_id=session_id, **arguments)
        return getattr(service, self.method)(**arguments)


def operation_route(service, action, session_id):
    if action not in WORKFLOW_ACTIONS:
        raise ValueError("Unsupported workflow action")
    if action in WORKFLOW_ALIASES:
        if not session_id:
            raise ValueError("Action requires a persistent GUI session")
        return OperationRoute(action, WORKFLOW_ALIASES[action], "session", ("session_id",))
    record = resolve_operation(action)
    if record.session_route == "session":
        if not session_id:
            raise ValueError("Action requires a persistent GUI session")
        return OperationRoute(action, record.name, "session", record.implicit_arguments)
    if session_id and record.session_route in ("native", "optional"):
        return OperationRoute(action, record.name, "session_native" if record.session_route == "native" else "session",
                              record.implicit_arguments)
    return OperationRoute(action, record.name, "service")


def bind_static(value, parameters, previous, dependencies, deferred, location):
    """Resolve parameters once; validate references without inventing their values."""
    if isinstance(value, list):
        return [
            bind_static(v, parameters, previous, dependencies, deferred, [*location, i])
            for i, v in enumerate(value)
        ]
    if not isinstance(value, dict):
        return value
    if "$param" in value:
        key = value["$param"]
        if set(value) != {"$param"} or not isinstance(key, str) or key not in parameters:
            raise ValueError("Missing/invalid workflow parameter: " + str(key))
        return parameters[key]
    if "$result" in value or "$artifact" in value:
        result_binding = "$result" in value
        token = "$result" if result_binding else "$artifact"
        source = value[token]
        if not isinstance(source, str) or source not in previous:
            raise ValueError("Binding must refer to an earlier step: " + str(source))
        if result_binding:
            path = value.get("path")
            if (
                set(value) != {"$result", "path"}
                or not isinstance(path, list)
                or any(not (isinstance(k, str) and k or type(k) is int and k >= 0) for k in path)
            ):
                raise ValueError("Invalid result binding path")
        else:
            index = value.get("index", 0)
            if set(value) - {"$artifact", "index"} or type(index) is not int or index < 0:
                raise ValueError("Invalid artifact binding index")
        dependencies.add(source)
        deferred.append(dict(argument_path=location, source_step=source, binding=value))
        return DeferredValue(source)
    if any(str(key).startswith("$") for key in value):
        raise ValueError("Unknown workflow expression")
    return {
        key: bind_static(v, parameters, previous, dependencies, deferred, [*location, key])
        for key, v in value.items()
    }


def compile_workflow(service, workflow, parameters=None, session_id=None):
    """Return an inspectable plan; never create jobs, read models or contact GUI."""
    from .workflow_checks import validate_checks
    from .workflows import resolve, validate_steps

    report = dict(
        schema_version=1,
        status="invalid",
        ready=False,
        executed=False,
        steps=[],
        errors=[],
        warnings=[],
        validation_scope="static_composition_only",
        not_checked=[
            "native_build_support",
            "session_liveness_and_model_state",
            "input_files",
            "runtime_result_paths_and_types",
            "engineering_semantics_and_quality",
        ],
    )

    def error(message, step_id=None):
        report["errors"].append(dict(step_id=step_id, message=str(message)))

    try:
        if not isinstance(workflow, dict) or workflow.get("schema_version") != 1:
            raise ValueError("Unsupported workflow schema")
        if workflow.get("unrecognized_commands") or workflow.get("review_reasons"):
            raise ValueError("Workflow requires review")
        steps = workflow.get("steps")
        validate_steps(steps)
        defaults = workflow.get("defaults", {})
        if not isinstance(defaults, dict) or (parameters is not None and not isinstance(parameters, dict)):
            raise ValueError("Workflow parameters/defaults must be objects")
        params = {**defaults, **(parameters or {})}
        json.dumps([workflow, params], allow_nan=False)
        if workflow.get("requires_gui_session") and not session_id:
            raise ValueError("This recording requires a persistent GUI session")
        if workflow.get("initial_model") and not session_id:
            raise ValueError("A recorded initial model requires a persistent GUI session")
        empty = workflow.get("initial_expected_empty", False)
        if type(empty) is not bool or empty and (not workflow.get("initial_model") or workflow.get("initial_file_type", "keyword") != "keyword"):
            raise ValueError("initial_expected_empty requires a keyword initial_model and a boolean value")
    except (ValueError, TypeError) as exc:
        error(exc)
        return report
    previous = set()
    for step in steps:
        ident, action = step["id"], step["action"]
        entry = dict(
            id=ident,
            action=action,
            dependencies=[],
            deferred_bindings=[],
            quality_policy=step.get("quality_policy", "auto"),
            automatic_quality_verdict=action in CHECK_PATHS,
        )
        try:
            route = operation_route(service, action, session_id)
            entry.update(module=domain_for(route.method), route=route.kind, method=route.method)
            dependencies = set()
            arguments = bind_static(
                step.get("arguments", {}), params, previous, dependencies, entry["deferred_bindings"], []
            )
            entry["dependencies"] = sorted(dependencies)
            route.validate_arguments(service, arguments)
            checks = resolve(step.get("checks", []), params, {})
            validate_checks(checks, allow_parameters=False)
            entry["resolved_checks"] = checks
        except (ValueError, TypeError, KeyError) as exc:
            error(exc, ident)
        report["steps"].append(entry)
        previous.add(ident)
    if any(s["deferred_bindings"] for s in report["steps"]):
        report["warnings"].append(
            "Result-dependent arguments are checked again immediately before dispatch; their values cannot be certified statically."
        )
    report.update(ready=not report["errors"], status="ready" if not report["errors"] else "invalid")
    return report
