"""Existing operation names expose migration facts, without changing execution."""
import asyncio
import inspect
import json
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ls_prepost_mcp.compact_server import CompactTools
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.operation_registry import OPERATIONS, bind_alias, resolve_operation
from ls_prepost_mcp.server import build_server
from ls_prepost_mcp.service import Service

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = "ls-prepost-mcp"


def wire_tools(server):
    return {tool.name: tool.model_dump(mode="json", by_alias=True) for tool in asyncio.run(server.list_tools())}


def test_full_mcp_tool_catalog_exposes_every_existing_operation_migration_fact(tmp_path):
    tools = wire_tools(build_server(Settings(tmp_path / "jobs"), "full"))
    registered = {record.name for record in OPERATIONS}
    assert set(tools) == registered
    for record in OPERATIONS:
        metadata = (tools[record.name].get("_meta") or {}).get(NAMESPACE)
        assert metadata is not None, "MCP list_tools lost migration facts: " + record.name
        assert metadata["operation_id"] == record.operation_id
        assert metadata["migration_target"] == record.target
        assert metadata["legacy_until"] == record.legacy_until
        assert metadata["compatibility_alias"] is (record.name != record.target)
        assert metadata["migration_target_registered"] is (record.target in registered)
        if record.name != record.target:
            assert "v0.6" in tools[record.name]["description"]
    assert not (tmp_path / "jobs").exists()


@pytest.mark.parametrize("name,target,registered", [
    ("inspect_model", "model_info", True),
    ("compute_stress_invariants", "extract_field", True),
    ("search_commands", "command_help", True),
    ("set_gui_entity_visibility", "set_display", False),
    ("probe_dpf_runtime", "alias", False),
    ("edit_keywords", "edit_keywords", True),
])
def test_compact_find_and_describe_return_same_migration_facts_for_names_and_ids(tmp_path, name, target, registered):
    compact = CompactTools(Service(Settings(tmp_path / "jobs")))
    rows = compact.lspp_find_operations(name)["operations"]
    found = next(row for row in rows if row["name"] == name)
    record = resolve_operation(name)
    for reference in (name, record.operation_id):
        described = compact.lspp_describe_operation(reference)
        assert described["migration_target"] == found["migration_target"] == target
        assert described["legacy_until"] == found["legacy_until"] == record.legacy_until
        assert described["operation_id"] == found["operation_id"] == record.operation_id
        assert described["compatibility_alias"] == found["compatibility_alias"] == (name != target)
        assert described["migration_target_registered"] == found["migration_target_registered"] == registered
        assert described["input_schema"]["additionalProperties"] is False
        if name != target:
            assert "v0.6" in described["description"] and target in described["description"]
            if not registered:
                assert "not a registered tool" in described["description"]
    assert not (tmp_path / "jobs").exists()


def test_default_profile_and_alias_execution_contract_remain_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("LSPP_TOOL_PROFILE", raising=False)
    settings = Settings(tmp_path / "jobs")
    default = wire_tools(build_server(settings))
    full = wire_tools(build_server(settings, "full"))
    compact = wire_tools(build_server(settings, "compact"))
    assert set(default) == set(full) == {record.name for record in OPERATIONS}
    assert set(compact) == {"lspp_find_operations", "lspp_describe_operation", "lspp_run_operation"}
    service = Service(settings)
    function = service.list_jobs
    alias = bind_alias(function, "list_jobs")
    assert inspect.signature(alias) == inspect.signature(function)
    assert alias(limit=1) == function(limit=1) == []
    canonical = full["edit_keywords"]
    assert canonical["description"] == inspect.getdoc(service.edit_keywords)
    metadata = (canonical.get("_meta") or {}).get(NAMESPACE)
    assert metadata and metadata["compatibility_alias"] is False and metadata["legacy_until"] is None


def decoded(result):
    if result.structuredContent is not None:
        return result.structuredContent
    texts = [json.loads(block.text) for block in result.content if block.type == "text"]
    return texts[0] if len(texts) == 1 else texts


@pytest.mark.parametrize("profile", ["full", "compact"])
def test_migration_facts_reach_real_stdio_list_and_compact_describe(tmp_path, profile):
    async def scenario():
        environment = dict(os.environ, PYTHONPATH=os.pathsep.join((str(ROOT / "src"), str(ROOT))),
                           PYTHONDONTWRITEBYTECODE="1", LSPP_WORKSPACE=str(tmp_path / "jobs"),
                           LSPP_ALLOWED_ROOTS=str(tmp_path), LSPP_TOOL_PROFILE=profile)
        config = StdioServerParameters(command=sys.executable, args=["-B", "-m", "ls_prepost_mcp.server"], env=environment)
        async with stdio_client(config) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                catalog = {tool.name: tool.model_dump(mode="json", by_alias=True) for tool in (await session.list_tools()).tools}
                if profile == "full":
                    assert set(catalog) == {record.name for record in OPERATIONS}
                    metadata = (catalog["inspect_model"].get("_meta") or {}).get(NAMESPACE)
                    assert metadata and metadata["migration_target"] == "model_info" and metadata["legacy_until"] == "v0.6"
                    assert (catalog["edit_keywords"].get("_meta") or {})[NAMESPACE]["compatibility_alias"] is False
                    result = await session.call_tool("list_jobs", {"limit": 1})
                    assert not result.isError
                    returned = decoded(result)
                    assert (returned.get("result") if isinstance(returned, dict) else returned) == []
                else:
                    assert set(catalog) == {"lspp_find_operations", "lspp_describe_operation", "lspp_run_operation"}
                    found_result = await session.call_tool("lspp_find_operations", {"query": "inspect_model"})
                    assert not found_result.isError
                    found = next(row for row in decoded(found_result)["operations"] if row["name"] == "inspect_model")
                    result = await session.call_tool("lspp_describe_operation", {"operation": "runtime.inspect_model"})
                    assert not result.isError
                    described = decoded(result)
                    assert described["legacy_until"] == found["legacy_until"] == "v0.6"
                    assert described["migration_target"] == found["migration_target"] == "model_info"
                    run = await session.call_tool("lspp_run_operation", {"operation": "runtime.list_jobs", "execution": "direct", "arguments": {"limit": 1}})
                    assert not run.isError
                    returned = decoded(run)
                    assert (returned.get("result") if isinstance(returned, dict) else returned) == []
        assert not (tmp_path / "jobs").exists()
    asyncio.run(asyncio.wait_for(scenario(), timeout=90))
