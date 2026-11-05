"""Real full/compact stdio smoke with a host-only recipe and no native context."""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


def decoded(result):
    if result.structuredContent is not None:
        return result.structuredContent
    rows = [json.loads(block.text) for block in result.content if block.type == "text"]
    return rows[0] if len(rows) == 1 else rows


@pytest.mark.parametrize("profile", ["full", "compact"])
def test_pinned_material_recipe_is_discovered_and_executed_through_stdio(tmp_path, profile):
    pytest.importorskip("ansys.dyna.core")
    source = tmp_path / "input.k"
    source.write_text("*KEYWORD\n*END\n", encoding="ascii")
    async def scenario():
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1", LSPP_WORKSPACE=str(tmp_path / "work"),
                   LSPP_ALLOWED_ROOTS=str(tmp_path), LSPP_TOOL_PROFILE=profile)
        config = StdioServerParameters(command=sys.executable, args=["-B", "-m", "ls_prepost_mcp.server"], env=env)
        async with stdio_client(config) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                async def call(operation, arguments):
                    if profile == "full":
                        return await session.call_tool(operation, arguments)
                    return await session.call_tool("lspp_run_operation", dict(operation=operation, execution="direct", arguments=arguments))
                found = await call("find_recipe", dict(task_id="P03", channel="keyword", include_candidates=True))
                assert not found.isError
                rows = decoded(found)
                if isinstance(rows, dict):
                    rows = rows["result"]
                assert len(rows) == 9
                selected = next(row for row in rows if row["id"] == "model:mat-001-elastic")
                assert "@" in selected["reference"]
                result = await call("run_recipe", dict(recipe=selected["reference"], parameters=dict(units="mm-t-s", mid=7,
                    params=dict(ro=7.8e-9, e=210000., pr=.3)), model=str(source)))
                assert not result.isError
                outcome = decoded(result)
                assert outcome["operation"] == "run_recipe" and outcome["status"] == "succeeded" and outcome["backend"] == "keyword"
                assert outcome["data"]["recipe"]["reference_policy"] == "pinned"
                assert outcome["data"]["recipe"]["native_executed"] is False
    asyncio.run(asyncio.wait_for(scenario(), timeout=90))
