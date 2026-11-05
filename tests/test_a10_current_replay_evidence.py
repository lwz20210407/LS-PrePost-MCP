"""Validate the public historical replay without freezing stale aggregate scores."""

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from tools.refresh_knowledge_evidence import SETS, validate_suite

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/decisions/evidence/a10-replay-refresh"


def artifacts():
    evidence = json.loads((EVIDENCE / "evidence.json").read_text(encoding="utf8"))
    markdown = (EVIDENCE / "summary.md").read_text(encoding="utf8")
    tables = {key: (EVIDENCE / (key + "-top3.md")).read_text(encoding="utf8") for key in SETS}
    return evidence, markdown, tables


def test_current_public_replay_artifacts_and_frozen_questions_are_consistent():
    evidence, markdown, tables = artifacts()
    validate_suite(evidence, markdown, tables)
    assert evidence["status"] == "partial" and evidence["verification_level"] == "L1"
    assert evidence["working_tree_dirty"] is False
    assert evidence["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
    assert set(evidence["index"]["visibility"]) == {"public"}
    assert evidence["index"]["categories"].get("api", 0) == 0
    for record in evidence["sets"].values():
        categories = record["category_totals"]
        for category, total in categories.items():
            rows = [row for row in record["run"]["results"] if row["category"] == category]
            assert total == dict(queries=len(rows), hits_at_3=sum(row["hit_at_3"] for row in rows))
        assert categories["api"] == dict(queries=4, hits_at_3=0)
    text = json.dumps(evidence, ensure_ascii=False)
    assert "F:\\" not in text and "C:\\" not in text and "D:\\" not in text
    assert "private_supplement" not in text


def test_evidence_checker_catches_stale_summary_and_reference_tables():
    evidence, markdown, tables = artifacts()
    record = evidence["sets"]["holdout_24"]
    record["run"]["hits_at_3"] += 1
    with pytest.raises(ValueError, match="total"):
        validate_suite(evidence, markdown, tables)
    evidence, markdown, tables = artifacts()
    with pytest.raises(ValueError, match="Summary Markdown"):
        validate_suite(evidence, markdown + "stale", tables)
    stale = deepcopy(tables)
    stale["legacy_20"] += "stale"
    with pytest.raises(ValueError, match="Markdown"):
        validate_suite(evidence, markdown, stale)


def test_evidence_has_product_runner_query_and_corpus_blob_identities():
    evidence, _, _ = artifacts()
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
                             capture_output=True, text=True, timeout=15)
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Historical A10 source identity needs complete Git history")
    groups = [(evidence["actual_git_revision"], records) for records in (
        evidence["product_source_identity"], evidence["runner_source_identity"], evidence["test_source_identity"],
        [record["questions"] for record in evidence["sets"].values()])]
    build = evidence["index"]["build"]
    groups.append((build["actual_git_revision"], build["input_source_identity"]))
    for revision, records in groups:
        for identity in records:
            ref = revision + ":" + identity["path"]
            blob = subprocess.check_output(["git", "rev-parse", ref], cwd=ROOT, text=True, timeout=15).strip()
            data = subprocess.check_output(["git", "show", ref], cwd=ROOT, timeout=15)
            assert blob == identity["git_blob"]
            assert hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest() == identity["sha256_lf"]
