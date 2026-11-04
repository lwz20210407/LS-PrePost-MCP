"""Current native claims must remain tied to the code and tests actually executed."""
import hashlib
import itertools
import json
import subprocess

import pytest


def evidence(root):
    folder = root / "docs/decisions/evidence/q07-butterworth-native"
    return folder, json.loads((folder / "evidence.json").read_text(encoding="utf8"))


def test_butterworth_native_records_are_complete_and_strict(pytestconfig):
    folder, data = evidence(pytestconfig.rootpath)
    assert data["native_executed"]
    assert {r["executable"]["version"] for r in data["runs"]} == {"4.10", "4.13"}
    expected = set(itertools.product(
        ["short_impulse", "sine_mix", "offset_step", "impact_ringdown"], [60, 600], ["s", "ms"]))
    for run in data["runs"]:
        text = (folder / run["report"]).read_text(encoding="utf8")
        assert hashlib.sha256(text.encode()).hexdigest() == run["report_sha256"]
        assert run["passed"] == len(run["cases"]) == len(run["test_ids"])
        assert run["failed"] == run["skipped"] == 0 and run["full_record"]
        assert not run["working_tree_dirty"]
        assert run["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
        bw = [c for c in run["cases"] if "case" in c]
        assert {(c["case"], c["nominal_frequency_hz"], c["time_unit"]) for c in bw} == expected
        for case in run["cases"]:
            assert case["actual_git_revision"] == run["actual_git_revision"]
            assert case["executable"] == run["executable"] and case["verdict"] == "agrees"
            comparison = case if "case" in case else case["comparisons"]["lsprepost"]
            assert comparison["rtol"] == 2e-5 and comparison["atol"] > 0
            assert case["trailing_option"] == 0
        assert run["product_source_identity"] and run["test_source_identity"]


def test_butterworth_current_evidence_is_bound_to_product_and_test_blobs(pytestconfig):
    root = pytestconfig.rootpath
    _, data = evidence(root)
    state = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=root,
                           capture_output=True, text=True)
    if state.returncode or state.stdout.strip() == "true":
        pytest.skip("Historical source binding requires a complete Git checkout")
    for run in data["runs"]:
        for source in run["product_source_identity"] + run["test_source_identity"]:
            historical = subprocess.check_output(
                ["git", "rev-parse", run["actual_git_revision"] + ":" + source["path"]], cwd=root, text=True)
            assert historical.strip() == source["git_blob_id"]
            if run["validity"] == "current":
                current = subprocess.run(["git", "hash-object", "--path=" + source["path"], source["path"]],
                                         cwd=root, check=True, capture_output=True, text=True)
                assert current.stdout.strip() == source["git_blob_id"], source["path"]
