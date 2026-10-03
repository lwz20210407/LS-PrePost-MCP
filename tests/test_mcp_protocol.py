import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_discovery_reference_and_rejection(tmp_path):
    async def scenario():
        env = dict(os.environ, LSPP_WORKSPACE=str(tmp_path), LSPP_TOOL_PROFILE="full",
                   PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        config = StdioServerParameters(command=sys.executable,
                                       args=["-B", "-m", "ls_prepost_mcp.server"], env=env)
        async with stdio_client(config) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                listing = await session.list_tools()
                names = {tool.name for tool in listing.tools}
                assert {"create_shell_plate", "probe_scl", "extract_lsreader_nodal", "search_commands",
                        "extract_native_stress", "create_solid_box", "compose_keyword_deck",
                        "prepare_native_program", "execute_native_program", "execute_gui_command",
                        "create_native_macro", "run_native_macro", "check_gui_solid_quality",
                        "inspect_workflow", "run_workflow_sweep", "export_gui_animation", "export_gui_curve_plot", "render_gui_field",
                        "probe_dpf_runtime", "inspect_dpf_results", "export_dpf_result", "measure_gui_geometry"} <= names
                result = await session.call_tool("search_commands", {"query": "runpython", "limit": 3})
                assert not result.isError
                recipe = tmp_path / "preview.json"
                recipe.write_text(json.dumps(dict(schema_version=1, steps=[dict(
                    id="later", action="inspect_model", arguments={"model": {"$param": "missing"}}
                )])))
                preview = await session.call_tool("inspect_workflow", {"path": str(recipe)})
                assert not preview.isError
                assert json.loads(preview.content[0].text)["ready"] is False
                invalid = await session.call_tool("create_shell_plate", {"nx": 0, "ny": 1, "size": [1, 1], "units": "mm"})
                assert invalid.isError
                invalid_ids = await session.call_tool("extract_native_fields", {
                    "path": "missing-result", "entity_type": "solid", "entity_ids": [True],
                    "states": [1], "fields": ["stress_x"], "integration_point": "mid", "units": "MPa"})
                assert invalid_ids.isError
                assert "integer" in str(invalid_ids.content).lower()
                invalid_nodal = await session.call_tool("extract_node_history", {
                    "d3plot": "missing-result", "node_ids": [1], "quantity": "displacement",
                    "states": [True, 2], "units": "mm"})
                assert invalid_nodal.isError and "integer" in str(invalid_nodal.content).lower()
                invalid_solid = await session.call_tool("check_gui_solid_quality", {
                    "session_id": "absent", "checks": [{"metric": "volume", "comparison": "gt", "threshold": True}],
                    "units": "mm"})
                assert invalid_solid.isError
                assert not (tmp_path / "jobs").exists()
    asyncio.run(scenario())


def test_compact_stdio_discovers_validates_and_executes_on_demand(tmp_path):
    async def scenario():
        env = dict(os.environ, LSPP_WORKSPACE=str(tmp_path), LSPP_TOOL_PROFILE="compact",
                   PYTHONPATH=str(Path(__file__).resolve().parents[1]/"src"))
        config = StdioServerParameters(command=sys.executable, args=["-B", "-m", "ls_prepost_mcp.server"], env=env)
        async with stdio_client(config) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                listing = await session.list_tools()
                assert len(listing.tools) == 3
                description = await session.call_tool("lspp_describe_operation", dict(operation="search_commands"))
                assert not description.isError and "query" in json.loads(description.content[0].text)["input_schema"]["properties"]
                result = await session.call_tool("lspp_run_operation", dict(operation="search_commands", execution="direct", arguments=dict(query="runpython", limit=1)))
                assert not result.isError
                result = await session.call_tool("lspp_run_operation", dict(operation="list_jobs", execution="direct", arguments={}))
                assert not result.isError
                invalid = await session.call_tool("lspp_run_operation", dict(operation="extract_native_fields", execution="gui", session_id="missing",
                    arguments=dict(entity_type="solid", entity_ids=[True], states=[1], fields=["stress_x"], units="MPa")))
                assert invalid.isError
                assert not list(tmp_path.iterdir())
    asyncio.run(scenario())
