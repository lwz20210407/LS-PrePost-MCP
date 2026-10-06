"""I01 diagnostic decoding: exact characters, request deltas and raw evidence."""

import codecs
import json
import os
import sys
from pathlib import Path

import pytest

from ls_prepost_mcp.core.native_log import LogCursor, decode, decode_with_info, native_errors, read_delta
from ls_prepost_mcp.engine import BatchEngine, BatchJob, SessionEngine, SessionJob
from ls_prepost_mcp.engine.processes import OwnedProcess

MESSAGE = 'Output file "中文结果.png" not open\n'
ENCODINGS = [("utf-8", codecs.BOM_UTF8), ("utf-16-le", codecs.BOM_UTF16_LE),
             ("utf-16-be", codecs.BOM_UTF16_BE), ("utf-32-le", codecs.BOM_UTF32_LE),
             ("utf-32-be", codecs.BOM_UTF32_BE)]


@pytest.mark.parametrize("encoding,signature", ENCODINGS)
def test_bom_decoding_preserves_diagnostic_even_with_conflicting_override(monkeypatch, encoding, signature):
    monkeypatch.setenv("LSPP_NATIVE_LOG_ENCODING", "cp1252")
    text, info = decode_with_info(signature + MESSAGE.encode(encoding))
    assert text == MESSAGE and info == dict(encoding=encoding, lossy=False)
    assert native_errors(text) == [MESSAGE.strip()]


def test_native_locale_fallback_does_not_use_python_utf8_preference(monkeypatch):
    monkeypatch.delenv("LSPP_NATIVE_LOG_ENCODING", raising=False)
    monkeypatch.setattr("ls_prepost_mcp.core.native_log.locale.getencoding", lambda: "cp936")
    monkeypatch.setattr("ls_prepost_mcp.core.native_log.locale.getpreferredencoding", lambda *a: "utf-8")
    text, info = decode_with_info(MESSAGE.encode("gbk"))
    assert text == MESSAGE and info == dict(encoding="gbk", lossy=False)


def test_explicit_encoding_and_loss_are_visible(monkeypatch):
    monkeypatch.setenv("LSPP_NATIVE_LOG_ENCODING", "utf-16-le")
    assert decode(MESSAGE.encode("utf-16-le")) == MESSAGE
    text, info = decode_with_info(b"\xff", encoding="utf8")
    assert text == "\ufffd" and info == dict(encoding="utf-8", lossy=True)
    monkeypatch.setenv("LSPP_NATIVE_LOG_ENCODING", "not-a-codec")
    with pytest.raises(LookupError):
        decode(b"data")
    assert native_errors("\ufeffInvalid command already decoded!") == ["Invalid command already decoded!"]


@pytest.mark.parametrize("encoding,signature", ENCODINGS)
def test_delta_keeps_file_encoding_without_replaying_old_errors(tmp_path, encoding, signature):
    path = tmp_path / "native.log"
    path.write_bytes(signature + "Invalid command OLD!\n".encode(encoding))
    cursor = LogCursor.capture(path)
    with path.open("ab") as stream:
        stream.write(MESSAGE.encode(encoding))
    assert cursor.read_bytes() == MESSAGE.encode(encoding)
    assert cursor.read() == read_delta(path, cursor.offset, existed=True) == MESSAGE
    assert native_errors(cursor.read()) == [MESSAGE.strip()]


