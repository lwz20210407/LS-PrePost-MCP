"""Current public NODOUT readback remains tied to its actual reader and wrapper."""
import hashlib
import subprocess
from pathlib import Path

import pytest

from tools.current_ascii_evidence import read_current_ascii_evidence, read_historical_ascii_evidence

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "docs/decisions/evidence/q06-ascii-nodout"
HISTORY_SHA256_LF = {
    "evidence.json": "8e6079c5cfc854933c2f2c810a358dc29fa778e00664338b68e84f152d2aa8a5",
    "report.md": "22cad6219ca544b12a7a1487ecd2c01f42aac238836aff209758a92ff04b0fed",
}


def current_evidence():
    return read_current_ascii_evidence(ROOT, "nodout")


def test_nodout_public_evidence_binds_the_reader_wrapper_and_scanner():
    evidence = current_evidence()
    assert evidence["task_status"] == "partial" and evidence["verification_level"] == "L1"
    assert evidence["native_executed"] is False
    products = evidence["product_source_identity"]
    assert {item["path"] for item in products} == {
        "src/ls_prepost_mcp/domain/results/ascii_nodout.py",
        "src/ls_prepost_mcp/results_target_tools.py",
        "src/ls_prepost_mcp/domain/results/ascii_records.py",
    }
    history = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
                             capture_output=True, text=True, timeout=15)
    if history.returncode or history.stdout.strip() == "true":
        pytest.skip("NODOUT product provenance requires complete Git history")
    for run in evidence["runs"]:
        assert run["working_tree_dirty"] is False
        for identity in products:
            path = identity["path"]
            recorded = subprocess.check_output(["git", "rev-parse", run["actual_git_revision"] + ":" + path],
                                               cwd=ROOT, text=True, timeout=15).strip()
            current = subprocess.check_output(["git", "rev-parse", "HEAD:" + path],
                                              cwd=ROOT, text=True, timeout=15).strip()
            assert recorded == identity["git_blob_id"]
            assert current == recorded, f"Refresh public NODOUT readback after product change: {path}"
            if "sha256_lf" in identity:
                raw = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
                assert hashlib.sha256(raw).hexdigest() == identity["sha256_lf"], path


def test_nodout_historical_records_remain_unchanged_after_current_refresh():
    for name, expected in HISTORY_SHA256_LF.items():
        raw = (HISTORY / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == expected


def test_nodout_posthoc_audit_preserves_original_failure_and_precise_negative_context():
    evidence = read_historical_ascii_evidence(ROOT, "nodout_0c9")
    assert evidence["original_capture_status"] == "failed"
    assert evidence["posthoc_audit_status"] == "accepted_exact_r2_metadata_context_contract"
    assert evidence["new_product_jobs_started"] == 0
    assert len(evidence["positive_host_jobs"]) == 54
    assert len(evidence["negative_limits"]) == 2
    positive_ids = {row["job_id"] for row in evidence["positive_host_jobs"]}
    negative_ids = {row["job_id"] for row in evidence["negative_limits"]}
    assert len(positive_ids) == 54 and len(negative_ids) == 2 and not positive_ids & negative_ids
    assert tuple(evidence["negative_tests"][key] for key in ("passed", "failed", "skipped")) == (2, 0, 0)
    for negative in evidence["negative_limits"]:
        assert negative["status"] == "failed" and negative["artifacts"] == 0
        assert negative["numeric_payload_empty"] is True and negative["failure_context_retained"] is True
        assert negative["failure_context"] == {
            "database": "nodout", "branch": None, "component": "z_displacement", "backend": "ls-dyna-ascii",
        }
    for run in evidence["runs"]:
        assert run["source_count"] == len(run["cases"]) == 6
        curves = [curve for case in run["cases"] for curve in case["curves"]]
        assert run["curve_count"] == len(curves) == 54
        assert run["compared_values"] == sum(curve["compared_values"] for curve in curves) == 231147
