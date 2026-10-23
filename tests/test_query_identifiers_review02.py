"""Review02 I05: source and query identifiers share boundaries, without eval tuning."""
import sqlite3
from contextlib import closing

import pytest

from ls_prepost_mcp.knowledge_index import Document, _api_terms, build_index, search_index


@pytest.mark.parametrize("query", ["GetDataCenterFloatArray", "GetDataCenter", "SCLGetData", "node ids", "SCL_GetData"])
def test_partial_or_spaced_identifier_finds_the_documented_api(tmp_path, query):
    path = tmp_path / "index.sqlite"
    text = "SCLGetDataCenterFloatArray GetNodeIDs"
    build_index(path, [Document("api", "api", "API reference", text, "test://api", "MIT", "public")])
    rows = search_index(path, query)
    assert rows and rows[0]["title"] == "API reference"
    assert rows[0]["snippet"] == text


def test_underscore_split_and_plural_acronym_do_not_create_fragment_tokens():
    tokens = _api_terms("SCL_GetData GetNodeIDs")
    assert "scl_get" not in tokens and "ds" not in tokens
    assert {"scl", "get", "data", "node", "ids"} <= set(tokens)


def test_full_identifier_is_an_alternative_to_all_parts_not_an_extra_requirement(tmp_path):
    path = tmp_path / "index.sqlite"
    docs = [Document(str(n), "command", str(n), text, "test://" + str(n), "MIT", "public")
            for n, text in enumerate(["GetDataCenter", "get data center", "get data", "get center", "data center"])]
    build_index(path, docs)
    assert {r["title"] for r in search_index(path, "GetDataCenter")} == {"0", "1"}
    assert search_index(path, "GetDataCenter missing") == []


@pytest.mark.parametrize("query", ['"node', 'NEAR(node shell)', 'node* -shell', "a'b", '节点"OR"壳'])
def test_fts_punctuation_is_literal_data_and_cannot_change_visibility(tmp_path, query):
    path = tmp_path / "index.sqlite"
    build_index(path, [Document("public", "api", "node shell a b 节点 壳", "node shell", "test://public", "MIT", "public"),
                       Document("secret", "api", "node shell a b 节点 壳", "node shell", "local://secret", "copyright")])
    rows = search_index(path, query)
    assert all(r["visibility"] == "public" for r in rows)


def test_legacy_index_returns_tokenization_and_rebuild_warning_without_writing(tmp_path, caplog):
    path = tmp_path / "legacy.sqlite"
    build_index(path, [Document("api", "api", "node", "GetNodeIDs", "test://api", "MIT", "public")])
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("ALTER TABLE metadata DROP COLUMN api_tokenization")
    before = path.read_bytes()
    rows = search_index(path, "node")
    assert rows[0].get("index_tokenization") == "legacy"
    assert any("rebuild" in warning.lower() for warning in rows[0].get("warnings", []))
    assert "rebuild" in caplog.text.lower()
    assert path.read_bytes() == before
