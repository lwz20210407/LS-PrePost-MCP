"""M3 keyword-engine tools confine every file the engine touches to the allowed roots (round-11 ce41).

The guard is enforced inside the engine (domain.model.access), so it also covers includes added by
edits, the reload after saving, and decks that fail later (recursion) after their includes were read.
"""
import json
import os
import sys
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model import preflight_includes
from ls_prepost_mcp.service import Service

MODEL = ("*KEYWORD\n*NODE\n       1             0.0             0.0             0.0\n"
         "*PART\ncube\n         1         1         1\n")
SECRET = "*KEYWORD\n$ SECRET-MARKER\n*NODE\n    2001             0.0             0.0             9.0\n"
UNC = ["//probe-host/share/x.k", "\\/probe-host/share/x.k", "/\\probe-host\\share\\x.k",
       "\\\\?\\UNC\\probe-host\\share\\x.k", "\\\\.\\pipe\\probe-host"]


@pytest.fixture()
def roots(tmp_path: Path) -> tuple[Service, Path, Path]:
    workspace, allowed, outside = tmp_path / "ws", tmp_path / "allowed", tmp_path / "outside"
    for directory in (workspace, allowed, outside):
        directory.mkdir()
    (outside / "secret.k").write_bytes(SECRET.encode("ascii"))
    return Service(Settings(workspace, None, (allowed,))), allowed, outside


class NetworkTouched(BaseException):
    """Raised (not caught by ``except Exception``) when code under test touches the probe host."""


@pytest.fixture()
def no_host(monkeypatch) -> list[str]:
    """Record every path the code stats, resolves or opens, and stop the test before a path naming
    the probe host reaches the operating system: a regression must fail, never contact a host."""
    import builtins
    import io

    seen: list[str] = []

    def guard(original, describe):
        def wrapped(target, *args, **kwargs):
            text = describe(target)
            seen.append(text)
            if "probe-host" in text.lower():
                raise NetworkTouched(text)
            return original(target, *args, **kwargs)
        return wrapped

    for method in ("is_file", "is_dir", "exists", "stat", "lstat", "resolve", "read_bytes", "open", "iterdir"):
        monkeypatch.setattr(Path, method, guard(getattr(Path, method), str))
    for module, name in ((os, "stat"), (os, "lstat"), (os, "open"), (os, "scandir"), (os, "listdir"),
                         (os.path, "realpath"), (os.path, "exists"), (os.path, "lexists"), (os.path, "isfile"),
                         (os.path, "isdir"), (builtins, "open"), (io, "open")):
        monkeypatch.setattr(module, name, guard(getattr(module, name), lambda t: str(t)))
    if sys.platform == "win32":
        import nt
        monkeypatch.setattr(nt, "_getfinalpathname", guard(nt._getfinalpathname, lambda t: str(t)))
    return seen


def _main(allowed: Path, tail: str) -> Path:
    path = allowed / "main.k"
    path.write_bytes((MODEL + tail + "*END\n").encode("ascii"))
    return path


def _calls(service: Service, main: Path, edits: list | None = None) -> dict:
    edits = edits or [{"op": "set_parameter", "name": "x", "value": 1}]
    return {"model_info": lambda: service.model_info(str(main)),
            "check_model": lambda: service.check_model(str(main)),
            "edit_keywords": lambda: service.edit_keywords(str(main), edits)}


def _leaked(service: Service) -> list[Path]:
    return [p for p in service.settings.workspace.rglob("*") if p.is_file() and b"SECRET-MARKER" in p.read_bytes()]


@pytest.mark.parametrize("include", ["../outside/secret.k", "ABSOLUTE", "../outside/absent.k", "OTHER_DRIVE"])
def test_includes_outside_the_roots_fail_whether_or_not_they_exist(roots, include: str) -> None:
    service, allowed, outside = roots
    if include == "OTHER_DRIVE":  # drive-relative name on another drive, e.g. D:Windows/win.ini
        if sys.platform != "win32":
            pytest.skip("drive letters are a Windows feature")
        include = ("E:" if str(allowed).upper().startswith("D:") else "D:") + "Windows/win.ini"
    name = str(outside / "secret.k") if include == "ABSOLUTE" else include
    main = _main(allowed, f"*INCLUDE\n{name}\n")
    for tool, call in _calls(service, main).items():
        result = call()
        assert result["status"] == "failed", tool
        assert "outside the allowed roots" in result["error"]["message"] and "SECRET" not in json.dumps(result)
    assert _leaked(service) == []  # edit_keywords used to copy the outside file into its job directory


@pytest.mark.parametrize("include", UNC)
def test_network_includes_fail_without_touching_the_network(roots, no_host, include: str) -> None:
    service, allowed, _ = roots
    main = _main(allowed, f"*INCLUDE\n{include}\n")
    for tool, call in _calls(service, main).items():
        result = call()
        assert result["status"] == "failed" and "Network path" in result["error"]["message"], tool
    assert any(s.endswith("main.k") for s in no_host) and not [s for s in no_host if "probe-host" in s]


