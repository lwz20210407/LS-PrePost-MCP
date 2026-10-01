import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_discovery_reference_and_rejection(tmp_path):
    async def scenario():
        env = dict(os.environ, LSPP_WORKSPACE=str(tmp_path),
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
                        "inspect_workflow", "run_workflow_sweep"} <= names
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
