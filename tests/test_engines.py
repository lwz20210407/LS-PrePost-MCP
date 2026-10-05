import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.core.native_log import LogCursor, read_delta
from ls_prepost_mcp.engine import BatchEngine, BatchJob, SessionEngine, SessionJob
from ls_prepost_mcp.engine.context import NativeContext
from ls_prepost_mcp.engine.environment import native_environment
from ls_prepost_mcp.engine.queue_transport import QueueTransport


@pytest.fixture(autouse=True)
def initialized_config_for_engine_unit_tests(tmp_path,monkeypatch):
    source=tmp_path/"user-lsppconf"
    source.write_text("*\npython_home = test-runtime\nconsent = YES\n")
    monkeypatch.setenv("LSPP_CONFIG_SOURCE",str(source))


def test_batch_clean_exit_requires_domain_verification(tmp_path, monkeypatch):
    process = MagicMock(pid=123, returncode=0)
    process.communicate.return_value = (b"", b"")
    monkeypatch.setattr("ls_prepost_mcp.engine.batch.subprocess.Popen", lambda *a, **kw: process)
    result = BatchEngine().run(BatchJob(tmp_path / "lspp", tmp_path / "job.cfile", tmp_path, 1))
    assert result.status == "unverified"
    assert result.data["configuration"]["source_modified"] is False
    assert (tmp_path / "native-config" / "lsppconf").is_file()


def test_batch_error_log_overrides_zero_exit_and_never_calls_verifier(tmp_path, monkeypatch):
    process = MagicMock(pid=123, returncode=0)

    def communicate(**kwargs):
        (tmp_path / "lspost.msg").write_text("Invalid command\n", encoding="utf8")
        return b"", b""

    process.communicate.side_effect = communicate
    monkeypatch.setattr("ls_prepost_mcp.engine.batch.subprocess.Popen", lambda *a, **kw: process)
    result = BatchEngine().run(BatchJob(tmp_path / "lspp", tmp_path / "job.cfile", tmp_path, 1,
                                      verify=lambda p: pytest.fail("Cannot verify failed execution")))
    assert result.status == "failed" and result.data["returncode"] == 0
    assert result.data["diagnostics"] == ["Invalid command"]


def test_environment_preserves_source_and_isolates_batch_and_session(tmp_path):
    source = tmp_path / "original"
    source.write_bytes(b"python_home = private-runtime\nconsent = YES\nworking_directory = old\n")
    original = source.read_bytes()
    paths = []
    for name in ("batch", "session"):
        directory = tmp_path / name
        directory.mkdir()
        env, config = native_environment(tmp_path / "lspp", directory, {"LSPP_CONFIG_SOURCE": str(source)})
        paths.append(env["LSTC_FILE"])
        assert env["TEMP"] == env["TMP"] == str(directory / "tmp")
        assert config["source_modified"] is False
        assert "python_home = private-runtime" in (directory / "native-config" / "lsppconf").read_text()
    assert paths[0] != paths[1] and source.read_bytes() == original


def test_missing_native_configuration_fails_before_private_config_or_launch(tmp_path):
    with pytest.raises(RuntimeError,match="LSPP_CONFIG_SOURCE"):
        native_environment(tmp_path/"lspp",tmp_path,{})
    assert not (tmp_path/"native-config").exists()


def test_service_reports_native_diagnostic_even_when_exit_code_is_zero(tmp_path,monkeypatch):
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.service import Service
    exe=tmp_path/"lspp.exe"
    exe.touch()
    service=Service(Settings(tmp_path,exe))
    monkeypatch.setattr("ls_prepost_mcp.service.execute",lambda *a,**kw:dict(
        returncode=0,timed_out=False,engine_status="failed",engine_error=dict(message="Invalid command actual_fault!")))
    result=service._native("probe",{})
    assert result["status"]=="failed" and result["error"]["message"]=="Invalid command actual_fault!"


def test_session_receipt_and_domain_validation(tmp_path):
    calls = []

    def submit():
        calls.append(1)
        (tmp_path / "complete.json").write_text(json.dumps(dict(job_id=tmp_path.name, ok=True)))

    result = SessionEngine().run(SessionJob("inspect", tmp_path, 1, submit, lambda: True,
        verify=lambda reply: JobResult(operation="inspect", job_id=reply["job_id"], status="succeeded")))
    assert result.status == "succeeded" and calls == [1]


@pytest.mark.parametrize("receipt", [dict(job_id="wrong", ok=True), dict(ok=True),
                                     dict(ok="true"), []])
