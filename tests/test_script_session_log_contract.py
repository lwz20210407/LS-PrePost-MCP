"""A01/I01: consume real SessionEngine log metadata through every script channel."""

import codecs
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.engine import SessionEngine, SessionJob
from ls_prepost_mcp.service import Service


@pytest.mark.parametrize("language", ["command", "cfile", "scl", "python"])
@pytest.mark.parametrize("encoding", ["cp936", "utf-16-le"])
@pytest.mark.parametrize("bad", [False, True])
def test_script_consumes_engine_log_metadata_without_losing_encoding(tmp_path, monkeypatch, language, encoding, bad):
    monkeypatch.setenv("LSPP_NATIVE_LOG_ENCODING", encoding)
    source = tmp_path / "lspost.msg"
    prefix = (codecs.BOM_UTF16_LE if encoding == "utf-16-le" else b"") + "header\n".encode(encoding)
    source.write_bytes(prefix)
    directory = tmp_path / "request"
    directory.mkdir()
    text = ("Invalid command 模型!" if bad else "top 模型") + "\n"

    def submit():
        with source.open("ab") as stream:
            stream.write(text.encode(encoding))
        (directory / "complete.json").write_text(json.dumps(dict(job_id="request", ok=True)))

    engine = SessionEngine().run(SessionJob("script_probe", directory, 1, submit, lambda: True, log=source))
    assert (engine.status == "failed") == bad
    result = dict(status="failed" if bad else "succeeded", error=engine.error, request_id="request",
                  job_directory=str(directory), native_request=dict(job_directory=str(directory)), data={})
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "execute_gui_command", lambda *a, **k: result)
    monkeypatch.setattr(service, "prepare_native_program", lambda *a, **k: dict(job_id="request", data=dict(sha256="h")))
    monkeypatch.setattr(service, "execute_native_program", lambda *a, **k: result)
    outcome = service.run_script(language, "top", context="session", session_id="owned")
    assert outcome["status"] == ("failed" if bad else "succeeded"), outcome
    echo = outcome["data"]["native_echo"]
    assert echo["text"] == text and echo["offset"] == len(prefix)
    assert echo["encoding"] == codecs.lookup(encoding).name and echo["decoding_lossy"] is False
    assert bool(echo["errors"]) == bad
    assert Path(echo["full_text_path"]).read_bytes() == text.encode(encoding)


def test_lossy_session_log_cannot_wrap_a_success_as_verified(tmp_path, monkeypatch):
    (tmp_path / "native-session.log").write_bytes(b"top\n")
    (tmp_path / "native-session-log.json").write_text(json.dumps(dict(encoding="utf-8", lossy=True)))
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "execute_gui_command", lambda *a, **k: dict(
        status="succeeded", job_directory=str(tmp_path), request_id="probe", data={}))
    result = service.run_script("command", "top", context="session", session_id="owned")
    assert result["status"] == "unverified" and result["error"]["type"] == "UnicodeError"
