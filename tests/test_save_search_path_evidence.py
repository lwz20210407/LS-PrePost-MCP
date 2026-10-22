"""Published P11 search-save provenance and native result consistency."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/decisions/evidence/p11-search-path-save"


def test_search_save_reports_bind_clean_source_and_real_processes():
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
                             capture_output=True, text=True)
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Historical evidence source requires a full Git checkout")
    runs = json.loads((EVIDENCE / "evidence.json").read_text(encoding="utf8"))["runs"]
    assert {r["executable"]["version"] for r in runs} == {"4.10", "4.13"}
    for run in runs:
        report = (EVIDENCE / run["report"]).read_text(encoding="utf8")
        assert hashlib.sha256(report.encode()).hexdigest() == run["report_sha256"]
        source = run["test_source_identity"]
        blob_id = subprocess.check_output(["git", "rev-parse", run["actual_git_revision"] + ":" + source["path"]],
                                          cwd=ROOT, text=True).strip()
        assert blob_id == source["git_blob_id"]
        blob = subprocess.check_output(["git", "cat-file", "blob", blob_id], cwd=ROOT)
        assert hashlib.sha256(blob.replace(b"\r\n", b"\n")).hexdigest() == source["sha256_lf"]
        assert run["working_tree_dirty"] is False and run["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
        assert run["passed"] == 4 and run["failed"] == 0 and len(run["cases"]) == 4
        for case in run["cases"]:
            assert case["status"] == "succeeded" and case["source_unchanged"] and case["saved_tree_ok"]
            assert case["actual_git_revision"] == run["actual_git_revision"]
            assert not case["differences"] and not case["saved_missing_directories"]
            assert len(case["native_jobs"]) == 2
            assert all(j["returncode"] == 0 and j["nographics"] is True and j["graphics"] is False
                       and j["timed_out"] is False for j in case["native_jobs"])
