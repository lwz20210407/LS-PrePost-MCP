"""Review02 process regressions: bound committed evidence and nested pytest startup."""
import json

import pytest


def test_doc_ci_rejects_a_single_oversized_evidence_json(tmp_path, monkeypatch):
    from tools import check_doc_links as check

    relative = "docs/decisions/evidence/example/evidence.json"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"oversized": "x" * (512 * 1024)}), encoding="utf8")
    monkeypatch.setattr(check, "ROOT", tmp_path)
    monkeypatch.setattr(check.subprocess, "check_output", lambda *a, **kw: (relative + "\0").encode())
    with pytest.raises(SystemExit, match="512 KiB"):
        check.main()


def test_remote_report_nested_pytest_has_at_least_a_two_minute_timeout(tmp_path, monkeypatch):
    import subprocess

    from tests.test_native_regression import (
        test_remote_report_keeps_failed_lanes_and_never_calls_evidence_passed as nested,
    )

    seen = []
    class Observed(Exception):
        pass

    def run(*args, **kwargs):
        seen.append(kwargs["timeout"])
        raise Observed

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(Observed):
        nested(tmp_path)
    assert seen and seen[0] >= 120


def test_small_evidence_still_goes_through_link_validation(tmp_path, monkeypatch):
    from tools import check_doc_links as check

    relative = "docs/decisions/evidence/example/evidence.json"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text('{"source":"docs/MISSING.md"}', encoding="utf8")
    monkeypatch.setattr(check, "ROOT", tmp_path)
    monkeypatch.setattr(check.subprocess, "check_output", lambda *a, **kw: (relative + "\0").encode())
    with pytest.raises(SystemExit, match="Missing local link"):
        check.main()
