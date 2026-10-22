"""P11 published provenance integrity; these checks do not launch or certify a native run."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/decisions/evidence/p11-save"


def records():
    return json.loads((EVIDENCE / "evidence.json").read_text(encoding="utf-8"))["runs"]


def test_published_report_hashes_and_historical_source_blobs():
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Historical evidence Git blobs require a non-shallow Git checkout")
    for record in records():
        report = (EVIDENCE / record["report"]).read_text(encoding="utf-8")
        assert hashlib.sha256(report.encode("utf-8")).hexdigest() == record["report_sha256"]
        identity = record["test_source_identity"]
        actual = subprocess.check_output(["git", "rev-parse", record["actual_git_revision"] + ":" + identity["path"]],
                                         cwd=ROOT, text=True).strip()
        assert actual == identity["git_blob_id"]
        assert record["working_tree_dirty"] is False
        assert record["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()


@pytest.mark.parametrize("run_id,expected_count", [("r413e", 7), ("r410c", 2)])
def test_final_native_records_keep_process_mode_input_identity_and_expected_failures(run_id, expected_count):
    record = next(r for r in records() if r["run_id"] == run_id)
    assert record["passed"] == expected_count and record["failed"] == 0
    assert len(record["cases"]) == expected_count
    for case in record["cases"]:
        assert case["test_status"] == "passed" and case["original_tree_unchanged"] is True
        assert case["source_tree_sha256"]
        assert all(j["graphics"] is False and j["nographics"] is True and j["returncode"] == 0
                   and j["timed_out"] is False for j in case["native_jobs"])
        if case["expected_status"] == "failed":
            assert case["observed_status"] == "failed" and case["differences"]
            assert not case["artifact_sha256"] and len(case["native_jobs"]) == 1
        else:
            assert case["observed_status"] == "succeeded" and not case["differences"]
            assert case["artifact_sha256"] and len(case["native_jobs"]) == 2
            before, after = (case["observations"][phase] for phase in ("before_save", "after_reopen"))
            assert before["counts"] == after["counts"]
            assert before["part_ids_sha256"] == after["part_ids_sha256"]


def test_first_public_rejection_remains_a_failure_with_no_native_process():
    first = records()[0]
    assert first["run_id"] == "r413a" and first["failed"] == 1
    case = next(c for c in first["cases"] if c["case"] == "public-include")
    assert case["test_status"] == "failed" and case["observed_status"] == "failed"
    assert case["error"]["message"] == "Empty *INCLUDE card" and not case["native_jobs"]
