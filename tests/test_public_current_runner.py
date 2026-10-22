"""I04 public runs use the canonical tree save and honest snapshot input policy."""
from pathlib import Path
from unittest.mock import Mock

import pytest

from tests.test_public_corpus_native import keyword_round_trip
from tools.public_corpus_preflight import input_classification, input_tree


def test_keyword_runner_uses_main_artifact_and_reuses_verified_reopen(tmp_path):
    service = Mock()
    source, output = tmp_path / "main.k", tmp_path / "saved/main.k"
    counts = {"nodes": 1, "elements": 0}
    service.inspect_model.return_value = {"status": "succeeded", "data": {"counts": counts, "part_ids": [2]}}
    service.list_nodes.return_value = {"status": "succeeded", "data": {"rows": [[7, 1., 2., 3.]]}}
    service.save_model.return_value = {"status": "succeeded", "artifacts": [{"path": "not-the-main.k", "kind": "keyword"}],
        "data": {"main": str(output), "observations": {"after_reopen": {"status": "succeeded", "job_id": "reopen",
                   "counts": counts, "part_ids": [2]}}}}
    service.export_keyword.side_effect = AssertionError("Legacy export cannot preserve Includes")
    record = {"checks": []}
    keyword_round_trip(service, source, record)
    service.save_model.assert_called_once_with(str(source))
    service.export_keyword.assert_not_called()
    service.inspect_model.assert_called_once()
    assert [c.args[0] for c in service.list_nodes.call_args_list] == [str(source), str(output)]


@pytest.mark.parametrize("keyword", ["*INCLUDE_PATH", "*INCLUDE_PATH_RELATIVE"])
def test_main_search_path_is_not_misclassified_as_an_unsupported_variant(tmp_path, keyword):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/nodes.k").write_text("*NODE\n1,0,0,0\n")
    main = tmp_path / "main.k"
    main.write_text("*KEYWORD\n" + keyword + "\nassets\n*INCLUDE\nnodes.k\n*END\n")
    tree, _ = input_tree(main, [main], keyword=True)
    assert input_classification(tree) == "preflight_ok_requires_native_diagnosis"


def test_ambiguous_input_is_limited_before_snapshot_launch(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub/assembly.k").write_text("*INCLUDE\nnodes.k\n")
    for path in (tmp_path / "nodes.k", tmp_path / "sub/nodes.k"):
        path.write_text("*NODE\n1,0,0,0\n")
    main = tmp_path / "main.k"
    main.write_text("*INCLUDE\nsub/assembly.k\n")
    tree, _ = input_tree(main, [main], keyword=True)
    assert input_classification(tree) == "input_ambiguous"


def test_public_tree_preflight_does_not_read_outside_explicit_roots(tmp_path, monkeypatch):
    root = tmp_path / "public"
    root.mkdir()
    main = root / "main.k"
    outside = tmp_path / "private.k"
    outside.write_bytes(b"private content")
    main.write_text("*INCLUDE\n../private.k\n")
    original = Path.open

    def guarded(path, *args, **kwargs):
        if path.resolve() == outside:
            pytest.fail("Public input preflight opened private data")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    tree, identities = input_tree(main, [main], keyword=True, allowed_roots=(root,))
    assert not tree["ok"] and set(identities) == {main}


def test_ambiguous_runner_row_is_evidence_only_without_native_launch():
    from types import SimpleNamespace

    from tests.test_public_corpus_native import test_public_corpus as run_case

    record = {"input_tree": {"ok": True, "problems": [{"kind": "ambiguous", "severity": "warning"}],
                             "unsupported_native_variants": []}, "checks": []}
    request = SimpleNamespace(node=SimpleNamespace(user_properties=[]))
    with pytest.raises(pytest.xfail.Exception, match="input_ambiguous"):
        run_case({"kind": "keyword"}, (None, None, record), request)
    assert record["status"] == "input_limited" and not record["checks"]
