import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/decisions/evidence/q05-stored-point-review02"


def test_history_points_are_explicit_and_wrong_pairings_are_not_passed_jobs():
    data = json.loads((DIRECTORY / "evidence.json").read_text(encoding="utf8"))
    assert data["status"] == "partial" and data["native_run"]
    assert sum(r["native_processes"] for r in data["runs"]) == 34
    for run in data["runs"]:
        assert run["failed"] == 0 and len(run["cases"]) == run["passed"]
        assert hashlib.sha256((DIRECTORY / run["report"]).read_text(encoding="utf8").encode()).hexdigest() == run["report_sha256"]
        for case in run["cases"]:
            assert case["status"] == case["expected_status"]
            assert case["source_unchanged"] and case["directory_unchanged"]
            if case["status"] == "failed":
                assert not case["artifact_sha256"]
        if run["group"] == "point":
            assert run["passed"] == 4 and sum(c["status"] == "failed" for c in run["cases"]) == 1
            for case in run["cases"]:
                assert case["layer_discrimination_nonzero"]
                if case["status"] == "succeeded":
                    assert all(c["index"] == case["stored_point"] for c in case["sampling"])


def test_history_point_provenance_matches_executed_product_and_fixture_blobs():
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, text=True, capture_output=True)
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Native provenance requires full Git history")
    data = json.loads((DIRECTORY / "evidence.json").read_text(encoding="utf8"))
    for run in data["runs"]:
        assert not run["working_tree_dirty"]
        assert run["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
        for item in [*run["product_source_identity"], *run["test_source_identity"]]:
            actual = subprocess.check_output(["git", "rev-parse", run["actual_git_revision"]+":"+item["path"]], cwd=ROOT, text=True).strip()
            assert actual == item["git_blob_id"]
