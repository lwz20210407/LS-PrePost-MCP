"""I05 source-side identifier splitting, without changing queries or source text."""
import hashlib
import sqlite3
from contextlib import closing

import pytest

from ls_prepost_mcp.knowledge_index import Document, build_index, search_index, terms


@pytest.mark.parametrize("identifier,query", [
    ("SCLGetDataCenterFloatArray", "data center float array"),
    ("SCLSwitchStateTo", "switch state"),
    ("getUserNodeId", "user node id"),
    ("VTKFileReader", "vtk file reader"),
    ("XMLHTTPRequest", "xmlhttp request"),
])
def test_spaced_query_finds_api_identifier_without_rewriting_reference(tmp_path, identifier, query):
    path=tmp_path / "api.sqlite"
    text=identifier+"(arg);"
    doc=Document("reference", "api", identifier, text, "local://example#L4", "copyright", "private", "4.13", 4, 4)
    build_index(path, [doc])
    assert search_index(path, query, category="api")==[]
    rows=search_index(path, query, category="api", include_private=True)
    assert rows and rows[0]["title"]==identifier
    assert rows[0]["sha256"]==hashlib.sha256(text.encode()).hexdigest()
    assert rows[0]["locator"]==doc.locator and rows[0]["line_start"]==4
    assert search_index(path, identifier, category="api", include_private=True)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT text FROM documents").fetchone()[0]==text
        assert db.execute("SELECT api_tokenization FROM metadata").fetchone()[0]=="identifier-parts-v2"


def test_non_api_sources_keep_legacy_tokenization(tmp_path):
    path=tmp_path / "command.sqlite"
    doc=Document("command", "command", "title", "SCLGetDataCenterFloatArray", "test://one", "MIT", "public")
    build_index(path, [doc])
    with closing(sqlite3.connect(path)) as db:
        actual=db.execute("SELECT terms FROM search_terms").fetchone()[0]
    assert actual==" ".join(terms(doc.title+" "+doc.text))


def test_legacy_v2_index_remains_readable_and_is_never_implicitly_rewritten(tmp_path):
    path=tmp_path / "legacy.sqlite"
    doc=Document("reference", "api", "SCLSwitchStateTo", "SCLSwitchStateTo(3);", "test://one", "MIT", "public")
    build_index(path, [doc])
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE search_terms SET terms=?", (" ".join(terms(doc.title+" "+doc.text)),))
        columns=[r[1] for r in db.execute("PRAGMA table_info(metadata)")]
        if "api_tokenization" in columns:
            db.execute("ALTER TABLE metadata DROP COLUMN api_tokenization")
    before=path.read_bytes()
    assert search_index(path,"SCLSwitchStateTo")
    assert search_index(path,"switch state")==[]
    assert path.read_bytes()==before
