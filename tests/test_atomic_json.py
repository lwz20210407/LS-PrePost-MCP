import json
from pathlib import Path

import pytest

from ls_prepost_mcp.jobs import atomic_json


def locked_error():
    error = PermissionError("Temporarily denied by a Windows reader")
    error.winerror = 5
    return error


def test_atomic_manifest_retries_transient_windows_lock_preserving_old_document(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text('{"old": true}')
    replace = Path.replace
    attempts = []

    def temporarily_locked(source, target):
        attempts.append(source)
        assert json.loads(path.read_text()) == {"old": True}
        if len(attempts) < 3:
            raise locked_error()
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", temporarily_locked)
    monkeypatch.setattr("ls_prepost_mcp.jobs.time.sleep", lambda delay: None)
    atomic_json(path, {"new": True})
    assert len(attempts) == 3 and json.loads(path.read_text()) == {"new": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_manifest_permanent_failure_is_bounded_and_does_not_replace_original(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text('{"old":true}')
    attempts = []

    def locked(source, target):
        attempts.append(source)
        raise locked_error()

    monkeypatch.setattr(Path, "replace", locked)
    monkeypatch.setattr("ls_prepost_mcp.jobs.time.sleep", lambda delay: None)
    with pytest.raises(PermissionError):
        atomic_json(path, {"new": True})
    assert len(attempts) == 6 and path.read_text() == '{"old":true}'
    assert not list(tmp_path.glob("*.tmp"))
