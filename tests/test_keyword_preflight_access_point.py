"""Review02 P1-4: confinement belongs at preflight, not only at MCP callers."""

from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model import access
from ls_prepost_mcp.service import Service


def outside_tree(tmp_path, content="plain"):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    secret = outside / "secret.k"
    second = outside / "second.k"
    second.write_text("*KEYWORD\n*NODE\n1,0,0,0\n*END\n")
    text = "*KEYWORD\n*INCLUDE\nsecond.k\n*END\n"
    secret.write_bytes(
        text.encode("utf16")
        if content == "utf16"
        else b"\x00\xff\x01"
        if content == "binary"
        else text.encode()
    )
    main = allowed / "main.k"
    main.write_text("*KEYWORD\n*INCLUDE\n" + secret.as_posix() + "\n*END\n")
    return main, secret, second


@pytest.mark.parametrize("entry", ["native_keyword_report", "check_keyword_includes"])
@pytest.mark.parametrize("content", ["plain", "utf16", "binary"])
def test_settings_preflight_never_reads_denied_include_before_rejecting(
    tmp_path, monkeypatch, entry, content
):
    main, secret, second = outside_tree(tmp_path, content)
    settings = Settings(tmp_path / "work", allowed_roots=(main.parent,))
    opened = []
    original = Path.open

    def watched(path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if path in (secret, second) and "r" in mode:
            opened.append(path.name)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", watched)
    with pytest.raises((ValueError, PermissionError), match="outside"):
        getattr(settings, entry)(main)
    assert opened == [], f"Denied files were opened before confinement: {opened}"


def test_public_inspect_entry_cannot_depend_on_an_outer_model_guard(tmp_path, monkeypatch):
    main, secret, second = outside_tree(tmp_path)
    service = Service(Settings(tmp_path / "work", allowed_roots=(main.parent,)))
    opened = []
    original = Path.open

    def watched(path, *args, **kwargs):
        if path in (secret, second):
            opened.append(path.name)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", watched)
    with pytest.raises((ValueError, PermissionError), match="outside"):
        service.inspect_keyword_deck(str(main))
    assert not opened


def test_internal_preflight_guard_must_not_weaken_a_stricter_existing_guard(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    main = root / "main.k"
    child = root / "child.k"
    main.write_text("*KEYWORD\n*INCLUDE\nchild.k\n*END\n")
    child.write_text("*KEYWORD\n*END\n")

    def narrower(path):
        if path == child:
            raise access.OutsideRoots("outer scope denies this child")

    settings = Settings(tmp_path / "work", allowed_roots=(root,))
    with access.confined(narrower), pytest.raises((ValueError, PermissionError), match="outer"):
        settings.native_keyword_report(main)


def test_denied_include_is_not_statted_after_the_preflight_error(tmp_path, monkeypatch):
    main, secret, second = outside_tree(tmp_path)
    settings = Settings(tmp_path / "work", allowed_roots=(main.parent,))
    probed = []
    original = Path.stat

    def watched(path, *args, **kwargs):
        if path in (secret, second):
            probed.append(path.name)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", watched)
    with pytest.raises((ValueError, PermissionError), match="outside"):
        settings.native_keyword_report(main)
    assert not probed