@pytest.mark.parametrize("encoding,signature", ENCODINGS + [("gbk", b"")])
def test_real_batch_zero_exit_with_encoded_diagnostic_fails(tmp_path, monkeypatch, encoding, signature):
    raw = signature + MESSAGE.encode(encoding)
    monkeypatch.setattr("ls_prepost_mcp.core.native_log.locale.getencoding", lambda: "cp936")
    monkeypatch.delenv("LSPP_NATIVE_LOG_ENCODING", raising=False)
    monkeypatch.setattr("ls_prepost_mcp.engine.batch.require_capability", lambda *a: {})
    monkeypatch.setattr("ls_prepost_mcp.engine.batch.native_environment", lambda *a, **kw: (dict(os.environ), {}))
    monkeypatch.setattr("ls_prepost_mcp.engine.batch.OwnedProcess", lambda args, **kwargs:
        OwnedProcess([sys.executable, "-c", "import sys;sys.stdout.buffer.write(" + repr(raw) + ")"], **kwargs))
    result = BatchEngine().run(BatchJob(Path(sys.executable), tmp_path / "run.cfile", tmp_path, 15))
    assert result.status == "failed" and result.data["returncode"] == 0
    assert MESSAGE.strip() in result.error["message"]
    assert (tmp_path / "stdout.log.raw").read_bytes() == raw
    assert (tmp_path / "stdout.log").read_text(encoding="utf8") == MESSAGE
    assert result.data["log_decoding"]["stdout.log"]["lossy"] is False


@pytest.mark.parametrize("encoding,signature", ENCODINGS)
def test_session_uses_bom_hint_for_only_this_request(tmp_path, encoding, signature):
    log = tmp_path / "native.log"
    log.write_bytes(signature + "Invalid command OLD!\n".encode(encoding))

    def submit():
        with log.open("ab") as stream:
            stream.write(MESSAGE.encode(encoding))
        (tmp_path / "complete.json").write_text(json.dumps(dict(job_id=tmp_path.name, ok=True)))

    result = SessionEngine().run(SessionJob("test", tmp_path, 1, submit, lambda: True, log=log))
    assert result.status == "failed" and result.error["message"] == MESSAGE.strip()
    assert (tmp_path / "native-session.log").read_bytes() == MESSAGE.encode(encoding)
    info = json.loads((tmp_path / "native-session-log.json").read_text())
    assert info["encoding"] == encoding and info["lossy"] is False


@pytest.mark.parametrize("encoding,expected_error", [("utf8", "UnicodeError"), ("not-a-codec", "LookupError")])
def test_session_loss_or_bad_configuration_is_uncertain_and_preserves_raw(tmp_path, monkeypatch, encoding, expected_error):
    monkeypatch.setenv("LSPP_NATIVE_LOG_ENCODING", encoding)
    log = tmp_path / "native.log"

    def submit():
        log.write_bytes(b"\xff")
        (tmp_path / "complete.json").write_text(json.dumps(dict(job_id=tmp_path.name, ok=True)))

    result = SessionEngine().run(SessionJob("test", tmp_path, 1, submit, lambda: True, log=log))
    assert result.status == "unverified" and result.error["type"] == expected_error
    assert (tmp_path / "native-session.log").read_bytes() == b"\xff"
    assert result.data["replayed"] is False


def test_batch_loss_preserves_both_raw_streams_and_refuses_verification(tmp_path, monkeypatch):
    monkeypatch.setenv("LSPP_NATIVE_LOG_ENCODING", "utf8")
    monkeypatch.setattr("ls_prepost_mcp.engine.batch.require_capability", lambda *a: {})
    monkeypatch.setattr("ls_prepost_mcp.engine.batch.native_environment", lambda *a, **kw: (dict(os.environ), {}))
    code = "import sys;sys.stdout.buffer.write(b'\\xff');sys.stderr.buffer.write(b'raw error')"
    monkeypatch.setattr("ls_prepost_mcp.engine.batch.OwnedProcess", lambda args, **kwargs:
        OwnedProcess([sys.executable, "-c", code], **kwargs))
    job = BatchJob(Path(sys.executable), tmp_path / "run.cfile", tmp_path, 15,
                   verify=lambda _: pytest.fail("Lossy logs cannot authorize verification"))
    result = BatchEngine().run(job)
    assert result.status == "failed" and result.error["type"] == "UnicodeError"
    assert result.data["log_decoding"]["stdout.log"]["lossy"] is True
    assert (tmp_path / "stdout.log.raw").read_bytes() == b"\xff"
    assert (tmp_path / "stderr.log.raw").read_bytes() == b"raw error"
