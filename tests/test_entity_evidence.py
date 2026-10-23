"""G04 published evidence retains failures and verifies native source provenance."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/decisions/evidence/g04-entity-query"


def test_entity_evidence_is_partial_and_retains_failed_first_run():
    evidence = json.loads((EVIDENCE / "evidence.json").read_text(encoding="utf8"))
    assert evidence["status"] == "partial"
    assert [(r["passed"], r["failed"]) for r in evidence["runs"]] == [(1, 2), (3, 0), (3, 0)]
    for run in evidence["runs"]:
        text = (EVIDENCE / run["report"]).read_text(encoding="utf8")
        assert hashlib.sha256(text.encode()).hexdigest() == run["report_sha256"]
        assert run["actual_git_revision"] in text
        assert run["working_tree_dirty"] is False
        assert run["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
        assert {c["case"] for c in run["cases"]} == {"keyword-include", "public-solid", "public-shell"}
        for case in run["cases"]:
            if case["status"] == "failed":
                assert run["run_id"] == "r413a" and case["proof"] is None and case["reason"]
                continue
            proof = case["proof"]
            assert proof["actual_git_revision"] == run["actual_git_revision"]
            assert proof["source_unchanged"] and proof["directory_unchanged"] and proof["connectivity_equal"]
            assert proof["query_status"] == ("succeeded" if case["case"] == "keyword-include" else "partial")
            assert proof["material_known"] == (case["case"] == "keyword-include")
            assert proof["native_jobs"] and all(
                j["status"] == "succeeded" and j["returncode"] == 0 and j["nographics"]
                and j["graphics"] is False and j["timed_out"] is False
                for j in proof["native_jobs"]
            )


def test_entity_evidence_test_sources_are_portable_git_blobs():
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
                             capture_output=True, text=True)
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Historical entity evidence needs a full Git checkout")
    for run in json.loads((EVIDENCE / "evidence.json").read_text(encoding="utf8"))["runs"]:
        for source in run["test_source_identities"]:
            blob = subprocess.check_output(
                ["git", "rev-parse", run["actual_git_revision"] + ":" + source["path"]], cwd=ROOT, text=True
            ).strip()
            assert blob == source["git_blob_id"]
            raw = subprocess.check_output(["git", "cat-file", "blob", blob], cwd=ROOT)
            assert hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == source["sha256_lf"]
