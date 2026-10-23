"""P1-10: a short query cannot schedule hundreds of coverage subqueries."""
import sqlite3

import ls_prepost_mcp.knowledge_index as index


def many_concepts(monkeypatch):
    terms = ["甲" + chr(0x4E00 + i) for i in range(200)]
    monkeypatch.setattr(index, "glossary", lambda: ({term: ["select"] for term in terms}, set()))
    query = "MPP " + " ".join(terms)
    assert len(query) < 1000
    return query


def document(n):
    return index.Document(f"budget:{n}", "command", f"Doc {n}", "MPP select", f"test://budget/{n}", "MIT", "public")


def test_unique_concepts_are_bounded_and_truncation_is_explicit(monkeypatch):
    plan = index.plan_query(many_concepts(monkeypatch))
    assert len(plan["concepts"]) <= 32
    assert plan["concepts_truncated"] is True
    assert plan["concepts_total"] == 200 and plan["concept_limit"] == 32
    assert len(plan["expansion"]) <= 32  # explain only concepts actually searched


def test_search_hits_report_the_concept_budget(tmp_path, monkeypatch):
    query = many_concepts(monkeypatch)
    path = tmp_path / "index.sqlite"
    index.build_index(path, [document(0)])
    hits = index.search_index(path, query)
    assert hits and hits[0].get("concepts_truncated") is True
    assert hits[0]["concepts_total"] == 200 and hits[0]["concepts_used"] == 32


def test_duplicate_concepts_do_not_consume_the_distinct_budget(monkeypatch):
    many_concepts(monkeypatch)
    short = index.plan_query("MPP 甲一")
    repeated = index.plan_query("MPP " + "甲一 " * 200)
    assert repeated["concepts"] == short["concepts"]
    assert repeated.get("concepts_truncated") is False
    assert repeated["concepts_total"] == 1


def test_long_query_fits_a_bounded_sqlite_work_budget(tmp_path, monkeypatch):
    query = many_concepts(monkeypatch)
    path = tmp_path / "budget.sqlite"
    index.build_index(path, (document(n) for n in range(2000)))
    connect = sqlite3.connect
    steps = []

    def bounded_connect(*args, **kwargs):
        db = connect(*args, **kwargs)

        def progress():
            steps.append(1000)
            return sum(steps) >= 3_000_000

        db.set_progress_handler(progress, 1000)
        return db

    monkeypatch.setattr(index.sqlite3, "connect", bounded_connect)
    # An instruction budget is reproducible across fast/slow CI hosts. A
    # separate external 30k-document benchmark records wall time, not a flaky
    # sleep/elapsed threshold in the test suite.
    hits = index.search_index(path, query, limit=1)
    assert hits and sum(steps) < 3_000_000
