"""Include preflight for native readers (tasks.yaml I07 backend; consumed by I04 corpus runs)."""
import hashlib
import shutil
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck, preflight_includes


def _deck(root: Path, files: dict[str, bytes | str]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("ascii"))
    return root / "main.k"


def _kinds(report: dict) -> list[tuple[str, str]]:
    return [(p["kind"], p["severity"]) for p in report["problems"]]


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(root.rglob("*")) if p.is_file()}


def test_clean_tree_lists_every_file_with_digests_in_reading_order(tmp_path: Path) -> None:
    main = _deck(tmp_path, {"main.k": "*KEYWORD\n*INCLUDE\nparts/a.k\n*INCLUDE\nb.k\n*END\n",
                            "parts/a.k": "*NODE\n", "b.k": "*PART\n"})
    before = _snapshot(tmp_path)
    report = preflight_includes(main)
    assert report["ok"] and report["problems"] == [] and report["read_only"]
    assert [(f["relative"], f["role"]) for f in report["files"]] == [
        ("main.k", "main"), ("parts/a.k", "include"), ("b.k", "include")]
    for entry in report["files"]:
        data = Path(entry["path"]).read_bytes()
        assert entry["sha256"] == hashlib.sha256(data).hexdigest() and entry["size"] == len(data)
    joined = "\n".join(f["sha256"] for f in report["files"]).encode("ascii")
    assert report["tree_sha256"] == hashlib.sha256(joined).hexdigest()
    assert _snapshot(tmp_path) == before and report["counts"] == {"files": 3, "errors": 0, "warnings": 0}


def test_tree_digest_follows_content_not_location(tmp_path: Path) -> None:
    main = _deck(tmp_path / "one", {"main.k": "*INCLUDE\na.k\n", "a.k": "*NODE\n"})
    shutil.copytree(tmp_path / "one", tmp_path / "two")
    first = preflight_includes(main)["tree_sha256"]
    assert preflight_includes(tmp_path / "two" / "main.k")["tree_sha256"] == first
    (tmp_path / "two" / "a.k").write_bytes(b"*NODE\n 1,0,0,0\n")
    assert preflight_includes(tmp_path / "two" / "main.k")["tree_sha256"] != first


def test_missing_includes_are_errors_with_location_and_hint(tmp_path: Path) -> None:
    main = _deck(tmp_path, {"main.k": "*KEYWORD\n*INCLUDE\nnot_here.k\n*INCLUDE\nD:\\cases\\mesh.k\n"
                                      "*INCLUDE\n/path/to/test.k\n*INCLUDE\ncases/{{ geometry }}.k\n"})
    report = preflight_includes(main)
    assert not report["ok"] and _kinds(report) == [("missing", "error")] * 4
    first = report["problems"][0]
    assert (first["relative"], first["line"], first["name_line"], first["keyword"], first["name"]) == (
        "main.k", 2, 3, "*INCLUDE", "not_here.k")
    assert [p["hint"] for p in report["problems"]] == ["not_found", "absolute_path", "absolute_path", "placeholder"]


def test_include_without_a_file_card_is_a_warning(tmp_path: Path) -> None:
    # "${...}" starts with "$", so LS-DYNA reads it as a comment and the block names no file;
    # R11 then skips the block without a message.
    main = _deck(tmp_path, {"main.k": "*INCLUDE\n${GEOMETRY_KEYWORD_PATH}\n*INCLUDE\n$ nothing\n*END\n"})
    report = preflight_includes(main)
    assert _kinds(report) == [("empty_include", "warning")] * 2 and report["ok"]
    assert [(p["line"], p["hint"]) for p in report["problems"]] == [(1, "placeholder"), (3, "no_file_card")]


def test_cycle_is_an_error_and_repeated_include_a_warning(tmp_path: Path) -> None:
    main = _deck(tmp_path, {"main.k": "*INCLUDE\na.k\n*INCLUDE\nb.k\n*INCLUDE\nb.k\n",
                            "a.k": "*INCLUDE\nmain.k\n", "b.k": "*NODE\n"})
    report = preflight_includes(main)
    assert _kinds(report) == [("cycle", "error"), ("repeated", "warning")]
    assert report["problems"][0]["relative"] == "a.k" and not report["ok"]


def test_ambiguous_include_names_every_candidate(tmp_path: Path) -> None:
    main = _deck(tmp_path, {"main.k": "*INCLUDE\nsub/a.k\n", "sub/a.k": "*INCLUDE\nb.k\n",
                            "sub/b.k": "*NODE\n", "b.k": "*PART\n"})
    report = preflight_includes(main)
    assert report["ok"] and _kinds(report) == [("ambiguous", "warning")]
    problem = report["problems"][0]
    assert problem["rule"] == "including_dir" and Path(problem["path"]) == tmp_path / "sub" / "b.k"
    assert len(problem["candidates"]) == 2


def test_opaque_target_is_hashed_but_not_followed(tmp_path: Path) -> None:
    main = _deck(tmp_path, {"main.k": "*INCLUDE_BINARY\nrestart.bin\n", "restart.bin": b"\x00\x01binary"})
    report = preflight_includes(main)
    assert report["ok"] and _kinds(report) == [("not_followed", "warning")]
    assert report["files"][-1]["role"] == "opaque"
    assert report["files"][-1]["sha256"] == hashlib.sha256(b"\x00\x01binary").hexdigest()


