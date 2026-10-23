"""Preserve actual negative comparisons and product identities for both versions."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/decisions/evidence/q03-clock-review02"


def test_clock_runs_keep_expected_failures_and_zero_time_floor():
    data = json.loads((DIRECTORY / "evidence.json").read_text(encoding="utf8"))
    assert data["status"] == "partial" and data["native_run"]
    assert sum(r["native_processes"] for r in data["runs"]) == 46
    for run in data["runs"]:
        assert run["passed"] == 19 and run["failed"] == 0
        assert len(run["cases"]) == 19 and sum(c["expected_status"] == "failed" for c in run["cases"]) == 3
        assert hashlib.sha256((DIRECTORY / run["report"]).read_text(encoding="utf8").encode()).hexdigest() == run["report_sha256"]
        for case in run["cases"]:
            assert case["status"] == case["expected_status"] and case["source_unchanged"] and case["directory_unchanged"]
            if case["status"] == "failed":
                assert not case["artifact_sha256"]
                continue
            comparison = case["comparison"]
            if case["kind"] == "tensor":
                assert comparison["time_atol"] == 0
            else:
                assert comparison["tolerances"]["time"]["atol"] == 0
            if case["kind"] == "force":
                assert "atol_by_curve" in comparison["tolerances"]["value"]


def test_clock_native_sources_are_bound_to_actual_git_revisions():
    probe = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, text=True, capture_output=True)
    if probe.returncode or probe.stdout.strip() == "true":
        pytest.skip("Native product history requires complete Git checkout")
    data = json.loads((DIRECTORY / "evidence.json").read_text(encoding="utf8"))
    for run in data["runs"]:
        assert not run["working_tree_dirty"] and run["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
        for item in [*run["product_source_identity"], *run["test_source_identity"]]:
            actual = subprocess.check_output(["git", "rev-parse", run["actual_git_revision"]+":"+item["path"]], cwd=ROOT, text=True).strip()
            assert actual == item["git_blob_id"]
