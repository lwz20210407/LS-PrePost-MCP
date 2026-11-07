"""G04 host evidence stays tied to its recorded product code and scope."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/decisions/evidence/g04-keyword-triangles"


def record():
    return json.loads((DIRECTORY / "evidence.json").read_text(encoding="utf8"))


def test_triangle_host_record_has_current_portable_product_and_test_sources():
    evidence = record()
    assert evidence["newline_identity"].startswith("Git blob ID")
    for group in ("product_source_identity", "test_source_identity"):
        assert evidence[group]
        for path, identity in evidence[group].items():
            assert not Path(path).is_absolute() and ".." not in Path(path).parts
            raw = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
            assert hashlib.sha256(raw).hexdigest() == identity["sha256_lf"], path
            assert len(identity["git_blob_id"]) == 40


def test_triangle_host_record_preserves_failure_and_does_not_claim_native_acceptance():
    evidence = record()
    assert evidence["status"] == "partial" and evidence["verification_level"] == "L1"
    assert evidence["working_tree_dirty"] is False
    assert evidence["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
    assert evidence["baseline"]["selected"] == evidence["baseline"]["failed"] + evidence["baseline"]["passed"]
    assert evidence["baseline"]["failed"] > 0 and evidence["baseline"]["deselected"] > 0
    assert evidence["clean_run"]["source_before_after_equal"] is True
    assert evidence["sdk_absence_simulation"]["complete_minimal_environment"] is False
    assert evidence["sdk_absence_simulation"]["data_empty"] is True
    assert evidence["native_jobs"] == 0 and evidence["native_verified"] is False
    assert evidence["solver_verified"] is False
    report = (DIRECTORY / evidence["report"]).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(report).hexdigest() == evidence["report_sha256_lf"]
    assert evidence["actual_git_revision"].encode() in report
    assert (DIRECTORY / "evidence.json").stat().st_size <= 512 * 1024
