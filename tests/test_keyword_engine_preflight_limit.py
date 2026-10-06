"""Shared include-reference budget of the preflight (tasks.yaml I01, review P2-52f).

Every *INCLUDE-family name counts each time LS-DYNA reads it: repeated includes count again together
with the references inside them, unresolved and failed names count too. Past ``max_references``
nothing is resolved, stat'ed or read, so a deck that includes each layer twice cannot make the
preflight take exponential time.
"""
import builtins
import io
import os
import sys
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck, SourceFile, access, preflight_includes

THREE = {"main.k": "*KEYWORD\n*INCLUDE\na.k\n*INCLUDE\nb.k\n*INCLUDE\nc.k\n*END\n",
         "a.k": "*NODE\n", "b.k": "*PART\n", "c.k": "*NODE\n"}


class NetworkTouched(BaseException):
    """Raised (not caught by ``except Exception``) before a path naming the probe host reaches the OS."""


def _deck(root: Path, files: dict[str, bytes | str]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("ascii"))
    return root / "main.k"


def _kinds(report: dict) -> list[tuple[str, str]]:
    return [(p["kind"], p["severity"]) for p in report["problems"]]


@pytest.fixture()
def touched(monkeypatch) -> list[str]:
    """Record every path the code stats, resolves or opens; a probe-host path never reaches the OS."""
    seen: list[str] = []

    def spy(original):
        def wrapped(target, *args, **kwargs):
            text = str(target)
            seen.append(text)
            if "probe-host" in text.lower():
                raise NetworkTouched(text)
            return original(target, *args, **kwargs)
        return wrapped

    for method in ("is_file", "is_dir", "exists", "stat", "lstat", "resolve", "read_bytes", "open", "iterdir"):
        monkeypatch.setattr(Path, method, spy(getattr(Path, method)))
    for module, name in ((os, "stat"), (os, "lstat"), (os, "open"), (os, "scandir"), (os, "listdir"),
                         (os.path, "realpath"), (os.path, "exists"), (os.path, "lexists"), (os.path, "isfile"),
                         (os.path, "isdir"), (builtins, "open"), (io, "open")):
        monkeypatch.setattr(module, name, spy(getattr(module, name)))
    if sys.platform == "win32":  # ntpath.realpath uses its own binding of nt._getfinalpathname
        import ntpath
        monkeypatch.setattr(ntpath, "_getfinalpathname", spy(ntpath._getfinalpathname))
    return seen


@pytest.mark.parametrize("limit", [None, 4, 1000])
def test_references_within_the_limit_are_checked_as_before(tmp_path: Path, limit: int | None) -> None:
    main = _deck(tmp_path, THREE)
    report = preflight_includes(main, max_references=limit)
    assert report["ok"] and report["problems"] == []
    assert [f["relative"] for f in report["files"]] == ["main.k", "a.k", "b.k", "c.k"]
    assert (report["reference_count"], report["max_references"]) == (3, limit)
    assert "repeated" in report["reference_counting"] and "unresolved" in report["reference_counting"]
    assert report["tree_sha256"] == preflight_includes(main)["tree_sha256"]


def test_exactly_the_limit_is_allowed(tmp_path: Path) -> None:
    main = _deck(tmp_path, THREE)
    report = preflight_includes(main, max_references=3)
    assert report["ok"] and report["problems"] == [] and report["reference_count"] == 3
    assert len(report["references"]) == 3 and len(report["files"]) == 4


def test_past_the_limit_nothing_is_resolved_stat_or_read(tmp_path: Path, touched: list[str]) -> None:
    # Reading order: a.k (1), inner.k (2), beyond_b.k (3 > 2: stop). Everything after it exists on disk.
    main = _deck(tmp_path, {"main.k": "*KEYWORD\n*INCLUDE\na.k\n*INCLUDE\nbeyond_b.k\n*INCLUDE_PATH\nbeyond_dir\n"
                                      "*INCLUDE_BINARY\nbeyond.bin\n*INCLUDE\nbeyond_c.k\n*END\n",
                            "a.k": "*INCLUDE\ninner.k\n", "inner.k": "*NODE\n", "beyond_b.k": "*INCLUDE\nbeyond_d.k\n",
                            "beyond_d.k": "*NODE\n", "beyond_c.k": "*NODE\n", "beyond.bin": b"\x00\x01",
                            "beyond_dir/x.k": "*NODE\n"})
    beyond = ("beyond_b.k", "beyond_d.k", "beyond_dir", "beyond.bin", "beyond_c.k")
    unlimited = preflight_includes(main)
    assert unlimited["ok"] and unlimited["reference_count"] == 7
    for name in beyond:  # without the limit the spy does see each of them
        assert any(name in p for p in touched), name
    touched.clear()
    checked: list[str] = []
    with access.confined(lambda path: checked.append(str(path))):
        report = preflight_includes(main, max_references=2)
    assert _kinds(report) == [("reference_limit", "error")] and not report["ok"]
    problem = report["problems"][0]
    assert (problem["relative"], problem["line"], problem["name_line"], problem["keyword"], problem["name"]) == (
        "main.k", 4, 5, "*INCLUDE", "beyond_b.k")
    assert (problem["counted"], problem["limit"], report["reference_count"], report["max_references"]) == (3, 2, 3, 2)
    assert "More than 2 include references" in problem["reason"]
    assert [(r["name"], r["path"] is None, r["candidates"]) for r in report["references"]][-1] == ("beyond_b.k", True, [])
    assert [r["name"] for r in report["references"]] == ["a.k", "inner.k", "beyond_b.k"]
    assert [f["relative"] for f in report["files"]] == ["main.k", "a.k", "inner.k"]
    assert any(p.endswith("inner.k") for p in touched) and any(p.endswith("inner.k") for p in checked)
    assert not [p for p in touched if any(name in p for name in beyond)], touched
    assert not [p for p in checked if any(name in p for name in beyond)], checked  # nor handed to the guard


