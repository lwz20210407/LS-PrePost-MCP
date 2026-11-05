"""A public readback does not remain current after an unrecorded parser change."""
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_nodout_public_evidence_binds_the_reader_wrapper_and_scanner():
    evidence = json.loads((ROOT / "docs/decisions/evidence/q06-ascii-nodout/evidence.json").read_text(encoding="utf8"))
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
