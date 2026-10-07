"""A10 cross-language retrieval; general glossary only, never evaluation questions."""
import json
from pathlib import Path

from ls_prepost_mcp.knowledge_index import Document, build_index, glossary, plan_query, search_index

DATA = Path(__file__).parent / "data"


def doc(title, text, category="command"):
    return Document("test:" + title, category, title, text, "test://" + title, "MIT", "public")


def test_chinese_query_reaches_english_reference_and_reports_expansion(tmp_path):
    path = tmp_path / "index.sqlite"
    build_index(path, [doc("rz", "Rotate model about global z axis"), doc("wire", "Display model in wire mode")])
    rows = search_index(path, "如何旋转模型")
    assert [row["title"] for row in rows] == ["rz", "wire"]
    assert {"term": "旋转", "english": ["rotate", "rotation"]} in rows[0]["query_expansion"]
    assert rows[0]["query_match"] == "text_only"


def test_more_matched_concepts_rank_before_bm25(tmp_path):
    path = tmp_path / "index.sqlite"
    build_index(path, [doc("one", "background " * 5), doc("two", "Change background color to white")])
    assert [row["title"] for row in search_index(path, "背景改成白色")] == ["two", "one"]


def test_english_inflections_match_but_identifiers_stay_literal(tmp_path):
    path = tmp_path / "index.sqlite"
    build_index(path, [doc("plural", "Select nodes by box"), doc("code", "value73 runtime42")])
    assert search_index(path, "select node")[0]["title"] == "plural"
    assert search_index(path, "selecting the nodes")[0]["title"] == "plural"
    assert search_index(path, "value7") == [] and search_index(path, "runtime4") == []


def test_explicit_keyword_outranks_prefix_siblings(tmp_path):
    path = tmp_path / "index.sqlite"
    build_index(path, [doc("*MAT_ELASTIC_FLUID pr", "Poisson's ratio of the fluid model", "keyword"),
                       doc("*MAT_ELASTIC pr", "Poisson ratio", "keyword")])
    rows = search_index(path, "*MAT_ELASTIC 泊松比", category="keyword")
    assert [row["title"] for row in rows] == ["*MAT_ELASTIC pr", "*MAT_ELASTIC_FLUID pr"]
    assert rows[0]["query_match"] == "both"


def test_snippet_centres_on_expanded_terms(tmp_path):
    path = tmp_path / "index.sqlite"
    text = "filler " * 300 + "Shrink Factor\nInput shrink factor."
    build_index(path, [doc("guide", text, "user_guide")])
    assert "Shrink Factor" in search_index(path, "收缩因子在哪里设置")[0]["snippet"]


def test_stopwords_alone_still_fall_back_to_raw_chinese(tmp_path):
    path = tmp_path / "index.sqlite"
    build_index(path, [doc("issue", "为什么这样", "known_issue")])
    assert search_index(path, "为什么")[0]["title"] == "issue"
    assert plan_query("为什么")["expansion"] == []


def test_glossary_is_general_and_disjoint_from_evaluation_questions():
    entries, stopwords = glossary()
    assert len(entries) >= 200 and not set(entries) & stopwords
    assert all(values and all(isinstance(value, str) and value.strip() for value in values) for values in entries.values())
    queries = {row["query"] for name in ("knowledge_queries.json", "knowledge_dev_queries.json",
                                         "knowledge_holdout_queries.json", "knowledge_holdout_b_queries.json")
               for row in json.loads((DATA / name).read_text(encoding="utf8"))}
    assert not set(entries) & queries


def test_tuning_and_holdout_sets_are_disjoint_and_cover_six_categories():
    sets = {name: json.loads((DATA / name).read_text(encoding="utf8"))
            for name in ("knowledge_dev_queries.json", "knowledge_holdout_b_queries.json")}
    tuned = {row["query"] for name in ("knowledge_queries.json", "knowledge_dev_queries.json")
             for row in json.loads((DATA / name).read_text(encoding="utf8"))}
    held = {row["query"] for name in ("knowledge_holdout_queries.json", "knowledge_holdout_b_queries.json")
            for row in json.loads((DATA / name).read_text(encoding="utf8"))}
    assert not tuned & held
    for rows in sets.values():
        assert len(rows) >= 20 and len({row["id"] for row in rows}) == len(rows)
        assert {row["category"] for row in rows} == {"command", "api", "keyword", "user_guide", "recipe", "known_issue"}
        assert all(any(key in row for key in ("title", "locator", "text", "field")) for row in rows)
