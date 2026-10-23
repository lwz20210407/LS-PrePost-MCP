"""Review02 evidence is bound to product code and an independent keyword oracle."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/decisions/evidence/q01-title-review02/evidence.json"


def test_title_evidence_is_not_a_native_or_same_algorithm_claim():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf8"))
    assert evidence["status"] == "partial" and evidence["native_run"] is False
    assert len(evidence["cases"]) == 3
    assert sorted(c["part_count"] for c in evidence["cases"]) == [2, 7, 7]
    assert evidence["baseline"]["unit_failed"] == 11 and evidence["baseline"]["public_oracle_failed"] == 3
    for case in evidence["cases"]:
        assert (
            case["titles_equal_keyword"]
            and case["keyword_tree_unchanged"]
            and case["result_family_unchanged"]
        )
        assert (
            case["working_tree_dirty"] is False
            and case["actual_git_revision"] == evidence["actual_git_revision"]
        )
        assert case["product_source_identity"] == evidence["product_source_identity"]
        assert case["title_mapping_source"] == "internal_ordinal"
    old = json.loads((ROOT / "docs/decisions/evidence/q01-validity/evidence.json").read_text(encoding="utf8"))
    assert all(
        r["titles_match_stored_ids"] is None and r["title_claim_status"] == "superseded_circular_oracle"
        for r in old["runs"]
    )


def test_active_title_evidence_matches_product_blobs_not_only_test_blobs():
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, capture_output=True, text=True
    )
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Title product provenance needs full Git history")
    evidence = json.loads(EVIDENCE.read_text(encoding="utf8"))
    for identity in evidence["product_source_identity"]:
        path = identity["path"]
        recorded = subprocess.check_output(
            ["git", "rev-parse", evidence["actual_git_revision"] + ":" + path], cwd=ROOT, text=True
        ).strip()
        assert recorded == identity["git_blob_id"]
        if evidence["validity"] == "current_for_recorded_product_blobs":
            current = subprocess.check_output(
                ["git", "rev-parse", "HEAD:" + path], cwd=ROOT, text=True
            ).strip()
            assert current == recorded, f"Product {path} changed: supersede or refresh the title evidence"
