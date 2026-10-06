"""I02: failures must survive strict JobResult construction at engine boundaries."""
import json

import pytest

from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.engine import BatchEngine, BatchJob, SessionEngine, SessionJob


@pytest.mark.parametrize("exception", [RuntimeError(), AssertionError(), RuntimeError(" \t")])
def test_batch_empty_exception_returns_failed_before_launch(tmp_path, monkeypatch, exception):
    def reject(*args, **kwargs):
        raise exception

    monkeypatch.setattr("ls_prepost_mcp.engine.batch.require_capability", reject)
    monkeypatch.setattr("ls_prepost_mcp.engine.batch.subprocess.Popen", lambda *a, **kw: pytest.fail("Must not launch"))
    result = BatchEngine().run(BatchJob(tmp_path / "lspp", tmp_path / "run.cfile", tmp_path, 1))
    assert result.status == "failed"
    assert result.error == dict(type=type(exception).__name__, message=type(exception).__name__)


def test_session_empty_exception_before_submission_returns_failed(tmp_path, monkeypatch):
    def fail(*args):
        raise RuntimeError()

    monkeypatch.setattr("ls_prepost_mcp.engine.session.LogCursor.capture", fail)
    result = SessionEngine().run(SessionJob("inspect", tmp_path, 1,
        lambda: pytest.fail("Must not submit"), lambda: True, log=tmp_path / "native.log"))
    assert result.status == "failed" and result.error["message"] == "RuntimeError"


@pytest.mark.parametrize("error", [None, {}, {"code": 42}, {"message": ""},
                                  {"message": " \t", "traceback": "native trace"}, {"message": 7}])
@pytest.mark.parametrize("verify", [False, True])
def test_failed_native_reply_keeps_fields_and_supplies_message(tmp_path, error, verify):
    reply = dict(job_id=tmp_path.name, ok=False, error=error)
    raw = json.dumps(reply)

    def submit():
        (tmp_path / "complete.json").write_text(raw, encoding="utf8")

    def validate(receipt):
        assert receipt["error"]["message"] == "Native reply reported failure without a diagnostic"
        return JobResult(operation="inspect", job_id=tmp_path.name, status="failed", error=receipt["error"])

    result = SessionEngine().run(SessionJob("inspect", tmp_path, 1, submit, lambda: True,
                                           verify=validate if verify else None))
    assert result.status == "failed"
    assert result.error["message"] == "Native reply reported failure without a diagnostic"
    for key, value in (error or {}).items():
        if key != "message":
            assert result.error[key] == value
    assert (tmp_path / "complete.json").read_text(encoding="utf8") == raw


def test_missing_native_error_still_returns_failed(tmp_path):
    def submit():
        (tmp_path / "complete.json").write_text(json.dumps(dict(job_id=tmp_path.name, ok=False)), encoding="utf8")

    result = SessionEngine().run(SessionJob("inspect", tmp_path, 1, submit, lambda: True))
    assert result.status == "failed" and result.error["message"]


def test_session_send_failure_preserves_uncertain_outcome(tmp_path):
    def submit():
        raise RuntimeError()

    result = SessionEngine().run(SessionJob("inspect", tmp_path, 1, submit, lambda: True))
    assert result.status == "unverified" and result.error["message"] == "RuntimeError"
