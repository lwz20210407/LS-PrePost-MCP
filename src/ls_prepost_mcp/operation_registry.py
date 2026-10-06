"""Runtime operation metadata and compatibility aliases, independent of plans."""

import inspect
import json
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import get_type_hints


@dataclass(frozen=True)
class Operation:
    name: str
    domain: str
    target: str
    task_id: str
    kind: str = "service"
    workflow: bool = False
    session_route: str | None = None
    mutation: bool = False
    gui_transform: bool = False
    session_path: bool = False
    legacy_until: str = "v0.6"
    note: str | None = None

    @property
    def operation_id(self):
        return self.domain + "." + self.name

    @property
    def implicit_arguments(self):
        if self.session_route == "native":
            return ("model", "d3plot", "file_type") + (("path",) if self.session_path else ())
        return ("session_id",)


def _load():
    data = json.loads(Path(__file__).with_name("data").joinpath("operations.json").read_text(encoding="utf8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported runtime registry schema")
    records = tuple(Operation(**row) for row in data["operations"])
    if len({r.name for r in records}) != len(records) or len({r.operation_id for r in records}) != len(records):
        raise ValueError("Duplicate runtime operation or alias")
    for record in records:
        if (not record.name.isidentifier() or record.name.startswith("_")
                or record.kind not in ("service", "knowledge")
                or record.session_route not in (None, "native", "session", "optional")
                or any(type(getattr(record, key)) is not bool for key in ("workflow", "mutation", "gui_transform", "session_path"))):
            raise ValueError("Invalid runtime operation metadata")
    aliases = data["workflow_aliases"]
    if any(value not in {r.name for r in records} for value in aliases.values()):
        raise ValueError("Unresolved workflow alias")
    return records, aliases


OPERATIONS, WORKFLOW_ALIASES = _load()
BY_NAME = {record.name: record for record in OPERATIONS}
BY_ID = {record.operation_id: record for record in OPERATIONS}
SERVICE_TOOLS = tuple(r.name for r in OPERATIONS if r.kind == "service")
KNOWLEDGE_TOOLS = tuple(r.name for r in OPERATIONS if r.kind == "knowledge")
NATIVE_ACTIONS = frozenset(r.name for r in OPERATIONS if r.session_route == "native")
GUI_ACTIONS = frozenset(r.name for r in OPERATIONS if r.workflow and r.session_route == "session")
WORKFLOW_ACTIONS = frozenset(r.name for r in OPERATIONS if r.workflow) | WORKFLOW_ALIASES.keys()
MUTATIONS = frozenset(r.name for r in OPERATIONS if r.mutation)
GUI_BATCH_ACTIONS = frozenset(r.name for r in OPERATIONS if r.gui_transform)


def resolve_operation(name):
    record = BY_NAME.get(name) or BY_ID.get(name)
    if record is None:
        raise ValueError("Unknown registered operation")
    return record


def domain_for(name):
    return resolve_operation(WORKFLOW_ALIASES.get(name, name)).domain


def bind_alias(function, name):
    """Expose the old name with its original typed signature until v0.6."""
    record = resolve_operation(name)

    @wraps(function)
    def alias(*args, **kwargs):
        return function(*args, **kwargs)

    alias.__name__ = record.name
    hints = get_type_hints(function, include_extras=True)
    signature = inspect.signature(function)
    alias.__annotations__ = hints
    alias.__signature__ = signature.replace(
        parameters=[p.replace(annotation=hints.get(p.name, p.annotation)) for p in signature.parameters.values()],
        return_annotation=hints.get("return", signature.return_annotation))
    alias.operation_id = record.operation_id
    alias.legacy_until = record.legacy_until
    return alias


def migration_map():
    return {r.name: dict(target=r.target, task_id=r.task_id, legacy_until=r.legacy_until,
                         **({"note": r.note} if r.note else {})) for r in sorted(OPERATIONS, key=lambda r: r.name)}
