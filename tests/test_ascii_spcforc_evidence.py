"""SPCFORC current records bind real stored values without certifying Native/frame semantics."""
import hashlib
from pathlib import Path

from tools.current_ascii_evidence import read_current_ascii_evidence

ROOT = Path(__file__).resolve().parents[1]


def test_spcforc_product_test_and_support_sources_match_recorded_lf():
    evidence = read_current_ascii_evidence(ROOT, "spcforc")
    assert {row["path"] for row in evidence["product_source_identity"]} == {
        "src/ls_prepost_mcp/domain/results/ascii_spcforc.py",
        "src/ls_prepost_mcp/results_target_tools.py",
        "src/ls_prepost_mcp/domain/results/ascii_records.py",
    }
    for group in ("product_source_identity", "captured_test_source_identity", "supporting_source_identity"):
        for identity in evidence[group]:
            path = identity["path"]
            assert not Path(path).is_absolute() and ".." not in Path(path).parts
            raw = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
            assert hashlib.sha256(raw).hexdigest() == identity["sha256_lf"], path
            assert len(identity["git_blob_id"]) == 40


def test_spcforc_positive_values_and_missing_moments_have_separate_real_job_roles():
    evidence = read_current_ascii_evidence(ROOT, "spcforc")
    assert evidence["task_status"] == "partial" and evidence["verification_level"] == "L1"
    assert evidence["native_executed"] is False and evidence["solver_executed"] is False
    run = evidence["runs"][0]
    assert run["working_tree_dirty"] is False and run["attempts"] == 1 and run["exit_code"] == 0
    assert run["source_before_sha256"] == run["source_after_sha256"]
    assert run["complete_source_before_after_equal"] is True
    assert run["input_full_sha256_stat_namespace_catalog_unchanged"] is True
    values = [column for case in run["cases"] for column in case["components"]]
    assert len(values) == run["positive_component_exports"] == 9
    assert sum(v["compared_values"] for v in values) == run["compared_values"] == 270192
    assert sum(v["nonzero_values"] for v in values) == run["nonzero_values"] == 130506
    assert sum(v["zero_values"] for v in values) == run["zero_values"] == 139686
    assert all(v["exact"] is True for v in values)
    positives = evidence["positive_jobs"]
    failures = evidence["expected_failed_missing_moment_jobs"]
    assert len(positives) == 9 and len(failures) == 3
    assert len({row["job_id"] for row in positives + failures}) == 12
    for row in positives:
        assert row["status"] == "succeeded" and row["artifact_count"] == 1
    assert {row["component"] for row in failures} == {"x_moment", "y_moment", "z_moment"}
    for row in failures:
        assert row["status"] == "failed" and row["artifact_count"] == 0
        assert row["numeric_payload_empty"] is True
        assert row["failure_context"] == {
            "database": "spcforc", "branch": None, "component": row["component"], "backend": "ls-dyna-ascii",
        }


def test_spcforc_declares_frame_and_actual_moment_evidence_limitations():
    evidence = read_current_ascii_evidence(ROOT, "spcforc")
    limits = evidence["evidence_boundaries"]
    assert limits["real_moment_nonzero_values"] == 0
    assert limits["real_written_moment_zero_values"] == 135000
    assert limits["missing_moments_filled"] is False and limits["historical_and_current_counts_added"] is False
    assert "local as printed" in evidence["source_semantics"]["frame"]
    assert "not CSID" in evidence["source_semantics"]["setid"]
    assert "stored_columns" in evidence["source_semantics"]["selection_mapping"]
