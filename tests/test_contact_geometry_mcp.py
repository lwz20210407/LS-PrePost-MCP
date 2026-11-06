"""P06 real stdio contracts plus validation that needs no optional PyDYNA SDK."""
import asyncio
import builtins
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ls_prepost_mcp.domain.model import KeywordDeck, contact_report, operations

ROOT = Path(__file__).resolve().parents[1]

# Run the actual server entrypoint with test-owned tripwires. Any attempt to
# obtain a native executable or launch another process leaves a durable marker
# and fails, including attempts that production code might catch internally.
HOST_ONLY_SERVER = '''\
import os
import subprocess
from pathlib import Path
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.server import main

def forbidden_native(*args, **kwargs):
    Path(os.environ["P06_NATIVE_ATTEMPT"]).write_text("native/process launch attempted", encoding="utf-8")
    raise AssertionError("P06 geometry must not invoke native execution")

Settings.native_executable = forbidden_native
subprocess.Popen = forbidden_native
main()
'''


def _decoded(result):
    assert not result.isError, result.model_dump(mode="json")
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(next(block.text for block in result.content if block.type == "text"))


def _tetrahedron(path):
    xyz = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (.8, .8, .8), (.1, .1, .1)]
    rows = ["*KEYWORD", "*PART", "tetrahedron", "         1         1         1",
            "*SECTION_SOLID", "         1         1", "*MAT_ELASTIC", "         1         1         1       0.3", "*NODE"]
    rows += [f"{index:>8}" + "".join(f"{float(value):>16g}" for value in point)
             for index, point in enumerate(xyz, 1)]
    rows += ["*ELEMENT_SOLID", "".join(f"{value:>8}" for value in (1, 1, 1, 2, 3, 4, 4, 4, 4, 4)),
             "*SET_NODE_LIST", "         9", "         5         6",
             "*CONTACT_AUTOMATIC_NODES_TO_SURFACE", "         9         1         4         3", "", "", "*END"]
    path.write_bytes(("\n".join(rows) + "\n").encode("ascii"))


