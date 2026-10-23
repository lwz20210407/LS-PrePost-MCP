"""Native filter xfails must remain explicit numeric mismatches, never passes."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest


def test_sae_native_evidence_keeps_all_eight_mismatches_and_product_identity(pytestconfig):
    root = Path(pytestconfig.rootpath)
    folder = root / "docs/decisions/evidence/q07-native-filter-review02"
    evidence = json.loads((folder / "evidence.json").read_text(encoding="utf8"))
    assert evidence["native_executed"] is True
    assert len(evidence["runs"]) == 2
    assert sum(r["passed"] for r in evidence["runs"]) == 0
    assert sum(r["mismatched_xfail"] for r in evidence["runs"]) == 8
    for run in evidence["runs"]:
        assert not run["working_tree_dirty"] and run["native_processes"] == 4
        assert run["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
        assert {(c["cfc"], c["time_unit"]) for c in run["cases"]} == {(60,"s"),(60,"ms"),(600,"s"),(600,"ms")}
        report = (folder / run["report"]).read_text(encoding="utf8")
        assert hashlib.sha256(report.encode()).hexdigest() == run["report_sha256"]
        for case in run["cases"]:
            assert case["verdict"] == "mismatch" and not case["comparisons"]["odd"]["agrees"]
            assert case["actual_git_revision"] == run["actual_git_revision"]
            assert case["samples"] == case["control"]["sample_count"] == 4001
            assert case["native_process"] == dict(returncode=0, graphics=False, timed_out=False)
            assert case["comparisons"]["odd"]["max_absolute_error"] > 0
    shallow = subprocess.run(["git","rev-parse","--is-shallow-repository"],cwd=root,text=True,capture_output=True)
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Historical product blobs require a complete Git checkout")
    for run in evidence["runs"]:
        for source in run["product_and_test_source_identity"]:
            actual = subprocess.check_output(["git","rev-parse",run["actual_git_revision"]+":"+source["path"]],
                                             cwd=root,text=True).strip()
            assert actual == source["git_blob_id"]
