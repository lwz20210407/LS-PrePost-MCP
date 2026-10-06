import subprocess
from unittest.mock import MagicMock, patch

import pytest

from ls_prepost_mcp.runner import decode, execute


@pytest.fixture(autouse=True)
def configured_native_preferences(tmp_path, monkeypatch):
    config = tmp_path / "user-lsppconf"
    config.write_text("*\nconsent = YES\n")
    monkeypatch.setenv("LSPP_CONFIG_SOURCE", str(config))


def test_runner_owns_cwd_and_never_uses_shell(tmp_path):
    process = MagicMock(pid=42, returncode=0)
    process.communicate.return_value = (b"hello", b"")
    owned = MagicMock(process=process, mechanism="fixture")
    owned.__enter__.return_value = owned
    with patch("ls_prepost_mcp.engine.batch.OwnedProcess", return_value=owned) as popen:
        result = execute(tmp_path / "lspp", tmp_path / "commands.cfile", tmp_path, timeout=1, graphics=False)
    args, kwargs = popen.call_args
    assert args[0][-1] == "-nographics"
    assert kwargs["cwd"] == tmp_path
    assert kwargs.get("shell", False) is False
    assert kwargs["env"]["TEMP"] == str(tmp_path / "tmp")
    assert result["returncode"] == 0
    assert (tmp_path / "stdout.log").read_text() == "hello"


def test_timeout_reaps_owned_process_and_keeps_logs(tmp_path):
    process = MagicMock(pid=424242, returncode=-9)
    process.communicate.side_effect = [subprocess.TimeoutExpired("lspp", 1, output=b"partial"), (b"partial", b"timeout")]
    owned = MagicMock(process=process, mechanism="fixture")
    owned.__enter__.return_value = owned
    owned.stop.side_effect = process.kill
    with patch("ls_prepost_mcp.engine.batch.OwnedProcess", return_value=owned):
        result = execute(tmp_path / "lspp", tmp_path / "commands.cfile", tmp_path, timeout=1, graphics=False)
    assert result["timed_out"]
    process.kill.assert_called_once()
    assert (tmp_path / "stdout.log").read_text() == "partial"
    assert decode(b"\xff") == "\ufffd"
