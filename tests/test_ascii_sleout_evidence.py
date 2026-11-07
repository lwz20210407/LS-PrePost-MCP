"""Q06 SLEOUT captures retain finite scope and portable product identities."""
import hashlib
from pathlib import Path

from tools.current_ascii_evidence import read_current_ascii_evidence, read_historical_ascii_evidence

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/decisions/evidence/q06-ascii-sleout"


def record():
    return read_current_ascii_evidence(ROOT, "sleout")


def test_sleout_capture_matches_current_product_and_verifier_lf_sources():
    evidence = record()
    assert {r["path"] for r in evidence["product_source_identity"]} == {
        "src/ls_prepost_mcp/domain/results/ascii_sleout.py",
        "src/ls_prepost_mcp/results_target_tools.py",
        "src/ls_prepost_mcp/domain/results/ascii_records.py",
    }
    for group in ("product_source_identity", "test_source_identity"):
        for identity in evidence[group]:
            path = identity["path"]
            assert not Path(path).is_absolute() and ".." not in Path(path).parts
            current = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
            assert hashlib.sha256(current).hexdigest() == identity["sha256_lf"], path
            assert len(identity["git_blob_id"]) == 40


def test_sleout_actual_public_capture_is_finite_and_keeps_input_source_guards():
    evidence = record()
    assert evidence["task_status"] == "partial" and evidence["verification_level"] == "L1"
    assert evidence["native_executed"] is False
    assert evidence["validity"]["deletion_validity"] == "unknown"
    assert evidence["validity"]["alive_mask_available"] is False
    assert set(evidence["components"]) == {"side_a_energy", "side_b_energy", "frictional_energy"}
    for run in evidence["runs"]:
        assert run["working_tree_dirty"] is False and run["native_executed"] is False
        assert run["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
        assert run["complete_source_before_after_equal"] is True
        assert run["source_before_sha256"] == run["source_after_sha256"]
        assert run["input_before_sha256"] == run["input_after_sha256"]
        assert run["input_full_sha256_stat_namespace_catalog_unchanged"] is True
        assert run["source_count"] == len(run["cases"]) == 2
        curves = [curve for case in run["cases"] for curve in case["curves"]]
        assert run["curve_count"] == len(curves) == 6
        assert sum(curve["compared_values"] for curve in curves) == run["compared_values"] == 14490
        assert sum(curve["nonzero_values"] for curve in curves) == run["nonzero_values"] == 6757
        assert all(curve["exact"] is True for curve in curves)
        assert all(case["source_unchanged"] and case["source_stat_unchanged"]
                   and case["source_directory_unchanged"] for case in run["cases"])


def test_sleout_history_and_report_do_not_turn_development_into_current_native_acceptance():
    evidence = read_historical_ascii_evidence(ROOT, "sleout_0c9")
    assert [r["failed"] for r in evidence["regressions"]] == [6, 3, 2]
    assert len({r["actual_git_revision"] for r in evidence["regressions"]}) == 3
    assert all(r["mock_missing_feature"] is False for r in evidence["regressions"])
    assert all(r["native_executed"] is False for r in evidence["regressions"])
    sdk = next(c for c in evidence["current_clean_checks"] if "minimal_environment" in c)
    assert sdk["minimal_environment"] is False
    report = (DIRECTORY / "report.md").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(report).hexdigest() == evidence["report_sha256"]
    assert evidence["runs"][0]["actual_git_revision"].encode() in report
    assert (DIRECTORY / "evidence.json").stat().st_size <= 512 * 1024
