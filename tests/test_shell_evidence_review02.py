"""Evidence is bound to executed product code, not merely its test source."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/decisions/evidence/q03-shell-review02"


def test_shell_records_preserve_failed_attempt_and_stricter_native_rejections():
    evidence = json.loads((DIRECTORY / "evidence.json").read_text(encoding="utf8"))
    assert evidence["status"] == "partial"
    assert [(r["passed"], r["failed"]) for r in evidence["runs"]] == [(7, 1), (8, 0), (8, 0)]
    for run in evidence["runs"]:
        assert hashlib.sha256((DIRECTORY / run["report"]).read_bytes()).hexdigest() == run["report_sha256"]
        assert not run["working_tree_dirty"] and run["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
        for case in run["cases"]:
            assert case["source_unchanged"] and case["directory_unchanged"]
            assert case["actual_git_revision"] == run["actual_git_revision"]
        if run["failed"]:
            continue
        assert sum(c["expected_status"] == "failed" for c in run["cases"]) == 2
        for case in run["cases"]:
            process, = case["native_jobs"]
            assert process["returncode"] == 0 and process["nographics"] and not process["timed_out"]
            if case["status"] == "succeeded":
                assert case["comparison"]["atol_rule"].startswith("1e-6 times")
                assert len(case["comparison"]["atol"]) == 6
            else:
                assert "disagreement" in case["error"]["message"] and not case["artifact_sha256"]


def test_shell_product_and_test_identities_match_executed_git_blobs():
    probe = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, capture_output=True, text=True)
    if probe.returncode or probe.stdout.strip() == "true":
        pytest.skip("Executed product identities require complete Git history")
    evidence = json.loads((DIRECTORY / "evidence.json").read_text(encoding="utf8"))
    for run in evidence["runs"]:
        for identity in [*run["product_source_identity"], run["test_source_identity"]]:
            blob = subprocess.check_output(["git", "rev-parse", run["actual_git_revision"] + ":" + identity["path"]], cwd=ROOT, text=True).strip()
            assert blob == identity["git_blob_id"]
