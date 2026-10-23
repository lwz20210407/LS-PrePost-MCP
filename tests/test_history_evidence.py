"""Q05 exact native provenance and per-domain acceptance coverage."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/decisions/evidence/q05-history"


def test_native_history_evidence_covers_all_modes_and_stricter_rechecks():
    runs = json.loads((EVIDENCE / "evidence.json").read_text(encoding="utf8"))["runs"]
    assert [(r["passed"], r["failed"]) for r in runs] == [(4, 0), (4, 0), (2, 0), (2, 0)]
    assert [r["executable"]["version"] for r in runs] == ["4.13", "4.10", "4.13", "4.10"]
    for index, run in enumerate(runs):
        expected = {"node", "solid", "part", "global"} if index < 2 else {"part", "global"}
        assert {r["domain"] for r in run["cases"]} == expected
        text = (EVIDENCE / run["report"]).read_text(encoding="utf8")
        assert hashlib.sha256(text.encode()).hexdigest() == run["report_sha256"]
        assert (
            run["working_tree_dirty"] is False and run["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
        )
        for row in run["cases"]:
            assert row["status"] == "succeeded" and row["source_unchanged"] and row["directory_unchanged"]
            assert row["actual_git_revision"] == run["actual_git_revision"]
            assert row["curve_count"] == (1 if row["domain"] == "global" else 2)
            assert len(row["artifact_sha256"]) == row["curve_count"] and row["total_samples"] > 0
            assert row["comparison"]["backend"] == "lsprepost"
            if index >= 2:
                assert row["comparison"]["tolerances"]["time"]["atol"] == 1e-9
                assert "max_time_absolute_error" in row["comparison"]
            assert all(
                j["status"] == "succeeded"
                and j["returncode"] == 0
                and j["graphics"] is False
                and j["nographics"]
                and j["timed_out"] is False
                for j in row["native_jobs"]
            )


def test_native_history_source_ids_and_lf_hashes():
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, capture_output=True, text=True
    )
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Historical native source blobs need a full checkout")
    for run in json.loads((EVIDENCE / "evidence.json").read_text(encoding="utf8"))["runs"]:
        for source in run["test_source_identities"]:
            blob = subprocess.check_output(
                ["git", "rev-parse", run["actual_git_revision"] + ":" + source["path"]], cwd=ROOT, text=True
            ).strip()
            assert blob == source["git_blob_id"]
            content = subprocess.check_output(["git", "cat-file", "blob", blob], cwd=ROOT)
            assert hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest() == source["sha256_lf"]
