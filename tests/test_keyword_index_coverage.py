"""I05 complete-catalog enumeration and repeated field-column identities."""

import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import replace
from types import SimpleNamespace

import pytest

from ls_prepost_mcp.keyword_documentation import KeywordField, keyword_fields
from ls_prepost_mcp.knowledge_index import build_index, search_index
from tools.build_knowledge_index import main


def field(offset=0):
    return KeywordField("*REPEATED_TEST", None, 1, "var", offset, 10, "Array component", [], None,
                        dict(evidence="documented"), "MIT", "fixture")


def test_same_name_in_distinct_columns_remains_two_searchable_records(tmp_path):
    path = tmp_path / "index.sqlite"
    result = build_index(path, [], [field(), field(10)])
    assert result["keyword_fields"] == 2
    rows = search_index(path, "REPEATED_TEST", category="keyword")
    assert len(rows) == 2 and len({row["locator"] for row in rows}) == 2
    assert {row["keyword_field"]["offset"] for row in rows} == {0, 10}
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT schema_version FROM metadata").fetchone()[0] == 2


def test_same_slot_conflicting_definition_still_rejects_publication(tmp_path):
    path = tmp_path / "index.sqlite"
    with pytest.raises(ValueError, match="conflicting field identities"):
        build_index(path, [], [field(), replace(field(), help="A contradictory meaning")])
    assert not path.exists()


def test_complete_provider_reports_fieldless_keywords_and_deduplicates_requests():
    calls = []

    def doc(key):
        calls.append(key)
        if key == "*NO_FIELDS":
            return dict(cards=[])
        return dict(keyword=key, cards=[dict(card=1, option=None,
                    fields=[dict(name="var", columns="1-10", help="first"),
                            dict(name="var", columns="11-20", help="second")])],
                    references=[], evidence="documented", source=dict(fields="fixture"))

    provider = SimpleNamespace(keywords=lambda: ["*REPEATED_TEST", "*NO_FIELDS", "*REPEATED_TEST"],
                               keyword_doc=doc, manual_field_text=lambda *args: None)
    coverage = {}
    fields = list(keyword_fields(provider=provider, coverage=coverage))
    assert len(fields) == 2 and calls == ["*REPEATED_TEST", "*NO_FIELDS"]
    assert coverage == dict(requested_keywords=2, completed_keywords=2,
                            field_records=2, without_fields=["*NO_FIELDS"])


def test_provider_failure_does_not_claim_catalog_complete():
    def broken(key):
        if key == "*BROKEN":
            raise RuntimeError("schema unavailable")
        return dict(cards=[])

    coverage = {}
    provider = SimpleNamespace(keywords=lambda: ["*OK", "*BROKEN"], keyword_doc=broken)
    with pytest.raises(RuntimeError, match="schema unavailable"):
        list(keyword_fields(provider=provider, coverage=coverage))
    assert coverage["requested_keywords"] == 2 and coverage["completed_keywords"] == 1


def test_all_keyword_cli_uses_integrated_provider_and_emits_coverage(tmp_path, monkeypatch, capsys):
    path = tmp_path / "index.sqlite"
    monkeypatch.setattr(sys, "argv", ["build_knowledge_index", "--all-keywords", "--output", str(path)])
    monkeypatch.setattr("tools.build_knowledge_index.repository_documents", lambda: [])

    def integrated(keywords, *, coverage):
        assert keywords is None
        coverage.update(requested_keywords=1, completed_keywords=1, field_records=2, without_fields=[])
        yield field()
        yield field(10)

    monkeypatch.setattr("tools.build_knowledge_index.keyword_fields", integrated)
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["keyword_fields"] == 2 and result["keyword_coverage"]["completed_keywords"] == 1


def test_all_keyword_cli_cannot_silently_publish_after_provider_failure(tmp_path, monkeypatch):
    path = tmp_path / "index.sqlite"
    monkeypatch.setattr(sys, "argv", ["build_knowledge_index", "--all-keywords", "--output", str(path)])
    monkeypatch.setattr("tools.build_knowledge_index.repository_documents", lambda: [])

    def broken(*args, **kwargs):
        yield field()
        raise RuntimeError("provider failed halfway")

    monkeypatch.setattr("tools.build_knowledge_index.keyword_fields", broken)
    with pytest.raises(RuntimeError, match="halfway"):
        main()
    assert not path.exists()


def test_keyword_selection_and_complete_catalog_are_mutually_exclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["build_knowledge_index", "--output", str(tmp_path / "index.sqlite"),
                                      "--all-keywords", "--keyword", "*PART"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
