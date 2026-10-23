"""The L1 arithmetic claim binds actual source blobs and never claims native proof."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest


def test_curve_validity_evidence_is_product_bound_and_l1_only(pytestconfig):
    root = Path(pytestconfig.rootpath)
    folder = root / "docs/decisions/evidence/q07-validity-review02"
    evidence = json.loads((folder / "evidence.json").read_text(encoding="utf8"))
    assert evidence["native_executed"] is False
    assert evidence["baseline"]["revision"].startswith("0563045") and evidence["baseline"]["failed"] == 17
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=root,
                             text=True, capture_output=True)
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Historical blob verification requires a complete Git checkout")
    for run in evidence["runs"]:
        assert run["passed"] == 129 and run["failed"] == 0 and not run["working_tree_dirty"]
        assert run["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
        report = (folder / run["report"]).read_text(encoding="utf8")
        assert run["report_sha256"] == hashlib.sha256(report.encode()).hexdigest()
        for source in [*run["product_source_identity"], run["test_source_identity"]]:
            blob = subprocess.check_output(["git", "rev-parse", run["actual_git_revision"] + ":" + source["path"]],
                                           cwd=root, text=True).strip()
            assert blob == source["git_blob_id"]
