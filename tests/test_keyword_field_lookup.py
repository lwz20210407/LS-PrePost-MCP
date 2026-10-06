"""A10: structured field requests must not depend on prose ranking."""

import sqlite3
from contextlib import closing
from dataclasses import replace

import pytest

from ls_prepost_mcp.keyword_documentation import KeywordField
from ls_prepost_mcp.knowledge import keyword_fields
from ls_prepost_mcp.knowledge_index import build_index


def record(key="*SYNTH_COMPONENT", name="target", offset=0, card=0, **changes):
    base = KeywordField(key, None, card, name, offset, 10, "A field description " * 100, [], None,
                        dict(evidence="documented"), "MIT", "synthetic fixture")
    return replace(base, **changes)


def index(tmp_path, monkeypatch, records):
    path = tmp_path / "index.sqlite"
    build_index(path, [], records)
    monkeypatch.setenv("LSPP_KNOWLEDGE_INDEX", str(path))
    return path


def test_old_schema_v2_without_lookup_index_remains_readable(tmp_path, monkeypatch):
    path = index(tmp_path, monkeypatch, [record("*PREFIX-A"), record("*PREFIX/A"), record("*PREFIX_A")])
    with closing(sqlite3.connect(path)) as db, db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='keyword_lookup'").fetchone()
        db.execute("DROP INDEX keyword_lookup")
    for key in ("PREFIX-", "PREFIX/", "PREFIX_"):
        rows = keyword_fields(key)
        assert len(rows) == 1 and rows[0]["keyword_field"]["entity_key"] == "*" + key + "A"


def test_explicit_field_cannot_be_crowded_out_by_other_fields_help(tmp_path, monkeypatch):
    # terms() deduplicates words: repeated prose alone does not make a long FTS
    # document. Use distinct context words to expose the old LIMIT-before-filter.
    long_help = " ".join("explanation_" + str(i) for i in range(600))
    index(tmp_path, monkeypatch, [record(help=long_help), *[
        record(name="other_" + str(i), help="target " * 100) for i in range(60)]])
    rows = keyword_fields("SYNTH_COMPONENT", "target", limit=1)
    assert len(rows) == 1 and rows[0]["keyword_field"]["field"] == "target"
    assert rows[0]["evidence_level"] == "documented" and rows[0]["version"] == "synthetic fixture"
    assert "line_start" not in rows[0] and rows[0]["query_expansion"] == []


def test_literal_prefix_and_exact_keyword_priority_before_limit(tmp_path, monkeypatch):
    index(tmp_path, monkeypatch, [record(), record("*SYNTH_COMPONENT_EXTRA", help="target"),
                                  record("*SYNTHXCOMPONENT", help="target")])
    assert keyword_fields("synth_component", "TARGET", limit=1)[0]["keyword_field"]["entity_key"] == "*SYNTH_COMPONENT"
    assert {r["keyword_field"]["entity_key"] for r in keyword_fields("SYNTH_COMPONENT", "target")} == {
        "*SYNTH_COMPONENT", "*SYNTH_COMPONENT_EXTRA"}


def test_alias_filters_before_limit_and_retains_attributed_verification(tmp_path, monkeypatch):
    index(tmp_path, monkeypatch, [record(name="renamed", aliases=["old_name"],
        solver_status=dict(evidence="verified", attribution="test provider", detail="Card check only")),
        record(name="distractor", help="old_name")])
    row = keyword_fields("SYNTH_COMPONENT", "OLD_NAME", limit=1)[0]
    assert row["keyword_field"]["field"] == "renamed" and row["evidence_level"] == "native_verified"
    assert row["verification_attribution"] == "test provider"
    assert "not verification of every field" in row["evidence_scope"]


def test_private_filter_precedes_exact_preference_and_limit(tmp_path, monkeypatch):
    index(tmp_path, monkeypatch, [record(manual_ref={"note": "private fixture"}, license="restricted_manual"),
                                  record("*SYNTH_COMPONENT_EXTRA")])
    public = keyword_fields("SYNTH_COMPONENT", "target", limit=1)
    assert len(public) == 1 and public[0]["private"] is False
    assert public[0]["keyword_field"]["entity_key"] == "*SYNTH_COMPONENT_EXTRA"
    private = keyword_fields("SYNTH_COMPONENT", "target", limit=1, include_private=True)
    assert len(private) == 1 and private[0]["private"] is True
    assert private[0]["keyword_field"]["entity_key"] == "*SYNTH_COMPONENT"


def test_card_and_column_order_retains_repeated_fields(tmp_path, monkeypatch):
    index(tmp_path, monkeypatch, [record(offset=20, card=10), record(offset=10, card=2),
                                  record(offset=0, card=2), record(card="engine:LOCAL", option="LOCAL")])
    rows = keyword_fields("SYNTH_COMPONENT")
    assert [(r["keyword_field"]["card"], r["keyword_field"]["offset"]) for r in rows] == [
        (2, 0), (2, 10), (10, 20), ("engine:LOCAL", 0)]
    assert keyword_fields("SYNTH_COMPONENT", "absent") == []


@pytest.mark.parametrize("arguments", [dict(keyword=None), dict(keyword="SYNTH%"),
    dict(keyword="SYNTH", field="x' OR 1=1"), dict(keyword="SYNTH", field=1),
    dict(keyword="SYNTH", limit=True), dict(keyword="SYNTH", limit=51),
    dict(keyword="SYNTH", include_private="yes")])
def test_lookup_rejects_invalid_or_injected_inputs(tmp_path, monkeypatch, arguments):
    index(tmp_path, monkeypatch, [record()])
    with pytest.raises(ValueError):
        keyword_fields(**arguments)
