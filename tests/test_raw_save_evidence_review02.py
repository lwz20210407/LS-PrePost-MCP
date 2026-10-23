"""P1-13: a native claim must bind product modules as well as its test file."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest


def test_active_save_evidence_binds_product_sources_and_actual_revision(pytestconfig):
    ROOT = Path(pytestconfig.rootpath)
    legacy = json.loads((ROOT / "docs/decisions/evidence/p11-save/evidence.json").read_text(encoding="utf-8"))
    active = legacy.get("active_product_evidence")
    if active:
        evidence_path = ROOT / active
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        records = [r for r in evidence["runs"] if r["validity"] == "current_for_recorded_product_blobs"]
    else:
        evidence_path = ROOT / "docs/decisions/evidence/p11-save/evidence.json"
        records = [r for r in legacy["runs"] if r["run_id"] in {"r413e", "r410c"}]
    assert records, "No active product-bound P11 evidence"
    required = {"src/ls_prepost_mcp/model_save.py", "src/ls_prepost_mcp/domain/model/persist.py",
                "src/ls_prepost_mcp/service.py", "src/ls_prepost_mcp/embedded.py"}
    for run in records:
        products = {p["path"]: p["git_blob_id"] for p in run.get("product_source_identity", [])}
        assert required <= products.keys(), "Native claim binds only the test file, not the reopen implementation"
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
                             text=True, capture_output=True)
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Historical product blobs require a complete Git checkout")
    for run in records:
        report = (evidence_path.parent / run["report"]).read_text(encoding="utf-8")
        assert hashlib.sha256(report.encode()).hexdigest() == run["report_sha256"]
        assert not run["working_tree_dirty"]
        assert run["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
        for item in run["product_source_identity"]:
            actual = subprocess.check_output(["git", "rev-parse", run["actual_git_revision"] + ":" + item["path"]],
                                             cwd=ROOT, text=True).strip()
            assert actual == item["git_blob_id"]
            current = subprocess.check_output(["git", "rev-parse", "HEAD:" + item["path"]],
                                              cwd=ROOT, text=True).strip()
            assert current == actual, "Native evidence superseded by product change: " + item["path"]