@pytest.mark.parametrize("profile", ["full", "compact"])
def test_contact_geometry_schema_and_coverage_cross_real_stdio(tmp_path, profile):
    # Only the actual geometry calls need this optional SDK. Validation tests
    # below remain collected and run in the minimal dependency environment.
    pytest.importorskip("ansys.dyna.core")
    source = tmp_path / "source.k"
    _tetrahedron(source)
    original = source.read_bytes()
    launcher = tmp_path / "host_only_server.py"
    launcher.write_text(HOST_ONLY_SERVER, encoding="utf-8")
    native_attempt = tmp_path / "native-attempt.txt"
    workspace = tmp_path / "work"

    async def scenario():
        environment = dict(os.environ, PYTHONPATH=os.pathsep.join((str(ROOT / "src"), str(ROOT))),
                           PYTHONDONTWRITEBYTECODE="1", LSPP_WORKSPACE=str(workspace),
                           LSPP_ALLOWED_ROOTS=str(tmp_path), LSPP_TOOL_PROFILE=profile,
                           P06_NATIVE_ATTEMPT=str(native_attempt))
        for key in ("LSPP_EXECUTABLE", "LSPP_EXECUTABLES", "LSPP_ENGINE_EXECUTABLE"):
            environment.pop(key, None)
        config = StdioServerParameters(command=sys.executable, args=["-B", str(launcher)], env=environment,
                                       cwd=str(tmp_path))
        async with stdio_client(config) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                catalog = {tool.name: tool for tool in (await session.list_tools()).tools}
                if profile == "full":
                    schema = catalog["check_model"].inputSchema
                else:
                    assert set(catalog) == {"lspp_find_operations", "lspp_describe_operation", "lspp_run_operation"}
                    described = _decoded(await session.call_tool("lspp_describe_operation", {"operation": "check_model"}))
                    assert described["execution"] == described["route"] == "direct"
                    schema = described["input_schema"]
                field = schema["properties"]["contact_geometry"]
                assert field["default"] is None
                assert {row["type"] for row in field["anyOf"]} == {"object", "null"}
                assert "contact_geometry" not in schema.get("required", [])

                async def check(arguments):
                    if profile == "full":
                        return _decoded(await session.call_tool("check_model", arguments))
                    return _decoded(await session.call_tool("lspp_run_operation", {
                        "operation": "check_model", "execution": "direct", "arguments": arguments}))

                default = await check({"model": str(source)})
                explicit_none = await check({"model": str(source), "contact_geometry": None})
                assert default == explicit_none
                assert default["status"] == "succeeded"
                assert "contact_geometry" not in default["data"]
                assert "contact_geometry_coverage" not in {row["name"] for row in default["checks"]}
                budgeted = await check({"model": str(source), "contact_geometry": {"max_pairs": 1}})
                assert budgeted["status"] == "succeeded"
                assert budgeted["data"]["complete"] is False
                geometry = budgeted["data"]["contact_geometry"]
                assert geometry["method"] == "keyword_triangle_gap" and geometry["native_verified"] is False
                assert geometry["coverage"]["evaluated_contacts"] == 0
                assert geometry["coverage"]["not_checked_contacts"] == 1
                assert geometry["coverage"]["complete"] is False
                assert "max_pairs" in geometry["not_checked"][0]["reason"]
                checks = {row["name"]: row for row in budgeted["checks"]}
                assert checks["all_blocks_read"]["status"] == "passed"
                assert checks["contact_geometry_coverage"]["status"] == "missing"
                assert checks["contact_geometry_coverage"]["required"] is False
                assert checks["contact_geometry_coverage"]["source_path"] == ["data", "contact_geometry", "coverage"]
                assert budgeted["data"]["errors"] == default["data"]["errors"]
                assert [row for row in budgeted["checks"] if row["name"] != "contact_geometry_coverage"] == default["checks"]
        assert source.read_bytes() == original
        assert not native_attempt.exists()
        assert not workspace.exists()
        transcript = {"profile": profile, "source_root": str(ROOT), "python": sys.executable,
                      "input_schema": schema, "default": default, "explicit_none": explicit_none,
                      "budgeted": budgeted, "native_attempted": native_attempt.exists(),
                      "source_before_sha256": hashlib.sha256(original).hexdigest(),
                      "source_after_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
        (tmp_path / "protocol-observations.json").write_text(json.dumps(transcript, indent=2), encoding="utf-8")

    asyncio.run(asyncio.wait_for(scenario(), timeout=90))


@pytest.mark.parametrize("options", [True, [], {"unknown": 1}, {"tolerance": True}, {"tolerance": float("nan")},
    {"tolerance": float("inf")}, {"max_pairs": True}, {"max_pairs": 0}, {"max_pairs": 1_000_001}, {"max_report": 51}])
def test_contact_geometry_options_reject_before_deck_or_sdk_access(monkeypatch, options):
    real_import = builtins.__import__

    def forbid_sdk(name, *args, **kwargs):
        if name == "ansys" or name.startswith("ansys."):
            pytest.fail("Option validation must not require the optional PyDYNA SDK")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", forbid_sdk)
    monkeypatch.setattr(KeywordDeck, "load", lambda *a, **kw: pytest.fail("Invalid options must precede deck loading"))
    with pytest.raises(ValueError, match="contact_geometry"):
        operations.check_deck("not-read.k", contact_geometry=options)


def test_contact_geometry_none_and_mesh_conflict_need_no_optional_sdk(monkeypatch):
    assert contact_report.options(None, include_mesh=False) is None
    monkeypatch.setattr(KeywordDeck, "load", lambda *a, **kw: pytest.fail("Conflicting options must precede deck loading"))
    with pytest.raises(ValueError, match="requires include_mesh=True"):
        operations.check_deck("not-read.k", include_mesh=False, contact_geometry={})
