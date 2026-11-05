"""A10 artifact checks catch stale lists, not merely unchanged aggregate hit counts."""
from copy import deepcopy

import pytest

from tools import evaluate_knowledge as evaluator

CASES=[dict(id="S01",category="command",query="synthetic query",title="intended")]


def fixture_report():
    return dict(queries=1,hits_at_3=1,include_private=False,results=[dict(
        id="S01",category="command",query="synthetic query",hit_at_3=True,first_correct_rank=2,
        returned=[dict(id="first",source_id="fixture",version="one",evidence_level="documented",
                       position=1,score=-2.,matched_expected=False,
                       reference=dict(category="command",source_id="fixture",locator="test://other",title="other")),
                  dict(id="second",source_id="fixture",version="one",evidence_level="documented",
                       position=2,score=-1.,matched_expected=True,
                       reference=dict(category="command",source_id="fixture",locator="test://intended",title="intended"))])])


def test_evaluate_exports_observed_ranks_and_public_stable_references(monkeypatch):
    row=dict(id="observed",source_id="fixture",version="one",evidence_level="documented",rank=-.25,
             private=False,category="command",title="intended",locator="test://intended",snippet="",sha256="a"*64)
    monkeypatch.setattr(evaluator,"search_docs",lambda *a,**kw:[row])
    report=evaluator.evaluate(CASES)
    result=report["results"][0]["returned"][0]
    assert result["score"]==-.25 and result["position"]==1 and result["matched_expected"]
    assert result["reference"]==dict(source_id="fixture",category="command",title="intended",locator="test://intended")
    assert result["text_sha256"]=="a"*64


def test_original_matching_still_requires_every_selector():
    case=dict(title="target",locator="test://one",field="value",text="needed")
    row=dict(title="target",locator="test://one",snippet="needed",keyword_field=dict(field="value"))
    assert evaluator.expected_match(case,row)
    assert not evaluator.expected_match(case,{**row,"keyword_field":dict(field="wrong")})


def test_artifact_validation_does_not_trust_a_corrupt_match_boolean():
    report=fixture_report()
    report["results"][0]["returned"][0]["matched_expected"]=True
    report["results"][0]["first_correct_rank"]=1
    with pytest.raises(ValueError,match="selectors"):
        evaluator.validate_evaluation(report,CASES)


def test_top_three_change_is_stale_even_with_the_same_hit_count():
    stored=fixture_report()
    fresh=deepcopy(stored)
    fresh["results"][0]["returned"][0]["reference"]["locator"]="test://different"
    with pytest.raises(ValueError,match="stale"):
        evaluator.check_replay(stored,fresh)


def test_score_change_is_not_hidden_by_equal_document_ids():
    stored=fixture_report()
    fresh=deepcopy(stored)
    fresh["results"][0]["returned"][0]["score"]=-.1
    with pytest.raises(ValueError,match="stale"):
        evaluator.check_replay(stored,fresh)


def test_evidence_grade_change_is_not_hidden_by_equal_document_ids():
    stored=fixture_report()
    fresh=deepcopy(stored)
    fresh["results"][0]["returned"][0]["evidence_level"]="source_example"
    with pytest.raises(ValueError,match="provenance"):
        evaluator.check_replay(stored,fresh)


def test_content_id_change_is_separate_from_stable_location_change():
    stored=fixture_report()
    fresh=deepcopy(stored)
    fresh["results"][0]["returned"][0]["id"]="rebuilt-content-id"
    change=evaluator.compare_replays(stored,fresh)[0]
    assert change["raw_doc_ids_changed"]
    assert change["stable_top3_changed"] is False and change["score_changed"] is False


def test_missing_historical_reference_is_explicit_instead_of_guessed():
    stored=fixture_report()
    fresh=deepcopy(stored)
    del stored["results"][0]["returned"][0]["reference"]
    change=evaluator.compare_replays(stored,fresh)[0]
    assert change["historical_references_unresolved"]==1
    assert change["stable_top3_changed"] is None


def test_report_and_json_cannot_silently_disagree():
    report=fixture_report()
    expected=("# A10 frozen-case replay\n\nTop-3 hits: 1/1\n\n"
              "| Query ID | Category | Hit | First correct rank | Top-three public references (BM25 score) | 有效性 |\n"
              "|---|---|---|---:|---|---|\n"
              "| S01 | command | true | 2 | 1. other (-2)<br>2. intended (-1) | 登记修订/索引有效 |\n")
    assert evaluator.markdown_report(report)==expected
    evaluator.check_artifacts(report,CASES,expected)
    with pytest.raises(ValueError,match="Markdown"):
        evaluator.check_artifacts(report,CASES,expected.replace("1/1","0/1"))
