"""I01: engine-owned logs cannot overwrite declared outputs or dependencies."""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.engine import BatchEngine, BatchJob
from ls_prepost_mcp.programs import RESERVED
from ls_prepost_mcp.service import Service

LOG_NAMES = ("stdout.log.raw", "stderr.log.raw", "native-session.log", "native-session-log.json")


@pytest.mark.parametrize("name", [name for base in LOG_NAMES for name in (base, base.upper())])
@pytest.mark.parametrize("role", ["output", "dependency"])
def test_native_log_names_are_rejected_before_preparation(tmp_path, name, role):
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    arguments = {}
    if role == "output":
        arguments["outputs"] = [dict(name=name, kind="text")]
    else:
        source = tmp_path / name
        source.write_bytes(b"user data must remain intact")
        arguments["dependencies"] = [dict(path=str(source), name=name)]
    with pytest.raises(ValueError, match="reserved"):
        service.prepare_native_program("command", code="top", **arguments)
    assert not (tmp_path / "work/jobs").exists()
    if role == "dependency":
        assert source.read_bytes() == b"user data must remain intact"


def test_every_batch_engine_created_log_is_reserved(tmp_path, monkeypatch):
    import ls_prepost_mcp.engine.batch as batch

    cfile = tmp_path / "commands.cfile"
    cfile.write_text("top\n")
    before = {path.name for path in tmp_path.iterdir()}
    process = SimpleNamespace(pid=123, returncode=0, communicate=lambda **kwargs: (b"stdout\n", b"stderr\n"))
    monkeypatch.setattr(batch, "OwnedProcess", lambda *a, **k: nullcontext(SimpleNamespace(process=process, mechanism="fake")))
    monkeypatch.setattr(batch, "require_capability", lambda *a, **k: {})
    monkeypatch.setattr(batch, "native_environment", lambda *a, **k: ({}, {}))
    result = BatchEngine().run(BatchJob(tmp_path / "fake.exe", cfile, tmp_path, 1))
    assert result.status == "unverified" and result.error is None
    created = {path.name for path in tmp_path.iterdir() if path.is_file()} - before
    assert created and created <= RESERVED
