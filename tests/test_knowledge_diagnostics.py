"""I05 diagnostics survive empty results without becoming reference hits."""
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest
from jsonschema import validate
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.knowledge import search_docs, search_knowledge
from ls_prepost_mcp.knowledge_index import API_TOKENIZATION, Document, build_index, search_index
from ls_prepost_mcp.server import build_server


def reference_index(tmp_path, *, legacy):
    path = tmp_path / "references.sqlite"
    build_index(path, [
        Document("public", "command", "open keyword", "Read a keyword deck", "repo://commands", "MIT", "public", "catalog"),
        Document("private", "api", "PrivateOnlyMarker", "PrivateDetailMustStayHidden", "local://private", "copyright", "private", "4.13"),
    ])
    if legacy:
        with sqlite3.connect(path) as db:
            db.execute("DROP TABLE metadata")
            db.execute("CREATE TABLE metadata (schema_version INTEGER)")
            db.execute("INSERT INTO metadata VALUES (2)")
    return path


@pytest.mark.parametrize("entrypoint", ["index", "docs", "knowledge"])
def test_empty_legacy_result_remains_a_list_with_diagnostics(tmp_path, monkeypatch, entrypoint):
    path = reference_index(tmp_path, legacy=True)
    monkeypatch.setenv("LSPP_KNOWLEDGE_INDEX", str(path))
    functions = {"index": lambda: search_index(path, "AbsentFunction937"),
                 "docs": lambda: search_docs("AbsentFunction937"),
                 "knowledge": lambda: search_knowledge("AbsentFunction937")}
    result = functions[entrypoint]()
    assert isinstance(result, list) and result == [] and json.dumps(result) == "[]"
    assert result.diagnostics["index_tokenization"] == "legacy"
    assert result.diagnostics["expected_index_tokenization"] == API_TOKENIZATION
    assert any("rebuild" in warning for warning in result.diagnostics["warnings"])


def test_current_empty_index_has_metadata_without_a_false_warning(tmp_path, monkeypatch):
    path = reference_index(tmp_path, legacy=False)
    monkeypatch.setenv("LSPP_KNOWLEDGE_INDEX", str(path))
    result = search_docs("AbsentFunction937")
    assert result == []
    assert result.diagnostics["index_tokenization"] == API_TOKENIZATION
    assert result.diagnostics["warnings"] == []


def test_unsearchable_input_does_not_claim_to_have_inspected_an_index(tmp_path):
    result = search_index(tmp_path / "does-not-exist.sqlite", "!!!")
    assert result == [] and result.diagnostics["search_executed"] is False
    assert result.diagnostics["index_tokenization"] is None
    assert result.diagnostics["warnings"] == []


def test_diagnostics_and_rows_share_one_readonly_connection_snapshot(tmp_path, monkeypatch):
    path = reference_index(tmp_path, legacy=True)
    connect = sqlite3.connect
    connections, statements = [], []

    def observed(*args, **kwargs):
        connections.append((args, kwargs))
        db = connect(*args, **kwargs)
        db.set_trace_callback(statements.append)
        return db

    monkeypatch.setattr("ls_prepost_mcp.knowledge_index.sqlite3.connect", observed)
    result = search_index(path, "open keyword")
    assert len(result) == 1 and result[0]["source_id"] == "public"
    assert result.diagnostics["index_tokenization"] == "legacy"
    assert len(connections) == 1 and "mode=ro" in connections[0][0][0]
    assert statements[0] == "BEGIN"


@pytest.mark.parametrize("profile", ["full", "compact"])
@pytest.mark.parametrize("legacy", [True, False])
def test_stdio_empty_query_returns_diagnostics_without_private_content(tmp_path, profile, legacy):
    path = reference_index(tmp_path, legacy=legacy)

    async def scenario():
        env = dict(os.environ, LSPP_WORKSPACE=str(tmp_path / "workspace"),
                   LSPP_KNOWLEDGE_INDEX=str(path), LSPP_TOOL_PROFILE=profile,
                   PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        config = StdioServerParameters(command=sys.executable,
                                       args=["-B", "-m", "ls_prepost_mcp.server"], env=env)
        async with stdio_client(config) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                arguments = dict(query="PrivateOnlyMarker", category="api")
                if profile == "full":
                    result = await session.call_tool("search_docs", arguments)
                else:
                    result = await session.call_tool("lspp_run_operation", dict(
                        operation="search_docs", execution="direct", arguments=arguments))
                assert not result.isError
                assert result.structuredContent is not None
                assert result.structuredContent["result"] == []
                metadata = result.structuredContent["diagnostics"]
                assert metadata["schema_version"] == 2
                assert metadata["index_tokenization"] == ("legacy" if legacy else API_TOKENIZATION)
                if legacy:
                    assert any("rebuild" in warning for warning in metadata["warnings"])
                else:
                    assert metadata["warnings"] == []
                serialized = result.model_dump_json()
                assert "PrivateOnlyMarker" not in serialized
                assert "PrivateDetailMustStayHidden" not in serialized
                assert path.name not in serialized and tmp_path.name not in serialized
                assert any("diagnostics" in c.text for c in result.content if c.type == "text")

    asyncio.run(asyncio.wait_for(scenario(), timeout=90))


def test_nonempty_mcp_results_keep_hit_rows_and_the_advertised_output_schema(tmp_path, monkeypatch):
    path = reference_index(tmp_path, legacy=True)
    monkeypatch.setenv("LSPP_KNOWLEDGE_INDEX", str(path))
    rows = search_docs("open keyword")
    server = build_server(Settings(tmp_path / "workspace"))
    specification = next(t for t in asyncio.run(server.list_tools()) if t.name == "search_docs")
    result = asyncio.run(server.call_tool("search_docs", dict(query="open keyword")))
    validate(result.structuredContent, specification.outputSchema)
    assert result.structuredContent["result"] == list(rows)
    blocks = [json.loads(block.text) for block in result.content if block.type == "text"]
    assert blocks == list(rows)
    assert result.structuredContent["diagnostics"]["index_tokenization"] == "legacy"
