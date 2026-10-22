"""P02 historical expression oracle and separate public save diagnostic integrity."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/decisions/evidence/p02-expression-commas"


def test_expression_evidence_keeps_native_oracle_and_public_failures_separate():
    data = json.loads((DIRECTORY / "evidence.json").read_text(encoding="utf8"))
    for run in [*data["runs"], *data["public_save_diagnostics"]]:
        report = (DIRECTORY / run["report"]).read_text(encoding="utf8")
        assert hashlib.sha256(report.encode()).hexdigest() == run["report_sha256"]
        assert run["working_tree_dirty"] is False and run["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
    assert {r["executable"]["version"] for r in data["runs"]} == {"4.13", "4.10"}
    for run in data["runs"]:
        assert run["passed"] == 2 and run["failed"] == 0 and len(run["cases"]) == 2
        for row in run["cases"]:
            assert row["status"] == "succeeded" and row["source_unchanged"] and not row["warnings"]
            assert len(row["observations"]) == 2 and len(row["native_jobs"]) == 4
            assert all(o["node_1"] == [1, 4.0, 0.0, 0.0] for o in row["observations"])
    before, after = data["public_save_diagnostics"]
    assert {r["case"] for r in before["cases"]} == {r["case"] for r in after["cases"]}
    for initial, final in zip(before["cases"], after["cases"], strict=True):
        assert initial["status"] == "failed" and initial["reload_warning_count"] == 4
        assert final["status"] == "succeeded" and final["reload_warning_count"] == 0
        assert initial["input_tree_sha256"] == final["input_tree_sha256"]
        assert initial["observations"] == final["observations"]
        assert final["originals_unchanged"] and final["directory_unchanged"]
        assert len(final["native_jobs"]) == 2


def test_expression_oracle_sources_bind_portable_git_blobs():
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
                             capture_output=True, text=True)
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Historical evidence requires full Git checkout")
    for run in json.loads((DIRECTORY / "evidence.json").read_text(encoding="utf8"))["runs"]:
        source = run["test_source_identity"]
        blob = subprocess.check_output(["git", "rev-parse", run["actual_git_revision"] + ":" + source["path"]],
                                       cwd=ROOT, text=True).strip()
        assert blob == source["git_blob_id"]
        content = subprocess.check_output(["git", "cat-file", "blob", blob], cwd=ROOT)
        assert hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest() == source["sha256_lf"]