def test_session_rejects_malformed_or_wrong_receipt_without_replay(tmp_path, receipt):
    calls = []
    if isinstance(receipt, dict) and "job_id" not in receipt and receipt.get("ok") == "true":
        receipt["job_id"] = tmp_path.name

    def submit():
        calls.append(1)
        (tmp_path / "complete.json").write_text(json.dumps(receipt))

    result = SessionEngine().run(SessionJob("inspect", tmp_path, 1, submit, lambda: True))
    assert result.status == "unverified" and result.error and calls == [1]


def test_session_stale_receipt_never_submits(tmp_path):
    (tmp_path / "complete.json").write_text("{}")
    result = SessionEngine().run(SessionJob("inspect", tmp_path, 1,
                                lambda: pytest.fail("Stale receipt must prevent send"), lambda: True))
    assert result.status == "failed" and result.data["submitted"] is False


def test_session_timeout_leaves_late_receipt_for_reconciliation(tmp_path):
    calls = []
    result = SessionEngine().run(SessionJob("edit", tmp_path, .001, lambda: calls.append(1), lambda: True))
    assert result.status == "unverified" and result.error["type"] == "TimeoutError"
    assert calls == [1] and result.data["replayed"] is False
    (tmp_path / "complete.json").write_text(json.dumps(dict(job_id=tmp_path.name, ok=True)))
    assert (tmp_path / "complete.json").exists()


def test_log_suffix_excludes_old_errors_and_detects_truncation(tmp_path):
    path = tmp_path / "lspost.msg"
    path.write_bytes(b"Invalid command\n")
    cursor = LogCursor.capture(path)
    with path.open("ab") as stream:
        stream.write(b"new result\n")
    assert cursor.read() == "new result\n"
    path.write_bytes(b"x")
    with pytest.raises(ValueError, match="truncated"):
        cursor.read()
    path.unlink()
    with pytest.raises(ValueError, match="disappeared"):
        cursor.read()
    with pytest.raises(ValueError, match="offset"):
        read_delta(path, -1)


def test_context_isolation_and_reset_after_exception():
    context = NativeContext()
    first, second = object(), object()
    with context.using(first):
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(lambda: context.executor).result() is None
        with pytest.raises(RuntimeError):
            with context.using(second):
                assert context.executor is second
                raise RuntimeError("validation failed")
        assert context.executor is first
    assert context.executor is None


def test_service_routes_typed_action_without_replacing_native(tmp_path, monkeypatch):
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.service import Service

    calls = []

    class Manager:
        def read(self, sid):
            return dict(state="ready", model_kind="keyword")

        def lock(self, sid):
            return nullcontext()

        def dispatch(self, sid, **request):
            calls.append(request)
            return dict(status="succeeded", data={})

        def save(self, *args):
            pass

        def journal(self, *args):
            pass

    service = Service(Settings(tmp_path))
    method = service._native.__func__
    monkeypatch.setattr(service, "_session_manager", Manager)
    result = service.gui_session_action("a" * 32, "inspect_model", {})
    assert result["status"] == "succeeded" and calls[0]["action"] == "inspect_model"
    assert service._native.__func__ is method and "_native" not in service.__dict__
    assert service._native_context.executor is None


def test_queue_authentication_duplicate_suppression_and_native_thread(tmp_path, monkeypatch):
    from ls_prepost_mcp.engine.embedded_queue import run

    original_cwd = os.getcwd()
    calls = []
    monkeypatch.setitem(sys.modules, "LsPrePost", SimpleNamespace(
        execute_command=lambda command: calls.append((command, threading.get_ident()))))
    sid, token, request_id = "a" * 32, "b" * 64, "c" * 32
    request = tmp_path / "requests" / request_id
    request.mkdir(parents=True)
    (request / "queue-job.json").write_text(json.dumps(dict(job_id=request_id, commands=["top"], python=[])))
    thread = threading.Thread(target=run, args=(tmp_path, sid, token))
    thread.start()
    try:
        deadline = time.monotonic() + 3
        while not (tmp_path / "ready.json").exists() and time.monotonic() < deadline:
            time.sleep(.01)
        ready = json.loads((tmp_path / "ready.json").read_text())
        QueueTransport(dict(ready, token="x" * 64), 1).submit(request_id)
        QueueTransport(ready, 1).submit(request_id)
        QueueTransport(ready, 1).submit(request_id)
        while not calls and time.monotonic() < deadline:
            time.sleep(.01)
        assert calls == [("top", thread.ident)]
        assert (request / "queue-started.json").is_file()
    finally:
        (tmp_path / "STOP").write_text("stop")
        thread.join(timeout=4)
        os.chdir(original_cwd)
        assert not thread.is_alive()
