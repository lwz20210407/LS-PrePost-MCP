"""Shared operation routing and side-effect-free workflow planning.

Planning checks composition, not native support or engineering validity. The
same route is used by the executor so a preview cannot choose a different API.
"""

import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import get_type_hints

from pydantic import TypeAdapter

from .outcomes import CHECK_PATHS
from .sessions import NATIVE_ACTIONS


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
    from .workflows import GUI_ACTIONS, WORKFLOW_ACTIONS

    if action not in WORKFLOW_ACTIONS:
        raise ValueError("Unsupported workflow action")
    aliases = {
        "new_model": "reset_gui_session",
        "open_model": "open_in_gui_session",
        "checkpoint": "checkpoint_gui_session",
    }
    if action in aliases or action in GUI_ACTIONS:
        if not session_id:
            raise ValueError("Action requires a persistent GUI session")
        return OperationRoute(action, aliases.get(action, action), "session", ("session_id",))
    if action in NATIVE_ACTIONS and session_id:
        implicit = ["model", "d3plot", "file_type"]
        if action in {"extract_native_fields", "extract_native_stress"}:
            implicit.append("path")
        return OperationRoute(action, action, "session_native", tuple(implicit))
    return OperationRoute(action, action, "service")


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
    except (ValueError, TypeError) as exc:
        error(exc)
        return report
    plan = json.loads(
        Path(__file__).with_name("data").joinpath("development_plan.json").read_text(encoding="utf8")
    )
    owners = {tool: module["id"] for module in plan["modules"] for tool in module["current_tools"]}
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
            entry.update(module=owners.get(route.method), route=route.kind, method=route.method)
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
