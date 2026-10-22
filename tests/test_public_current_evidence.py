"""I04 current public run: preservation, honest verdict transitions and provenance."""
import collections
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/decisions/evidence/i04-current-public100"


def test_public100_verdicts_and_preservation_are_complete_and_not_reclassified_as_passes():
    data = json.loads((EVIDENCE / "evidence.json").read_text(encoding="utf8"))
    rows = data["cases"]
    assert len(rows) == len({r["case"] for r in rows}) == 100
    assert collections.Counter(r["status"] for r in rows) == data["outcomes"] == {
        "passed": 45, "failed": 5, "evidence_only": 50}
    transitions = collections.Counter((r["previous_status"], r["status"]) for r in rows)
    assert transitions == {(r["previous"], r["current"]): r["count"] for r in data["transition_counts"]}
    assert transitions["failed", "passed"] == 29 and transitions["failed", "evidence_only"] == 11
    for row in rows:
        assert row["originals_unchanged"] and row["input_tree_unchanged"] and row["source_directory_listing_unchanged"]
        assert row["tree_sha256"] == row["input_tree"]["tree_sha256"]
        assert row["tree_sha256_version"] and row["input_tree"]["files"]
        if row["status"] == "evidence_only":
            assert not row["checks"] and row["input_classification"]
        elif row["status"] == "failed":
            assert row["failure_class"]


def test_public100_report_and_historical_runner_blobs_are_portable():
    data = json.loads((EVIDENCE / "evidence.json").read_text(encoding="utf8"))
    report = (EVIDENCE / data["report"]).read_text(encoding="utf8")
    assert hashlib.sha256(report.encode()).hexdigest() == data["report_sha256"]
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
                             capture_output=True, text=True)
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Historical evidence source requires full Git checkout")
    assert data["working_tree_dirty"] is False and data["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
    for source in data["test_source_identities"]:
        blob_id = subprocess.check_output(["git", "rev-parse", data["actual_git_revision"] + ":" + source["path"]],
                                          cwd=ROOT, text=True).strip()
        assert blob_id == source["git_blob_id"]
        content = subprocess.check_output(["git", "cat-file", "blob", blob_id], cwd=ROOT)
        assert hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest() == source["sha256_lf"]
