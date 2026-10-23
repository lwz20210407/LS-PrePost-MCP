"""Q08 acceptance is tied to real native batches, not mocked raster/CSV generation."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/decisions/evidence/q08-batch"


def test_batch_plot_evidence_covers_all_q08_acceptance_and_native_hash_scopes():
    evidence = json.loads((EVIDENCE / "evidence.json").read_text(encoding="utf8"))
    assert evidence["status"] == "done"
    assert len(evidence["runs"]) == 4
    for run in evidence["runs"]:
        text = (EVIDENCE / run["report"]).read_text(encoding="utf8")
        assert hashlib.sha256(text.encode()).hexdigest() == run["report_sha256"]
        assert run["actual_git_revision"] in text
        assert (
            run["working_tree_dirty"] is False and run["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
        )
        assert run["passed"] == 3 and run["failed"] == 0 and len(run["jobs"]) == 6
        assert {j["curve_count"] for j in run["jobs"]} == {1, 3, 10}
        assert {j["axes"]["native_axes_token"] for j in run["jobs"]} == {"Lin-Lin", "Log-Lin", "Log-Log"}
        assert any(not j["legend"] for j in run["jobs"])
        assert any(j["axes"]["requested_x_range"] and j["axes"]["requested_y_range"] for j in run["jobs"])
        for job in run["jobs"]:
            assert job["status"] == "succeeded" and job["route"] == "batch" and job["visible_gui"] is False
            assert job["source_csvs_unchanged"] and all(
                c["numeric_verification"]["row_order_preserved"] for c in job["curves"]
            )
            process = job["process"]
            assert process["graphics"] is False and process["returncode"] == 0 and process["nographics"]
            assert process["timed_out"] is False
            artifacts = {a["name"]: a for a in job["artifacts"]}
            consistency = job["png_csv_consistency"]
            assert consistency["same_native_plot_window"] and consistency["readback_after_png"]
            assert artifacts["plot.png"]["sha256"] == consistency["png_sha256"]
            assert artifacts["curves.csv"]["sha256"] == consistency["csv_sha256"]
            assert artifacts["native.xy"]["sha256"] == consistency["native_xy_sha256"]
            assert all(n > 100 for n in artifacts["plot.png"]["dimensions"])
            if run["run_id"].endswith("b"):
                assert len(job["executable"]["sha256"]) == 64
                assert len(job["executable"]["source_config_sha256"]) == 64
                assert "before and after" in job["executable"]["hash_scope"]
            else:
                assert job["executable"]["sha256"] is None
                assert "no full startup hash claimed" in job["executable"]["hash_scope"]


def test_batch_plot_evidence_has_portable_historical_source_hashes():
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, capture_output=True, text=True
    )
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Historical XYPlot provenance needs full Git history")
    for run in json.loads((EVIDENCE / "evidence.json").read_text(encoding="utf8"))["runs"]:
        for source in run["source_identities"]:
            blob = subprocess.check_output(
                ["git", "rev-parse", run["actual_git_revision"] + ":" + source["path"]], cwd=ROOT, text=True
            ).strip()
            assert blob == source["git_blob_id"]
            raw = subprocess.check_output(["git", "cat-file", "blob", blob], cwd=ROOT)
            assert hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == source["sha256_lf"]