def test_unreadable_include_is_reported_and_the_rest_still_checked(tmp_path: Path) -> None:
    main = _deck(tmp_path, {"main.k": "*INCLUDE\nbad.k\n*INCLUDE\ngood.k\n*INCLUDE\nlost.k\n",
                            "bad.k": b"*NODE\x00\x00", "good.k": "*NODE\n"})
    report = preflight_includes(main)
    assert _kinds(report) == [("unreadable", "error"), ("missing", "error")]
    assert "NUL bytes" in report["problems"][0]["reason"]
    assert [f["relative"] for f in report["files"]] == ["main.k", "good.k"]
    with pytest.raises(ValueError, match="NUL bytes"):  # ordinary loading is unchanged
        KeywordDeck.load(main)


def test_include_count_limit_is_reported_not_raised(tmp_path: Path) -> None:
    main = _deck(tmp_path, {"main.k": "*INCLUDE\na.k\n*INCLUDE\nb.k\n", "a.k": "*NODE\n", "b.k": "*PART\n"})
    report = preflight_includes(main, max_files=2)
    assert _kinds(report) == [("limit", "error")] and report["problems"][0]["name"] == "b.k"
    with pytest.raises(ValueError, match="More than 2 include files"):
        KeywordDeck.load(main, max_files=2)


def test_missing_search_directory_warns_and_utf16_include_is_an_error(tmp_path: Path) -> None:
    wide = b"\xff\xfe" + "*NODE\n".encode("utf-16-le")  # R11 stops with Error 10450 on such a file
    main = _deck(tmp_path, {"main.k": "*INCLUDE_PATH\nno_such_dir\n*INCLUDE\nw.k\n", "w.k": wide})
    report = preflight_includes(main)
    assert not report["ok"] and _kinds(report) == [("missing_search_dir", "warning"), ("utf16_text", "error")]
    assert report["problems"][1]["relative"] == "w.k"


def test_network_names_are_reported_without_touching_the_file_system(tmp_path: Path, monkeypatch) -> None:
    main = _deck(tmp_path, {"main.k": "*INCLUDE_PATH\n//host/dir\n*INCLUDE\n\\\\host\\share\\a.k\n"
                                      "*INCLUDE\nlocal.k\n", "local.k": "*NODE\n"})
    queried: list[str] = []
    for method in ("is_file", "is_dir", "exists", "stat"):
        original = getattr(Path, method)
        monkeypatch.setattr(Path, method, lambda self, *a, _o=original, **k: queried.append(str(self)) or _o(self, *a, **k))
    report = preflight_includes(main)
    assert _kinds(report) == [("network_path", "error"), ("network_path", "error")]
    assert [f["relative"] for f in report["files"]] == ["main.k", "local.k"]
    assert any(q.endswith("local.k") for q in queried) and not [q for q in queried if "host" in q]


def test_a_failing_lookup_stays_on_its_own_reference(tmp_path: Path, monkeypatch) -> None:
    main = _deck(tmp_path, {"main.k": "*INCLUDE\nlocked.k\n*INCLUDE\ngood.k\n", "good.k": "*NODE\n"})
    before = _snapshot(tmp_path)
    is_file = Path.is_file

    def denied(self: Path) -> bool:
        if self.name == "locked.k":
            raise PermissionError(13, "Access is denied", str(self))
        return is_file(self)

    monkeypatch.setattr(Path, "is_file", denied)
    report = preflight_includes(main)
    assert _kinds(report) == [("unreadable", "error")] and report["problems"][0]["name"] == "locked.k"
    assert [f["relative"] for f in report["files"]] == ["main.k", "good.k"] and report["tree_sha256"]
    assert _snapshot(tmp_path) == before
    with pytest.raises(PermissionError):  # ordinary loading is unchanged
        KeywordDeck.load(main)


def test_empty_include_in_a_repeated_file_is_reported_once(tmp_path: Path) -> None:
    main = _deck(tmp_path, {"main.k": "*INCLUDE\na.k\n*INCLUDE\na.k\n*INCLUDE\na.k\n", "a.k": "*INCLUDE\n$ off\n"})
    report = preflight_includes(main)
    assert _kinds(report) == [("repeated", "warning"), ("repeated", "warning"), ("empty_include", "warning")]


def test_files_follow_reading_order_including_opaque_targets(tmp_path: Path) -> None:
    main = _deck(tmp_path, {"main.k": "*INCLUDE_BINARY\nr.bin\n*INCLUDE\na.k\n", "r.bin": b"\x00",
                            "a.k": "*NODE\n"})
    report = preflight_includes(main)
    assert [(f["relative"], f["role"]) for f in report["files"]] == [
        ("main.k", "main"), ("r.bin", "opaque"), ("a.k", "include")]
    assert report["tree_sha256_version"] == 1


def test_too_deep_a_tree_is_a_limit_problem(tmp_path: Path, monkeypatch) -> None:
    from ls_prepost_mcp.domain.model import preflight

    def too_deep(*args, **kwargs):
        raise RecursionError("maximum recursion depth exceeded")

    main = _deck(tmp_path, {"main.k": "*INCLUDE\na.k\n", "a.k": "*NODE\n"})
    monkeypatch.setattr(preflight, "KeywordDeck", too_deep)
    report = preflight_includes(main)
    assert _kinds(report) == [("limit", "error")] and [f["role"] for f in report["files"]] == ["main"]


def test_unreadable_main_deck_is_a_report_not_an_exception(tmp_path: Path) -> None:
    report = preflight_includes(tmp_path / "absent.k")
    assert not report["ok"] and report["files"] == [] and report["tree_sha256"] is None
    assert _kinds(report) == [("unreadable", "error")]
