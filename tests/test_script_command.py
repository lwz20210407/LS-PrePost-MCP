import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import CheckResult, JobResult
from ls_prepost_mcp.core.script_request import ScriptRequest
from ls_prepost_mcp.service import Service


@pytest.mark.parametrize("values", [dict(code="top\nbottom"), dict(code="top;exit"),
                                     dict(code="exit"), dict(context="session"),
                                     dict(session_id="sid"), dict(expected_counts={"nodes": True}),
                                     dict(code='open command "other.cfile"'),
                                     dict(code=' OpEn\t COMMAND "other.cfile"'),
                                     dict(code='openc   command "other.cfile"'), dict(code="   ")])
def test_script_invalid_context_or_code_has_no_execution(tmp_path, values):
    args = dict(language="command", code="top")
    args.update(values)
    with pytest.raises((ValueError, ValidationError)):
        Service(Settings(tmp_path)).run_script(**args)
    assert not list(tmp_path.iterdir())


def test_batch_returns_typed_result_and_native_error_text(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))
    directory = tmp_path / "job"
    directory.mkdir()
    (directory / "lspost.msg").write_bytes(b"invalid_test\nInvalid command invalid_test!\n")
    monkeypatch.setattr(service, "prepare_native_program", lambda *a, **kw: dict(job_id="prepared", data=dict(sha256="hash")))
    monkeypatch.setattr(service, "execute_native_program", lambda *a, **kw: dict(
        status="failed", job_id="job", job_directory=str(directory), error=dict(message="Native rejected")))
    result = JobResult.model_validate(service.run_script("command", "invalid_test"))
    assert result.status == "failed"
    assert result.data["native_echo"]["errors"] == ["Invalid command invalid_test!"]
    assert Path(result.evidence[0].path).read_bytes() == (directory / "lspost.msg").read_bytes()


def test_session_uses_immutable_request_log_not_later_session_messages(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))
    directory = tmp_path / "request"
    directory.mkdir()
    (directory / "native-session.log").write_bytes(b"top\n")
    source = tmp_path / "lspost.msg"
    source.write_text("old error\ntop\nInvalid command from later job\n")
    (directory / "native-session-log.json").write_text(json.dumps(dict(source=str(source), offset=10)))
    monkeypatch.setattr(service, "execute_gui_command", lambda *a, **kw: dict(
        status="succeeded", request_id="request", job_directory=str(directory), data=dict(counts=dict(nodes=8))))
    monkeypatch.setattr(service, "execute_native_program", lambda *a, **kw: pytest.fail("Session must not spawn batch"))
    result = service.run_script("command", "top", context="session", session_id="sid", expected_counts=dict(nodes=8))
    assert result["status"] == "succeeded" and result["data"]["native_echo"]["text"] == "top\n"
    assert result["data"]["native_echo"]["offset"] == 10


def test_open_output_validation_precedes_session_mutation(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "open_in_gui_session", lambda *a, **kw: pytest.fail("No side effects"))
    with pytest.raises(ValueError, match="Open command"):
        service.run_script("command", 'open keyword "file.k"', context="session", session_id="sid",
                           outputs=[dict(name="output.k", kind="keyword")])


def test_command_contract_has_only_explicit_batch_or_session_context():
    request = ScriptRequest(language="command", code="top", context="session", session_id="sid")
    assert request.model is None


def test_failed_execution_remains_failed_when_native_log_is_missing(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "prepare_native_program", lambda *a, **kw: dict(job_id="p", data=dict(sha256="h")))
    monkeypatch.setattr(service, "execute_native_program", lambda *a, **kw: dict(
        status="failed", job_id="j", job_directory=str(tmp_path), error=dict(message="Native crashed")))
    result = service.run_script("command", "top")
    assert result["status"] == "failed" and result["error"]["message"] == "Native crashed"


def test_declared_outputs_bind_exact_tokens_preserving_native_windows_paths():
    from ls_prepost_mcp.native.commands import bind_output_paths
    directory = r"C:\jobs\fresh request"
    assert bind_output_paths('save keyword "part.k"', ["part.k"], directory) == 'save keyword "C:\\jobs\\fresh request\\part.k"'
    assert bind_output_paths('print png part.png opaque', ["part.png"], directory) == 'print png "C:\\jobs\\fresh request\\part.png" opaque'
    assert bind_output_paths('save keyword "other-part.k"', ["part.k"], directory) == 'save keyword "other-part.k"'


def test_native_output_open_failure_is_an_error_but_normal_output_echo_is_not():
    from ls_prepost_mcp.core.native_log import native_errors
    assert native_errors("Output file templsppfile_F:/job/output.k not open")
    assert not native_errors("save keyword output.k\nScript parsed. no error found")


@pytest.mark.parametrize("log_present", [True, False])
def test_script_result_preserves_normalized_warnings_and_checks(tmp_path, monkeypatch, log_present):
    service = Service(Settings(tmp_path))
    if log_present:
        (tmp_path / "lspost.msg").write_text("top\n", encoding="utf8")
    normalized = JobResult(operation="run_script", status="partial", data=dict(exported=1),
                           warnings=["Image export incomplete"],
                           checks=[CheckResult(name="image", status="failed")])
    monkeypatch.setattr("ls_prepost_mcp.script_tools.normalize_outcome", lambda *args: normalized)
    monkeypatch.setattr(service, "prepare_native_program", lambda *a, **kw: dict(job_id="p", data=dict(sha256="h")))
    monkeypatch.setattr(service, "execute_native_program", lambda *a, **kw: dict(job_directory=str(tmp_path)))
    result = JobResult.model_validate(service.run_script("command", "top"))
    assert result.status == ("partial" if log_present else "unverified")
    assert result.warnings == normalized.warnings
    assert result.checks == normalized.checks
    assert not result.execution_accepted


def test_legacy_partial_with_warning_does_not_fail_when_wrapping_native_echo(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))
    (tmp_path / "lspost.msg").write_bytes(b"top\n")
    monkeypatch.setattr(service, "prepare_native_program", lambda *a, **kw: dict(job_id="p", data=dict(sha256="h")))
    monkeypatch.setattr(service, "execute_native_program", lambda *a, **kw: dict(
        status="partial", data=dict(exported=1), warnings=["Image missing"], job_directory=str(tmp_path)))
    result = JobResult.model_validate(service.run_script("command", "top"))
    assert result.status == "partial"
    assert result.warnings == ("Image missing",)
    assert result.data["native_echo"]["text"] == "top\n"
