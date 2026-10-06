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