@pytest.mark.parametrize("edit", [
    {"op": "insert", "text": "*INCLUDE\n../outside/secret.k\n"},
    {"op": "insert", "text": "*INCLUDE_PATH\n../outside\n*INCLUDE\nsecret.k\n"},
    {"op": "insert", "text": "*INCLUDE\n//probe-host/share/x.k\n"},
])
def test_includes_added_by_an_edit_are_confined_too(roots, no_host, edit: dict) -> None:
    pytest.importorskip("ansys.dyna.core")
    service, allowed, _ = roots
    result = service.edit_keywords(str(_main(allowed, "")), [edit])
    assert result["status"] == "failed" and "SECRET" not in json.dumps(result)
    assert _leaked(service) == [] and not [s for s in no_host if "probe-host" in s]


def test_a_line_break_cannot_smuggle_a_keyword_into_a_field(roots) -> None:
    pytest.importorskip("ansys.dyna.core")
    service, allowed, _ = roots
    edit = {"op": "set", "keyword": "*PART", "match": {"pid": 1}, "field": "heading",
            "value": "x\n*INCLUDE\n../outside/secret.k"}
    result = service.edit_keywords(str(_main(allowed, "")), [edit])
    assert result["status"] == "failed" and "line breaks" in json.dumps(result)
    assert _leaked(service) == []


def test_a_deck_that_fails_later_never_reached_its_network_include(roots, no_host) -> None:
    service, allowed, _ = roots
    deep = "R deep    " + "+".join(["1"] * 3000) + "\n"
    main = _main(allowed, "*INCLUDE\n//probe-host/share/x.k\n*PARAMETER_EXPRESSION\n" + deep)
    result = service.model_info(str(main))
    assert result["status"] == "failed" and not [s for s in no_host if "probe-host" in s]


def test_includes_inside_the_allowed_roots_still_work(roots) -> None:
    pytest.importorskip("ansys.dyna.core")
    service, allowed, _ = roots
    (allowed / "sub").mkdir()
    (allowed / "sub" / "part.k").write_bytes(b"*NODE\n       2             1.0             0.0             0.0\n")
    main = _main(allowed, "*INCLUDE\nsub/part.k\n")
    assert service.model_info(str(main))["status"] == "succeeded"
    edited = service.edit_keywords(str(main), [{"op": "insert", "text": "*INCLUDE\nsub/part.k\n"}])
    assert edited["status"] == "succeeded"


def test_a_network_main_deck_is_refused_before_it_is_resolved(roots, no_host) -> None:
    service, _, _ = roots
    with pytest.raises(ValueError, match="Network path"):
        service.model_info("\\\\probe-host\\share\\m.k")
    assert not [s for s in no_host if "probe-host" in s]


@pytest.mark.skipif(sys.platform != "win32", reason="extended-length paths are a Windows feature")
def test_preflight_resolves_dot_dot_under_an_extended_length_main_path(tmp_path: Path) -> None:
    (tmp_path / "deck").mkdir()
    (tmp_path / "shared.k").write_bytes(b"*NODE\n")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "mat.k").write_bytes(b"*PART\n")
    (tmp_path / "deck" / "main.k").write_bytes(b"*INCLUDE_PATH\n../lib\n*INCLUDE\n../shared.k\n*INCLUDE\nmat.k\n")
    plain = preflight_includes(tmp_path / "deck" / "main.k")
    extended = preflight_includes("\\\\?\\" + os.path.abspath(tmp_path / "deck" / "main.k"))
    assert plain["ok"] and extended["ok"] and extended["problems"] == []
    assert extended["tree_sha256"] == plain["tree_sha256"] and extended["counts"]["files"] == 3


@pytest.mark.parametrize("main", [r"\\?\UNC/probe-host/share/m.k",
                                  r"\\?\GLOBALROOT\Device\Mup\probe-host\share\m.k",
                                  "//?/UNC/probe-host/share/m.k"])
def test_extended_length_network_spellings_of_the_main_deck_are_refused(roots, no_host, main: str) -> None:
    service, _, _ = roots
    with pytest.raises(ValueError, match="Network path"):
        service.model_info(main)


@pytest.mark.parametrize("edit", [
    {"op": "create_set", "kind": "node", "ids": [1], "title": "s\n*CONTROL_TERMINATION\n1.0"},
    {"op": "insert", "card": {"keyword": "*MAT_ELASTIC_TITLE",
                              "fields": {"title": "m\n*CONTROL_TERMINATION", "mid": 5, "ro": 1.0, "e": 1.0, "pr": 0.3}}},
])
def test_titles_cannot_add_keywords(roots, edit: dict) -> None:
    pytest.importorskip("ansys.dyna.core")
    service, allowed, _ = roots
    result = service.edit_keywords(str(_main(allowed, "")), [edit])
    assert result["status"] == "failed" and "line breaks" in json.dumps(result)
