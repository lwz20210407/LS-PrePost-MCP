"""I05 complete-catalog enumeration and repeated field-column identities."""

import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import replace
from types import SimpleNamespace

import pytest

from ls_prepost_mcp.keyword_documentation import (
    KeywordField,
    KeywordWithoutFields,
    fieldless_review,
    keyword_fields,
    provider_structure,
)
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


def test_exact_duplicate_field_creates_one_field_and_one_document(tmp_path):
    path = tmp_path / "index.sqlite"
    result = build_index(path, [], [field(), field()])
    assert result["keyword_fields"] == 1
    assert result["documents"] == 1 and result["categories"] == {"keyword": 1}
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT count(*) FROM keyword_fields").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM documents WHERE category='keyword'").fetchone()[0] == 1


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
    assert coverage == dict(requested_keywords=2, completed_keywords=2, field_records=2,
                            without_fields=["*NO_FIELDS"], without_fields_verdicts={"unreviewed": 1},
                            without_fields_detail=[dict(entity_key="*NO_FIELDS", version="unspecified",
                                                        provider_structure="no_cards", card_kinds=[], review=None)])


@pytest.mark.parametrize(("kinds", "expected"), [
    ([], "no_cards"),
    (["Card"], "no_named_fields"),
    (["TextCard"], "free_text_card"),
    (["SeriesCard"], "series_layout_not_returned"),
    (["CardSet (engine layout of a generated card)"], "generated_layout_not_returned"),
    (["TableCardGroup"], "layout_not_returned"),
])
def test_fieldless_structure_comes_from_provider_card_kinds(kinds, expected):
    assert provider_structure([dict(kind=kind, fields=[]) for kind in kinds]) == expected


def test_reviewed_fieldless_keyword_carries_verdict_and_unreviewed_stays_unknown():
    docs = {"*PARAMETER": [dict(kind="SeriesCard", fields=[])], "*NEW_DIRECTIVE": [dict(kind="Card", fields=[])]}
    provider = SimpleNamespace(keywords=lambda: list(docs), manual_field_text=lambda *args: None,
                               keyword_doc=lambda key: dict(keyword=key, cards=docs[key], source=dict(fields="fixture")))
    coverage = {}
    assert list(keyword_fields(provider=provider, coverage=coverage)) == []
    detail = {row["entity_key"]: row for row in coverage["without_fields_detail"]}
    assert detail["*PARAMETER"]["review"]["verdict"] == "provider_layout_missing"
    assert detail["*PARAMETER"]["provider_structure"] == "series_layout_not_returned"
    assert detail["*NEW_DIRECTIVE"]["review"] is None
    assert coverage["without_fields_verdicts"] == {"provider_layout_missing": 1, "unreviewed": 1}


def test_review_file_classifies_every_entry_without_manual_text():
    review = fieldless_review()
    counts = {}
    for key, entry in review["keywords"].items():
        assert key.startswith("*") and entry["verdict"] in review["verdicts"] and entry["basis"]
        assert set(entry) <= {"verdict", "basis", "note"} and len(entry.get("note", "")) <= 120
        counts[entry["verdict"]] = counts.get(entry["verdict"], 0) + 1
    assert counts == {"no_data_card": 23, "free_text": 1, "provider_layout_missing": 10, "unconfirmed": 4}


def test_reviewed_entries_still_match_the_integrated_provider():
    pytest.importorskip("ansys.dyna.core")
    from ls_prepost_mcp.keyword_documentation import documentation_provider

    review = fieldless_review()["keywords"]
    coverage = {}
    assert list(keyword_fields(list(review), documentation_provider(), coverage=coverage)) == []
    assert coverage["without_fields"] == list(review)
    for row in coverage["without_fields_detail"]:
        verdict = review[row["entity_key"]]["verdict"]
        if verdict == "no_data_card":
            assert row["provider_structure"] in ("no_cards", "no_named_fields")
        elif verdict == "free_text":
            assert row["provider_structure"] == "free_text_card"


def fieldless(key="*CONTROL_MPP_IO_NODUMP", structure="no_named_fields"):
    return KeywordWithoutFields(key, "fixture", structure, ["Card"], fieldless_review()["keywords"].get(key))


def test_fieldless_keywords_are_public_searchable_keyword_documents(tmp_path):
    path = tmp_path / "index.sqlite"
    result = build_index(path, [], [field()], [fieldless(), fieldless("*PARAMETER", "series_layout_not_returned")])
    assert result["keywords_without_fields"] == 2 and result["categories"] == {"keyword": 3}
    rows = search_index(path, "CONTROL_MPP_IO_NODUMP", category="keyword")
    assert len(rows) == 1 and rows[0]["locator"] == "keyword_docs://*CONTROL_MPP_IO_NODUMP"
    assert rows[0]["visibility"] == "public" and "no_data_card" in rows[0]["snippet"]
    with closing(sqlite3.connect(path)) as db:
        stored = dict(db.execute("SELECT entity_key, verdict FROM keyword_without_fields").fetchall())
    assert stored == {"*CONTROL_MPP_IO_NODUMP": "no_data_card", "*PARAMETER": "provider_layout_missing"}


def test_conflicting_fieldless_records_and_foreign_objects_reject_publication(tmp_path):
    path = tmp_path / "index.sqlite"
    with pytest.raises(ValueError, match="conflicting field-less"):
        build_index(path, [], [field()], [fieldless(), fieldless(structure="no_cards")])
    with pytest.raises(ValueError, match="adapter"):
        build_index(path, [], [field()], [dict(entity_key="*X")])
    with pytest.raises(ValueError, match="verdict"):
        KeywordWithoutFields("*X", "fixture", "no_cards", [], dict(verdict="looks_fine"))
    assert not path.exists()


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
        coverage.update(requested_keywords=2, completed_keywords=2, field_records=2, without_fields=["*COMMENT"],
                        without_fields_detail=[dict(entity_key="*COMMENT", version="fixture",
                                                    provider_structure="free_text_card", card_kinds=["TextCard"],
                                                    review=fieldless_review()["keywords"]["*COMMENT"])])
        yield field()
        yield field(10)

    monkeypatch.setattr("tools.build_knowledge_index.keyword_fields", integrated)
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["keyword_fields"] == 2 and result["keyword_coverage"]["completed_keywords"] == 2
    assert result["keywords_without_fields"] == 1
    assert search_index(path, "COMMENT", category="keyword")[0]["locator"] == "keyword_docs://*COMMENT"


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
