"""Published snapshot provenance integrity; does not substitute for a native run."""
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def evidence():
    path = ROOT / "docs/decisions/evidence/i01-keyword-snapshot/evidence.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_snapshot_evidence_source_blobs_exist_at_the_actual_revisions():
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Historical native sources require a non-shallow Git checkout")
    data = evidence()
    for run in [*data["runs"], data["p11_410"]]:
        source = run["test_source"]
        blob = subprocess.check_output(["git", "rev-parse", run["actual_git_revision"] + ":" + source["path"]],
                                       cwd=ROOT, text=True).strip()
        assert blob == source["git_blob_id"] and run["working_tree_dirty"] is False


def test_snapshot_records_preserve_mode_identity_and_cleanup_scope():
    data = evidence()
    assert [r["passed"] for r in data["runs"]] == [8, 8, 1]
    for run in data["runs"]:
        for case in run["cases"]:
            assert case["actual_git_revision"] == run["actual_git_revision"]
            assert case["status"] == "succeeded" and case["nodes"] == 4
            assert case["source_unchanged"] and case["directory_unchanged"] and case["nographics"]
            assert case["snapshot_files"] == case["cleanup_removed"] == 3 and case["cleanup_retained"] == 0
            assert case["process"]["returncode"] == 0 and case["process"]["graphics"] is False


def test_public_failure_rechecks_are_versioned_and_do_not_claim_all_p100():
    cases = evidence()["public_cases"]
    assert {c["executable"]["version"] for c in cases} == {"4.13", "4.10"}
    for case in cases:
        assert case["case_id"] == "extra-keyword-064" and case["status"] == "identical_counts_only"
        assert case["counts"]["nodes"] == 35656 and case["counts"]["elements"] == 30420
        assert case["originals_unchanged"] and case["directory_listing_unchanged"]
        assert len(case["input_tree"]["files"]) == 2 and case["input_tree"]["tree_sha256_version"] == 1
        assert len(set(case["native_jobs"])) == 3
        assert case["process"]["graphics"] is False and case["nographics"]


def test_p11_negative_case_stays_failed_after_the_snapshot_fix():
    run = evidence()["p11_410"]
    assert run["passed"] == 7
    negative = next(c for c in run["cases"] if c["case"] == "mismatch")
    assert negative["status"] == negative["expected_result"] == "failed"
    assert negative["original_tree_unchanged"] and len(negative["native_jobs"]) == 1
