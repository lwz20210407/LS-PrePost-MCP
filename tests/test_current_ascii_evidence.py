"""Evidence routing is explicit, LF portable and confined before any target read."""
import hashlib
import json

import pytest

from tools.current_ascii_evidence import read_current_ascii_evidence, read_historical_ascii_evidence


def fixture_context(tmp_path):
    base = tmp_path / "docs/decisions/evidence"
    target = base / "owned"
    target.mkdir(parents=True)
    report = b"owned report\n"
    report_sha = hashlib.sha256(report).hexdigest()
    record = {"task_status": "partial", "report_sha256_lf": report_sha}
    raw = (json.dumps(record, indent=2) + "\n").encode()
    (target / "evidence.json").write_bytes(raw.replace(b"\n", b"\r\n"))
    (target / "report.md").write_bytes(report.replace(b"\n", b"\r\n"))
    entry = {"path": "docs/decisions/evidence/owned/evidence.json",
             "evidence_sha256_lf": hashlib.sha256(raw).hexdigest(), "report_sha256_lf": report_sha}
    context = {"schema_version": 1, "current": {"sleout": entry}, "history": {"owned": entry}}
    path = base / "q06-current.json"
    path.write_text(json.dumps(context), encoding="utf8")
    return context, path, target


def test_current_and_historical_records_verify_lf_without_relabeling(tmp_path):
    fixture_context(tmp_path)
    assert read_current_ascii_evidence(tmp_path, "sleout")["task_status"] == "partial"
    assert read_historical_ascii_evidence(tmp_path, "owned")["task_status"] == "partial"


@pytest.mark.parametrize("path", ["../outside/evidence.json", "/docs/decisions/evidence/evidence.json",
                                "//server/share/evidence.json", "C:/private/evidence.json",
                                "docs/decisions/evidence/../outside/evidence.json"])
def test_invalid_references_are_rejected_without_opening_an_outside_target(tmp_path, path):
    context, context_path, _ = fixture_context(tmp_path)
    context["current"]["sleout"]["path"] = path
    context_path.write_text(json.dumps(context), encoding="utf8")
    with pytest.raises(ValueError, match="reference"):
        read_current_ascii_evidence(tmp_path, "sleout")


@pytest.mark.parametrize("field", ["evidence_sha256_lf", "report_sha256_lf"])
def test_changed_record_or_report_cannot_be_silently_selected(tmp_path, field):
    context, context_path, _ = fixture_context(tmp_path)
    context["current"]["sleout"][field] = "0" * 64
    context_path.write_text(json.dumps(context), encoding="utf8")
    with pytest.raises(ValueError, match="differs"):
        read_current_ascii_evidence(tmp_path, "sleout")


@pytest.mark.parametrize("version", [True, 2, "1"])
def test_context_schema_is_strict(tmp_path, version):
    context, context_path, _ = fixture_context(tmp_path)
    context["schema_version"] = version
    context_path.write_text(json.dumps(context), encoding="utf8")
    with pytest.raises(ValueError, match="context"):
        read_current_ascii_evidence(tmp_path, "sleout")


def test_unknown_role_does_not_fall_back_to_another_capture(tmp_path):
    with pytest.raises(ValueError, match="role"):
        read_current_ascii_evidence(tmp_path, "unknown")


def test_report_links_cannot_read_an_outside_file(tmp_path):
    _, _, target = fixture_context(tmp_path)
    report = target / "report.md"
    report.unlink()
    outside = tmp_path / "outside-owned-report.md"
    outside.write_text("owned outside fixture\n", encoding="utf8")
    try:
        report.symlink_to(outside)
    except OSError:
        pytest.skip("Creating a local symlink is unavailable on this host")
    with pytest.raises(ValueError, match="links|reparse"):
        read_current_ascii_evidence(tmp_path, "sleout")
