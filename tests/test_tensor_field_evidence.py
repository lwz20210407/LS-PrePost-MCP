"""Q03 provenance integrity; never executes a native process."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT / "docs/decisions/evidence/q03-tensor-field"


def test_native_tensor_evidence_preserves_failures_and_explicit_mismatch_rejections():
    runs=json.loads((EVIDENCE / "evidence.json").read_text(encoding="utf8"))["runs"]
    assert [(r["passed"],r["failed"]) for r in runs] == [(3,3),(8,0),(8,0)]
    assert [r["executable"]["version"] for r in runs] == ["4.13","4.13","4.10"]
    for run in runs:
        report=(EVIDENCE / run["report"]).read_text(encoding="utf8")
        assert hashlib.sha256(report.encode()).hexdigest()==run["report_sha256"]
        assert run["working_tree_dirty"] is False and run["git_diff_sha256"]==hashlib.sha256(b"").hexdigest()
        for row in run["cases"]:
            assert row["source_unchanged"] and row["directory_unchanged"]
            assert row["actual_git_revision"]==run["actual_git_revision"]
            assert len(row["native_jobs"])==1
            if row["status"]=="succeeded":
                assert len(row["artifact_sha256"])==2
                assert row["comparison"]["entities"]==row["shape"][0]
            elif row["expected_status"]=="failed":
                assert not row["artifact_sha256"] and "disagreement" in row["error"]["message"]
    for run in runs[1:]:
        for row in run["cases"]:
            process=row["native_jobs"][0]
            assert process["status"]=="succeeded" and process["returncode"]==0 and process["nographics"]
            assert process["graphics"] is False and process["timed_out"] is False
        assert sum(c["expected_status"]=="failed" for c in run["cases"])==2


def test_native_tensor_sources_bind_actual_revision_and_lf_blobs():
    shallow=subprocess.run(["git","rev-parse","--is-shallow-repository"],cwd=ROOT,capture_output=True,text=True)
    if shallow.returncode or shallow.stdout.strip()=="true":
        pytest.skip("Historical native source identities require a full Git checkout")
    for run in json.loads((EVIDENCE / "evidence.json").read_text(encoding="utf8"))["runs"]:
        for source in run["test_source_identities"]:
            blob=subprocess.check_output(["git","rev-parse",run["actual_git_revision"]+":"+source["path"]],cwd=ROOT,text=True).strip()
            assert blob==source["git_blob_id"]
            content=subprocess.check_output(["git","cat-file","blob",blob],cwd=ROOT)
            assert hashlib.sha256(content.replace(b"\r\n",b"\n")).hexdigest()==source["sha256_lf"]
