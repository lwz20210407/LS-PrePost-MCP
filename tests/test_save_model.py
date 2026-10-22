"""P11 Include-preserving save; only native process observations are substituted in L1."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.service import Service

pytest.importorskip("ansys.dyna.core")


def deck(root):
    root.mkdir(parents=True)
    (root / "nodes.k").write_bytes(b"$ untouched nodes\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n3,1,1,0\r\n4,0,1,0\r\n")
    (root / "mesh.k").write_text("*ELEMENT_SHELL\n1,1,1,2,3,4\n*PART\nplate\n1,1,1\n"
                                "*SECTION_SHELL\n1,2\n1,1,1,1\n*MAT_ELASTIC\n1,1,100,0.3\n", encoding="utf-8")
    main = root / "main.k"
    main.write_bytes(b"*KEYWORD\r\n$ keep hierarchy\r\n*INCLUDE\r\nnodes.k\r\nmesh.k\r\n*END\r\n")
    return main


BASELINE = {"status": "succeeded", "job_id": "native-before", "data": {
    "counts": {"nodes": 4, "elements": 1, "states": 1}, "part_ids": [1]}}


def service(tmp_path, monkeypatch, after=None):
    main = deck(tmp_path / "source")
    svc = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path / "source",)))
    calls = []

    def native(action, parameters, model=None, **kwargs):
        assert action == "inspect_model" and not kwargs.get("export") and not kwargs.get("graphics")
        calls.append(Path(model))
        reply = copy.deepcopy(BASELINE if len(calls) == 1 else (after or BASELINE))
        reply["job_id"] = "native-before" if len(calls) == 1 else "native-after"
        return reply

    monkeypatch.setattr(svc, "_native", native)
    return svc, main, calls


def invoke(svc, main, **kwargs):
    return JobResult.model_validate_json(json.dumps(svc.save_model(str(main), **kwargs), allow_nan=False))


def test_include_save_keeps_original_bytes_and_automatically_reopens(tmp_path, monkeypatch):
    svc, main, calls = service(tmp_path, monkeypatch)
    before = {p.name: p.read_bytes() for p in main.parent.iterdir()}
    result = invoke(svc, main)
    assert result.status == "succeeded", result.error
    assert result.check_status == "passed"
    saved = Path(result.data["main"])
    assert saved.is_relative_to(svc.jobs.root / result.job_id)
    assert calls == [main, saved]
    assert {p.name: p.read_bytes() for p in main.parent.iterdir()} == before
    assert {p.name: p.read_bytes() for p in saved.parent.iterdir()} == before
    assert len(result.artifacts) == 3
    assert all(hashlib.sha256(Path(a.path).read_bytes()).hexdigest() == a.sha256 for a in result.artifacts)
    manifest = json.loads((svc.jobs.root / result.job_id / "job.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "succeeded" and manifest["result"]["operation"] == "save_model"


@pytest.mark.parametrize("changes", [{"counts": {"nodes": 3, "elements": 1}}, {"part_ids": [2]},
                                     {"counts": {"nodes": 4}}, {"counts": {"nodes": True, "elements": 1}},
                                     {"counts": "malformed"}])
def test_reopen_differences_fail_and_return_actual_observations(tmp_path, monkeypatch, changes):
    after = copy.deepcopy(BASELINE)
    after["data"].update(changes)
    svc, main, calls = service(tmp_path, monkeypatch, after)
    result = invoke(svc, main)
    assert result.status == "failed" and result.error["message"]
    assert result.data["differences"] and not result.artifacts
    assert len(calls) == 2


def test_explicit_expected_counts_refuse_an_incorrect_input_before_copy(tmp_path, monkeypatch):
    svc, main, calls = service(tmp_path, monkeypatch)
    result = invoke(svc, main, expected_counts={"nodes": 5, "elements": 1}, expected_part_ids=[1])
    assert result.status == "failed" and result.data["differences"]
    assert len(calls) == 1 and "main" not in result.data


@pytest.mark.parametrize("kwargs", [{"expected_counts": {"nodes": True}},
                                    {"expected_counts": {"unrecognized": 2}},
                                    {"expected_part_ids": [1, 1]}])
def test_bad_expectations_do_not_launch_native(tmp_path, monkeypatch, kwargs):
    svc, main, calls = service(tmp_path, monkeypatch)
    result = invoke(svc, main, **kwargs)
    assert result.status == "failed" and not calls


def test_native_error_is_retained_not_turned_into_verified_save(tmp_path, monkeypatch):
    svc, main, calls = service(tmp_path, monkeypatch, {"status": "failed", "error": {"message": "native diagnostic"}})
    result = invoke(svc, main)
    assert result.status == "failed" and "native diagnostic" in result.error["message"]
    assert not result.artifacts and len(calls) == 2


def test_source_modified_during_reopen_is_refused(tmp_path, monkeypatch):
    svc, main, calls = service(tmp_path, monkeypatch)
    original = svc._native

    def native(*args, **kwargs):
        reply = original(*args, **kwargs)
        if len(calls) == 2:
            (main.parent / "nodes.k").write_text("unexpected external change", encoding="utf-8")
        return reply

    monkeypatch.setattr(svc, "_native", native)
    result = invoke(svc, main)
    assert result.status == "failed" and "changed" in result.error["message"].lower()
    assert not result.artifacts


def test_source_change_between_engine_load_and_snapshot_is_refused(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.model.deck import KeywordDeck

    svc, main, calls = service(tmp_path, monkeypatch)
    load = KeywordDeck.load

    def changed(*args, **kwargs):
        loaded = load(*args, **kwargs)
        (main.parent / "nodes.k").write_text("$ external change\n*NODE\n1,0,0,0\n", encoding="utf-8")
        return loaded

    monkeypatch.setattr(KeywordDeck, "load", changed)
    result = invoke(svc, main)
    assert result.status == "failed" and "changed while loading" in result.error["message"]
    assert not calls and not result.artifacts


def test_source_directory_new_file_during_reopen_is_refused(tmp_path, monkeypatch):
    svc, main, calls = service(tmp_path, monkeypatch)
    original = svc._native

    def native(*args, **kwargs):
        reply = original(*args, **kwargs)
        if len(calls) == 2:
            (main.parent / "unexpected.txt").write_text("created by external actor", encoding="utf-8")
        return reply

    monkeypatch.setattr(svc, "_native", native)
    result = invoke(svc, main)
    assert result.status == "failed" and "listing changed" in result.error["message"]
    assert not result.artifacts


def test_comment_only_plain_include_is_not_a_missing_file(tmp_path):
    main = tmp_path / "main.k"
    main.write_text("*KEYWORD\n*INCLUDE\n$disabled alternative\n*END\n", encoding="utf-8")
    Settings(tmp_path).check_keyword_includes(main)


def test_empty_unsupported_variant_still_fails(tmp_path):
    main = tmp_path / "main.k"
    main.write_text("*KEYWORD\n*INCLUDE_BINARY\n$disabled alternative\n*END\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Only plain|preflight failed"):
        Settings(tmp_path).check_keyword_includes(main)


def test_include_outside_roots_is_not_opened_even_for_preflight(tmp_path, monkeypatch):
    svc, main, calls = service(tmp_path, monkeypatch)
    outside = tmp_path / "external.k"
    outside.write_bytes(b"external contents must not be inspected")
    main.write_text("*KEYWORD\n*INCLUDE\n../external.k\n*END\n", encoding="utf-8")
    original = Path.open

    def guarded(path, *args, **kwargs):
        if path.resolve() == outside:
            pytest.fail("Preflight opened an input outside allowed roots")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    result = invoke(svc, main)
    assert result.status == "failed" and "outside" in result.error["message"].lower()
    assert not calls and result.job_id is None
