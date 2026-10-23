"""Portable product provenance and honest denominators for ASCII all-column checks."""
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/decisions/evidence/q06-ascii-metadata-review02"


def test_all_column_evidence_keeps_missing_components_as_rejections():
    evidence = json.loads((DIRECTORY / "evidence.json").read_text(encoding="utf8"))
    rows, summary = evidence["cases"], evidence["summary"]
    assert evidence["status"] == "partial" and evidence["native_run"] is False
    assert len(rows) == summary["cases"]
    assert sum(r["component_stored"] for r in rows) == summary["stored_components"]
    assert sum(not r["component_stored"] for r in rows) == summary["missing_components_rejected"]
    assert sum(r["samples_checked"] for r in rows) == summary["raw_column_values_checked"]
    report = (DIRECTORY / "report.md").read_text(encoding="utf8")
    assert f'{summary["stored_components"]} stored components matched' in report
    assert f'{summary["raw_column_values_checked"]:,} matched' in report
    for row in rows:
        assert row["input_bytes_and_listing_unchanged"] and not row["working_tree_dirty"]
        assert row["actual_git_revision"] == evidence["actual_git_revision"]
        assert row["status"] == ("succeeded" if row["component_stored"] else "failed")
        assert row["independent_raw_columns_equal"] == row["component_stored"]
        assert bool(row["artifact_sha256"]) == row["component_stored"]


def test_ascii_all_column_records_bind_executed_product_and_test_blobs():
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, text=True, capture_output=True)
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Product provenance needs complete Git history")
    evidence = json.loads((DIRECTORY / "evidence.json").read_text(encoding="utf8"))
    for identity in [*evidence["product_source_identity"], evidence["test_source_identity"]]:
        blob = subprocess.check_output(["git", "rev-parse", evidence["actual_git_revision"]+":"+identity["path"]], cwd=ROOT, text=True).strip()
        assert blob == identity["git_blob_id"]