def test_a_repeated_include_counts_again_with_everything_it_includes(tmp_path: Path) -> None:
    main = _deck(tmp_path, {"main.k": "*INCLUDE\na.k\n*INCLUDE\na.k\n", "a.k": "*INCLUDE\nb.k\n", "b.k": "*NODE\n"})
    unlimited = preflight_includes(main)
    # LS-DYNA reads a.k twice and therefore b.k twice: a.k, b.k, a.k, b.k.
    assert unlimited["reference_count"] == 4 and len(unlimited["references"]) == 3
    assert _kinds(unlimited) == [("repeated", "warning")]
    assert preflight_includes(main, max_references=4)["ok"]
    report = preflight_includes(main, max_references=3)  # the second a.k fits, the b.k it reads again does not
    assert _kinds(report) == [("reference_limit", "error")]
    problem = report["problems"][0]
    assert (problem["name"], problem["line"], problem["counted"], problem["limit"]) == ("a.k", 3, 4, 3)
    assert Path(problem["path"]) == tmp_path / "a.k"
    second = preflight_includes(main, max_references=2)["problems"][0]  # the second a.k itself is over
    assert (second["name"], second["line"], second["counted"], second["limit"]) == ("a.k", 3, 3, 2)


def test_doubling_includes_are_counted_in_reading_order_and_stopped_early(tmp_path: Path) -> None:
    # Every layer includes the next one twice: 24 listed references, 2**13 - 2 reads by LS-DYNA.
    layers = 12
    files = {f"l{n}.k": f"*INCLUDE\nl{n + 1}.k\n*INCLUDE\nl{n + 1}.k\n" for n in range(1, layers)}
    files.update({"main.k": "*INCLUDE\nl1.k\n*INCLUDE\nl1.k\n", f"l{layers}.k": "*NODE\n"})
    main = _deck(tmp_path, files)
    unlimited = preflight_includes(main)
    assert unlimited["ok"] and unlimited["reference_count"] == 2 ** (layers + 1) - 2
    assert len(unlimited["references"]) == 2 * layers
    report = preflight_includes(main, max_references=100)
    assert [p["kind"] for p in report["problems"]][-1] == "reference_limit" and not report["ok"]
    problem = report["problems"][-1]
    assert problem["counted"] == report["reference_count"] > 100 and problem["limit"] == 100
    assert report["reference_count"] < unlimited["reference_count"]
    # The real cost is the reading-order expansion (parameters, block iteration): bounded by the count.
    full = len(KeywordDeck.load(main).blocks())
    deck = KeywordDeck(SourceFile.read(main), [], record_unreadable=True, max_references=100)
    assert full == 3 * 2 ** layers - 2 and len(deck.blocks()) <= 2 * (deck.reference_count + 1) < full


def test_unresolved_and_failed_names_count_too(tmp_path: Path, touched: list[str]) -> None:
    main = _deck(tmp_path, {"main.k": "*INCLUDE_PATH\nno_dir\n*INCLUDE\nmissing.k\n*INCLUDE\n\\\\probe-host.invalid\\share\\x.k\n"
                                      "*INCLUDE_BINARY\nnone.bin\n*INCLUDE\nbad.k\n*INCLUDE\nmain.k\n",
                            "bad.k": b"*NODE\x00\x00"})
    report = preflight_includes(main)
    assert [p["kind"] for p in report["problems"]] == [
        "missing_search_dir", "missing", "network_path", "missing", "unreadable", "cycle"]
    assert report["reference_count"] == 6 and len(report["references"]) == 6
    exact = preflight_includes(main, max_references=6)
    assert "reference_limit" not in [p["kind"] for p in exact["problems"]] and exact["reference_count"] == 6
    limited = preflight_includes(main, max_references=5)
    assert [p["kind"] for p in limited["problems"]] == [
        "missing_search_dir", "missing", "network_path", "missing", "unreadable", "reference_limit"]
    assert (limited["problems"][-1]["name"], limited["problems"][-1]["counted"]) == ("main.k", 6)
    assert not [p for p in touched if "probe-host" in p.lower()]


def test_include_blocks_past_the_stop_are_not_reported_as_empty(tmp_path: Path) -> None:
    # c.k is never walked; only the block without a file card is an empty include.
    main = _deck(tmp_path, {"main.k": "*INCLUDE\na.k\n*INCLUDE\nb.k\n*INCLUDE\nc.k\n*INCLUDE\n$ no card\n",
                            "a.k": "*NODE\n"})
    report = preflight_includes(main, max_references=1)
    assert _kinds(report) == [("reference_limit", "error"), ("empty_include", "warning")]
    assert report["problems"][1]["line"] == 7


def test_ordinary_loading_raises_past_the_limit(tmp_path: Path) -> None:
    main = _deck(tmp_path, THREE)
    assert KeywordDeck.load(main, max_references=3).reference_count == 3
    assert KeywordDeck.load(main).max_references is None
    with pytest.raises(ValueError, match="More than 2 include references"):
        KeywordDeck.load(main, max_references=2)


@pytest.mark.parametrize("bad", [-1, True, 2.5, "10"])
def test_invalid_limits_are_rejected(tmp_path: Path, bad: object) -> None:
    main = _deck(tmp_path, THREE)
    with pytest.raises(ValueError, match="max_references"):
        preflight_includes(main, max_references=bad)
    with pytest.raises(ValueError, match="max_references"):
        preflight_includes(tmp_path / "absent.k", max_references=bad)
