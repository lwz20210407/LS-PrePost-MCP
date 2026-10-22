import hashlib
import json

from tools.public_corpus_preflight import input_classification, input_tree


def test_complete_include_tree_is_hashed_without_absolute_paths(tmp_path):
    main = tmp_path / "main.k"
    child = tmp_path / "child.k"
    main.write_text("*KEYWORD\n*INCLUDE\nchild.k\n*END\n")
    child.write_text("*KEYWORD\n*END\n")
    report, private = input_tree(main, [main], keyword=True)
    assert report["ok"] and set(private) == {main, child}
    assert [f["relative"] for f in report["files"]] == ["main.k", "child.k"]
    assert all(set(f) == {"relative", "role", "size", "sha256"} for f in report["files"])
    assert str(tmp_path) not in json.dumps(report)
    expected = hashlib.sha256("\n".join(f["sha256"] for f in report["files"]).encode()).hexdigest()
    assert report["tree_sha256"] == expected and report["tree_sha256_version"] == 1
    child.write_text("$ modified\n*KEYWORD\n*END\n")
    changed, _ = input_tree(main, [main], keyword=True)
    assert changed["tree_sha256"] != report["tree_sha256"]


def test_missing_second_include_is_an_input_limitation(tmp_path):
    main = tmp_path / "main.k"
    main.write_text("*KEYWORD\n*INCLUDE\nchild.k\nmissing.k\n*END\n")
    (tmp_path / "child.k").write_text("*KEYWORD\n*END\n")
    report, _ = input_tree(main, [main], keyword=True)
    assert report["ok"] is False and report["tree_sha256"]
    assert input_classification(report) == "input_not_found"
    assert report["problems"][0]["name_line"] == 4


def test_variant_policy_is_distinct_from_missing_input(tmp_path):
    main = tmp_path / "main.k"
    main.write_text("*KEYWORD\n*INCLUDE_TRANSFORM\nchild.k\n*END\n")
    (tmp_path / "child.k").write_text("*KEYWORD\n*END\n")
    report, _ = input_tree(main, [main], keyword=True)
    assert report["ok"]
    assert input_classification(report) == "unsupported_native_include_variant"


def test_result_family_has_explicit_scope_and_all_file_hashes(tmp_path):
    first, second = tmp_path / "d3plot", tmp_path / "d3plot01"
    first.write_bytes(b"geometry")
    second.write_bytes(b"states")
    report, private = input_tree(first, [first, second], keyword=False)
    assert set(private) == {first, second}
    assert report["tree_kind"] == "result_family" and len(report["files"]) == 2
    assert str(tmp_path) not in json.dumps(report)


def test_input_limitation_stops_before_any_native_call():
    from types import SimpleNamespace

    import pytest

    from tests.test_public_corpus_native import test_public_corpus as run_case

    tree = dict(ok=False, problems=[dict(severity="error", kind="missing", hint="not_found")],
                unsupported_native_variants=[])
    record = dict(input_tree=tree, checks=[])
    request = SimpleNamespace(node=SimpleNamespace(user_properties=[]))
    with pytest.raises(pytest.xfail.Exception, match="input_not_found"):
        run_case({"kind": "keyword"}, (None, None, record), request)
    assert record["status"] == "input_limited" and record["checks"] == []
    assert ("native_scope", "evidence_only") in request.node.user_properties


def test_extended_root_parent_include_has_same_tree_as_plain_path(tmp_path):
    import os

    import pytest

    from tools.fetch_corpus import io_root

    if os.name != "nt":
        pytest.skip("Windows extended path semantics")
    (tmp_path / "deck").mkdir()
    (tmp_path / "inc").mkdir()
    main = tmp_path / "deck/main.k"
    main.write_text("*KEYWORD\n*INCLUDE\n../inc/child.k\n*END\n")
    (tmp_path / "inc/child.k").write_text("*KEYWORD\n*END\n")
    expected, _ = input_tree(main, [main], keyword=True)
    extended = io_root(tmp_path) / "deck/main.k"
    actual, _ = input_tree(extended, [extended], keyword=True)
    assert actual["ok"] is True
    assert actual == expected
    assert actual["files_relative_to"] == "common_input_directory"
    assert actual["main_relative"] == "deck/main.k"
    assert [row["relative"] for row in actual["files"]] == ["deck/main.k", "inc/child.k"]


def test_source_directory_snapshot_detects_created_files_and_subdirectories(tmp_path):
    from tools.public_corpus_preflight import directory_snapshot

    main = tmp_path / "main.k"
    main.write_text("*KEYWORD\n*END\n")
    before = directory_snapshot([main])
    assert before == directory_snapshot([main])
    (tmp_path / "unexpected").mkdir()
    (tmp_path / "unexpected/lspost.msg").write_text("native side effect")
    assert before != directory_snapshot([main])


def test_io_root_normalizes_dot_segments_before_extending(tmp_path):
    from tools.fetch_corpus import io_root, plain_path

    (tmp_path / "nested").mkdir()
    assert io_root(io_root(tmp_path) / "nested" / "..") == io_root(tmp_path)
    assert plain_path(io_root(tmp_path)) == tmp_path


def test_relative_input_uses_the_same_declared_file_base(tmp_path, monkeypatch):
    from pathlib import Path

    main = tmp_path / "main.k"
    main.write_text("*KEYWORD\n*END\n")
    expected, _ = input_tree(main, [main], keyword=True)
    monkeypatch.chdir(tmp_path)
    actual, _ = input_tree(Path("main.k"), [Path("main.k")], keyword=True)
    assert actual == expected
