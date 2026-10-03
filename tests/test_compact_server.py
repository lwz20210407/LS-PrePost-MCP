import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from ls_prepost_mcp.compact_server import CompactTools
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.server import build_server
from ls_prepost_mcp.service import Service


def test_compact_schemas_are_on_demand_and_invalid_calls_have_no_side_effects(tmp_path):
    service = Service(Settings(tmp_path))
    compact = CompactTools(service)
    names = {t.name for t in asyncio.run(build_server(service.settings, "compact").list_tools())}
    assert names == {"lspp_find_operations", "lspp_describe_operation", "lspp_run_operation"}
    description = compact.lspp_describe_operation("extract_native_fields", "gui", "missing")
    properties = description["input_schema"]["properties"]
    assert "path" not in properties and "entity_ids" in properties
    for arguments in (dict(nx=True, ny=2, size=[1., 1.], units="mm"),
                      dict(nx=2, ny=2, size=[1., 1.], units="mm", invented=True)):
        with pytest.raises(ValidationError):
            compact.lspp_run_operation("create_shell_plate", arguments, "direct")
    assert not list(tmp_path.iterdir())
    assert compact.lspp_find_operations("visibility")["total"] >= 1
    result = compact.lspp_run_operation("search_commands", dict(query="runpython", limit=1), "direct")
    assert result


def test_gui_routing_never_changes_backend_or_model_silently(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))
    compact = CompactTools(service)
    args = dict(nx=2, ny=2, size=[1., 1.], units="mm")
    with pytest.raises(ValueError, match="session_id"):
        compact.lspp_run_operation("create_shell_plate", args, "gui")
    with pytest.raises(ValueError, match="context session_id"):
        compact.lspp_run_operation("create_shell_plate", args, "direct", "sid")
    monkeypatch.setattr(service, "_session_manager", lambda: SimpleNamespace(read=lambda sid: dict(process_alive=False, state="closed")))
    with pytest.raises(RuntimeError, match="no batch fallback"):
        compact.lspp_run_operation("create_shell_plate", args, "gui", "sid")
    called = []
    monkeypatch.setattr(service, "_session_manager", lambda: SimpleNamespace(read=lambda sid: dict(process_alive=True, state="ready")))
    monkeypatch.setattr(service, "gui_session_action", lambda sid, action, arguments: called.append((sid, action, arguments)) or {"status": "succeeded"})
    assert compact.lspp_run_operation("create_shell_plate", args, "gui", "sid")["status"] == "succeeded"
    assert called == [("sid", "create_shell_plate", args)]
    assert not list(tmp_path.iterdir())


def test_preview_keeps_execution_and_readiness_unproven(tmp_path):
    compact = CompactTools(Service(Settings(tmp_path)))
    result = compact.lspp_run_operation("create_shell_plate", dict(nx=2, ny=3, size=[1., 1.], units="mm"), "gui", "missing", preview=True)
    assert result["executed"] is False and result["status"] == "planned"
    assert not list(tmp_path.iterdir())
    with pytest.raises(ValueError):
        compact.lspp_describe_operation("__dict__")


def test_every_registered_operation_has_a_strict_discoverable_schema(tmp_path):
    compact = CompactTools(Service(Settings(tmp_path)))
    for name in compact.functions:
        schema = compact.lspp_describe_operation(name)["input_schema"]
        assert schema["additionalProperties"] is False
    assert not list(tmp_path.iterdir())
