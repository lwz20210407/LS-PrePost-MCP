import asyncio
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
                        "extract_native_stress", "create_solid_box", "compose_keyword_deck"} <= names
                result = await session.call_tool("search_commands", {"query": "runpython", "limit": 3})
                assert not result.isError
                invalid = await session.call_tool("create_shell_plate", {"nx": 0, "ny": 1, "size": [1, 1], "units": "mm"})
                assert invalid.isError
                assert not (tmp_path / "jobs").exists()
    asyncio.run(scenario())
