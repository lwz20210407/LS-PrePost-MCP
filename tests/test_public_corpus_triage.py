import json

from tools.triage_public_corpus import category, summarize


def test_legacy_sidecar_is_recovered_without_fabricating_the_missing_diff(tmp_path):
    report = tmp_path / "report.json"
    raw = {"cases": {
        "tests/test_public_corpus_native.py::test_public_corpus[dependency]": {
            "status": "failed", "reason": "E ModuleNotFoundError: No module named 'numpy'"},
        "tests/test_public_corpus_native.py::test_public_corpus[ok]": {"status": "passed", "reason": ""}}}
    report.write_text(json.dumps(raw), encoding="utf8")
    original = report.read_bytes()
    (tmp_path / "execution-context.json").write_text(json.dumps({
        "actual_git_head": "a" * 40, "working_tree_dirty": True, "source_snapshot_sha256": "b" * 64}), encoding="utf8")
    result = summarize(report)
    assert result["actual_git_revision"] == "a" * 40 and result["git_diff_sha256"] is None
    assert result["missing_provenance"] == ["git_diff_sha256"] and not result["revision_binding_complete"]
    assert result["outcomes"] == {"failed": 1, "passed": 1}
    assert result["preliminary_categories"] == {"dependency": 1}
    assert result["input_preservation"] == {} and report.read_bytes() == original


def test_missing_output_and_reader_schema_errors_are_not_relabelled_as_input_defects():
    assert category("E FileNotFoundError: curve.xy") == "unclassified"
    assert category("assert native_count == reader['state_count']\nE KeyError: state_count") == "unclassified"
    assert category("E AssertionError: Native batch failed: timeout=False, returncode=0, diagnostics=['error']") == "unclassified"


def test_unknown_revision_stays_unknown(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"cases": {}}), encoding="utf8")
    result = summarize(report)
    assert result["actual_git_revision"] is None and not result["revision_binding_complete"]
    assert result["missing_provenance"] == ["actual_git_head", "working_tree_dirty"]


def test_invalid_context_does_not_establish_revision_binding(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"cases": {}, "execution_context": {
        "actual_git_head": "", "working_tree_dirty": "false", "git_diff_sha256": "made-up"}}), encoding="utf8")
    result = summarize(report)
    assert not result["revision_binding_complete"]
    assert result["missing_provenance"] == ["actual_git_head", "working_tree_dirty"]


def test_include_oserror_is_a_reference_path_symptom():
    assert category("check_keyword_includes\nE OSError: [WinError 123] invalid filename") == "missing_referenced_input"
    assert category("E OSError: output file is locked") == "unclassified"
