"""Q06 exact native provenance, separate sides and retained negative observations."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/decisions/evidence/q06-native-forces"


def test_force_native_evidence_covers_axes_sides_and_wrong_component_rejection():
    evidence = json.loads((EVIDENCE / "evidence.json").read_text(encoding="utf8"))
    assert evidence["status"] == "partial"
    assert evidence["initial_experiment"]["failed_cases"] == 3
    assert evidence["initial_experiment"]["actual_git_revision"] is None
    assert [(r["passed"], r["failed"]) for r in evidence["runs"]] == [(7, 0), (7, 0), (2, 0), (2, 0)]
    total = 0
    for run in evidence["runs"]:
        text = (EVIDENCE / run["report"]).read_text(encoding="utf8")
        assert hashlib.sha256(text.encode()).hexdigest() == run["report_sha256"]
        assert run["actual_git_revision"] in text and run["working_tree_dirty"] is False
        assert run["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
        if run["kind"] == "public_runner_compatibility":
            assert {c["case"] for c in run["cases"]} == {"ascii-contact-force", "ascii-section-force"}
            assert all(
                c["status"] == "succeeded"
                and c["originals_unchanged"]
                and c["input_tree_unchanged"]
                and c["source_directory_listing_unchanged"]
                for c in run["cases"]
            )
            continue
        assert len(run["cases"]) == 7
        for case in run["cases"]:
            assert case["actual_git_revision"] == run["actual_git_revision"]
            assert case["status"] == case["expected_status"]
            assert (
                case["source_unchanged"]
                and case["directory_unchanged"]
                and case["backend"] == "ls-dyna-ascii"
            )
            assert all(
                j["status"] == "succeeded"
                and j["returncode"] == 0
                and j["nographics"]
                and j["graphics"] is False
                and j["timed_out"] is False
                for j in case["native_jobs"]
            )
            if case["expected_status"] == "failed":
                assert "disagree" in case["error"]["message"] and not case["artifact_sha256"]
            else:
                curves = case["comparison"]["curves"]
                assert {c["side"] for c in curves} == ({0, 1} if case["database"] == "rcforc" else {None})
                total += sum(c["samples"] for c in curves)
    assert total == 2952


def test_force_native_test_sources_use_portable_blob_and_lf_identities():
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, capture_output=True, text=True
    )
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Historical force evidence needs full Git history")
    for run in json.loads((EVIDENCE / "evidence.json").read_text(encoding="utf8"))["runs"]:
        for source in run["test_source_identities"]:
            blob = subprocess.check_output(
                ["git", "rev-parse", run["actual_git_revision"] + ":" + source["path"]], cwd=ROOT, text=True
            ).strip()
            assert blob == source["git_blob_id"]
            raw = subprocess.check_output(["git", "cat-file", "blob", blob], cwd=ROOT)
            assert hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == source["sha256_lf"]
