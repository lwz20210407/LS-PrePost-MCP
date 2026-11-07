"""Full/compact host stdio routes retain run_recipe's public shape for P10."""
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
    rows = [json.loads(c.text) for c in result.content if c.type == "text"]
    return rows[0] if len(rows) == 1 else rows


@pytest.mark.parametrize("profile", ["full", "compact"])
def test_p10_pinned_story_through_existing_stdio_run_recipe(tmp_path, profile):
    pytest.importorskip("ansys.dyna.core")
    source = tmp_path / "input.k"
    source.write_text("*KEYWORD\n*END\n", encoding="ascii")
    async def scenario():
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(ROOT / "src"), str(ROOT))),
            PYTHONDONTWRITEBYTECODE="1", LSPP_WORKSPACE=str(tmp_path / "work"),
            LSPP_ALLOWED_ROOTS=str(tmp_path), LSPP_TOOL_PROFILE=profile, TEMP=str(tmp_path), TMP=str(tmp_path))
        config = StdioServerParameters(command=sys.executable, args=["-B", "-m", "ls_prepost_mcp.server"], env=env)
        async with stdio_client(config) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                async def call(operation, arguments):
                    if profile == "full":
                        return await session.call_tool(operation, arguments)
                    return await session.call_tool("lspp_run_operation", dict(operation=operation, execution="direct", arguments=arguments))
                result = await call("find_recipe", dict(task_id="P10", channel="keyword", include_candidates=True))
                assert not result.isError
                rows = decoded(result)
                if isinstance(rows, dict):
                    rows = rows["result"]
                assert len(rows) == 7
                row = next(r for r in rows if r["id"] == "model:control-output")
                outcome = await call("run_recipe", dict(recipe=row["reference"], model=str(source), parameters=dict(
                    units="g-mm-us", termination={"endtim": 50.}, d3plot={"dt": 1.},
                    ascii={"names": ["glstat", "matsum", "rcforc"], "dt": .1}, hourglass={"ihq": 1, "qh": .03})))
                assert not outcome.isError
                value = decoded(outcome)
                assert value["operation"] == "run_recipe" and value["status"] == "succeeded"
                assert value["data"]["recipe"]["reference_policy"] == "pinned"
                assert value["data"]["recipe"]["native_executed"] is False
    asyncio.run(asyncio.wait_for(scenario(), timeout=90))
