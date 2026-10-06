"""Reject remote/device inputs before any filesystem probing (no real network)."""
import os
from pathlib import Path, PureWindowsPath

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service

BS = chr(92)
PREFIX = BS * 2
HOST = "path-probe.invalid"
REMOTE = [
    PREFIX + HOST + BS + "share" + BS + "m.k", "//" + HOST + "/share/m.k",
    BS + "/" + HOST + "/share/m.k", "/" + BS + HOST + BS + "share" + BS + "m.k",
    PREFIX + "?" + BS + "UNC" + BS + HOST + BS + "share" + BS + "m.k",
    "//?/UNC/" + HOST + "/share/m.k",
    PREFIX + "?" + BS + "unc" + BS + HOST + BS + "share" + BS + "m.k",
    PREFIX + "?" + BS + "GLOBALROOT" + BS + "Device" + BS + "Mup" + BS + HOST + BS + "m.k",
    PREFIX + "." + BS + "UNC" + BS + HOST + BS + "share" + BS + "m.k",
    PREFIX + "." + BS + "GLOBALROOT" + BS + "Device" + BS + "Mup" + BS + HOST + BS + "m.k",
    PREFIX + "." + BS + "pipe" + BS + "probe", PREFIX + "." + BS + "CON",
]
DEVICES = ["CON", "NUL", "COM1", "CONIN$", "AUX.k"]


class ProbeReachedFilesystem(BaseException):
    pass


@pytest.fixture
def deny_unsafe_io(monkeypatch):
    """Trip before the OS; BaseException cannot be swallowed as an expected IO error."""
    hits = []

    def unsafe(value):
        try:
            text = os.fsdecode(os.fspath(value))
        except TypeError:
            return False
        return text.replace("/", BS).startswith(PREFIX) or PureWindowsPath(text).is_reserved()

    def wrap(owner, name):
        original = getattr(owner, name, None)
        if original is None:
            return

        def checked(value, *args, **kwargs):
            if unsafe(value):
                hits.append(name)
                raise ProbeReachedFilesystem(name)
            return original(value, *args, **kwargs)
        monkeypatch.setattr(owner, name, checked)

    for name in ["resolve", "stat", "lstat", "open"]:
        wrap(Path, name)
    for name in ["stat", "lstat", "open", "scandir"]:
        wrap(os, name)
    if os.name == "nt":
        import nt
        import ntpath

        wrap(nt, "_getfinalpathname")
        wrap(ntpath, "_getfinalpathname")
    return hits


@pytest.mark.parametrize("entry", ["input_path", "check_keyword_includes", "inspect_keyword_deck"])
@pytest.mark.parametrize("value", REMOTE + DEVICES, ids=["remote-" + str(n) for n in range(12)] + DEVICES)
def test_network_and_devices_never_reach_filesystem(tmp_path, deny_unsafe_io, entry, value):
    settings = Settings(tmp_path)
    with pytest.raises(ValueError, match="Network|device"):
        if entry == "input_path":
            settings.input_path(value)
        elif entry == "check_keyword_includes":
            settings.check_keyword_includes(Path(value))
        else:
            Service(settings).inspect_keyword_deck(value)
    assert deny_unsafe_io == []


def test_guard_interceptor_is_active(deny_unsafe_io):
    for call in [lambda: Path(REMOTE[0]).resolve(), lambda: os.stat(REMOTE[0])]:
        with pytest.raises(ProbeReachedFilesystem):
            call()
    assert len(deny_unsafe_io) == 2


def test_local_input_and_keyword_preflight_still_work(tmp_path, deny_unsafe_io):
    path = tmp_path / "local.k"
    path.write_text("*KEYWORD\n*END\n", encoding="utf8")
    settings = Settings(tmp_path)
    assert settings.input_path("local.k") == path
    assert settings.input_path(str(path)) == path
    settings.check_keyword_includes(path)
    assert deny_unsafe_io == []


def test_remote_base_cannot_bypass_raw_value_check(tmp_path, deny_unsafe_io):
    settings = Settings(tmp_path)
    with pytest.raises(ValueError, match="Network|device"):
        # Forward separators preserve a UNC base on both Windows and POSIX;
        # a backslash-only string has parent '.' on POSIX.
        settings.input_path("m.k", base=Path(REMOTE[1]).parent)
    assert deny_unsafe_io == []
