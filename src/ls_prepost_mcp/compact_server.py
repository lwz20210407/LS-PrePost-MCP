"""Opt-in small MCP surface with on-demand schemas and unchanged typed operations."""

import inspect
import json
from pathlib import Path
from typing import Any, Literal, get_type_hints

from pydantic import ConfigDict, StrictInt, create_model

from . import knowledge
from .registry import SERVICE_TOOLS
from .workflow_runtime import operation_route

KNOWLEDGE = ("search_knowledge", "list_capabilities", "search_commands", "search_workflows")


class CompactTools:
    def __init__(self, service):
        self.service = service
        self.functions = {name: getattr(service, name) for name in SERVICE_TOOLS}
        self.functions.update({name: getattr(knowledge, name) for name in KNOWLEDGE})
        plan = json.loads((Path(__file__).with_name("data")/"development_plan.json").read_text(encoding="utf8"))
        self.domains = {name: module["id"] for module in plan["modules"] for name in module["current_tools"]}
        self.domains.update({name: "knowledge" for name in KNOWLEDGE})

    def lspp_find_operations(self, query: str = "", domain: str | None = None,
                             offset: StrictInt = 0, limit: StrictInt = 20) -> dict:
        """Discover registered operations by domain/text, without loading all schemas. Then describe the chosen operation. Catalog presence is not native certification."""
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("offset must be nonnegative and limit must be 1..50")
        domains = sorted(set(self.domains.values()))
        if domain is not None and domain not in domains:
            raise ValueError("Unknown domain; choose "+", ".join(domains))
        terms = query.lower().split()
        rows = []
        for name, function in self.functions.items():
            group = self.domains.get(name, "unassigned")
            description = inspect.getdoc(function) or ""
            if (domain is None or group == domain) and all(t in (name+" "+description).lower() for t in terms):
                rows.append(dict(name=name, domain=group, summary=description.split(". ")[0][:220]))
        rows.sort(key=lambda item: (item["domain"], item["name"]))
        return dict(operations=rows[offset:offset+limit], total=len(rows), domains=domains,
                    next_offset=offset+limit if offset+limit < len(rows) else None,
                    note="Use list_capabilities to check actual native/size/version scope")

    def _resolve(self, operation, execution, session_id):
        if operation not in self.functions:
            raise ValueError("Unknown registered operation")
        if execution not in ("direct", "gui"):
            raise ValueError("execution must be direct or gui")
        if execution == "gui":
            if not session_id:
                raise ValueError("GUI execution requires an explicit session_id; no automatic batch fallback")
            route = operation_route(self.service, operation, session_id)
            function = getattr(self.service, route.method)
            signature = route.signature(self.service)
        else:
            if session_id is not None:
                raise ValueError("direct does not consume a context session_id; use gui or an explicit lifecycle operation")
            route, function = None, self.functions[operation]
            signature = inspect.signature(function)
        hints = get_type_hints(function, include_extras=True)
        fields = {name: (hints.get(name, parameter.annotation),
                         ... if parameter.default is inspect.Parameter.empty else parameter.default)
                  for name, parameter in signature.parameters.items()}
        model = create_model("OperationArguments", __config__=ConfigDict(extra="forbid", strict=True), **fields)
        return function, route, model

    def lspp_describe_operation(self, operation: str, execution: Literal["direct", "gui"] = "direct",
                                session_id: str | None = None) -> dict:
        """Return one operation's strict argument schema and explicit execution route. GUI context removes implicit model/session arguments; never falls back to another process."""
        function, route, model = self._resolve(operation, execution, session_id)
        return dict(operation=operation, description=inspect.getdoc(function), execution=execution,
                    route=route.kind if route else "direct", method=route.method if route else operation,
                    input_schema=model.model_json_schema(),
                    native_availability="Not established by schema discovery; inspect capabilities/environment/session")

    def lspp_run_operation(self, operation: str, arguments: dict, execution: Literal["direct", "gui"],
                           session_id: str | None = None, preview: bool = False) -> Any:
        """Validate and execute one registered operation using its original contract. Explicit direct/gui route, no silent instance/backend fallback. preview validates arguments without native execution. GUI requires a live ready owned session. Raw programs retain their existing trusted-source requirements."""
        function, route, model = self._resolve(operation, execution, session_id)
        if type(preview) is not bool:
            raise ValueError("preview must be boolean")
        model.model_validate(arguments, strict=True)
        if preview:
            return dict(status="planned", executed=False, operation=operation, execution=execution,
                        route=route.kind if route else "direct", arguments_valid=True,
                        note="Composition only; native readiness and engineering checks not performed")
        if route:
            meta = self.service._session_manager().read(session_id)
            if not meta.get("process_alive") or meta["state"] != "ready" or meta.get("active_request"):
                raise RuntimeError("GUI context is not ready; no batch fallback and no uncertain-operation replay")
            return route.execute(self.service, arguments, session_id)
        return function(**arguments)
