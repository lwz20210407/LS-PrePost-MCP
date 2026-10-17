"""Offline I04 diagnostic contracts; no real host, corpus, or native executable."""

from unittest.mock import Mock

import pytest

from tools import diagnose_public_corpus as diagnostic


def test_state_disagreement_preserves_all_values_and_one_based_positions():
    native = {"counts": {"states": 2}, "state_times": [0.0, 1.0]}
    reader = {"state_count": 4, "state_times": [0.0, 1.0, -999999.0, 1.0]}
    result = diagnostic.state_comparison(native, reader)
    assert result["verdict"] == "backend_state_count_mismatch"
    assert result["reader_times"] == reader["state_times"]
    assert result["reader_time_reversals"] == [3]


@pytest.mark.parametrize("count,times,verdict", [
    (2, [0.0], "incomplete_time_arrays"),
    (2, [0.0, 2.0], "backend_time_array_mismatch"),
    (2, [0.0, 1.0], "identical_state_metadata_only"),
])
def test_time_arrays_are_not_truncated_or_adjusted(count, times, verdict):
    result = diagnostic.state_comparison({"counts": {"states": 2}, "state_times": [0.0, 1.0]},
                                         {"state_count": count, "state_times": times})
    assert result["verdict"] == verdict


def test_keyword_crash_does_not_export_or_reclassify_empty_model(tmp_path):
    service = Mock()
    service.inspect_model.return_value = {"status": "failed", "error": {"message": "returncode=3221225477"}}
    result = diagnostic.diagnose(service, tmp_path / "model.k", "keyword", run_native=True)
    assert result["status"] == "native_inventory_failed"
    assert result["native_inventory"]["error"] == service.inspect_model.return_value["error"]
    service.export_keyword.assert_not_called()


def test_offline_never_launches_native(tmp_path, monkeypatch):
    service = Mock()
    monkeypatch.setattr(diagnostic, "overview", lambda _: {"backend": "mock", "states": 1, "times": [0.0]})
    result = diagnostic.diagnose(service, tmp_path / "d3plot", "d3plot", run_native=False)
    assert result["status"] == "offline_only"
    service.inspect_model.assert_not_called()
    service.export_keyword.assert_not_called()


def test_native_requires_explicit_executable(tmp_path):
    with pytest.raises(SystemExit):
        diagnostic.main(["--case", diagnostic.CASE_IDS[0], "--corpus-root", str(tmp_path),
                         "--output", str(tmp_path / "out"), "--run-native"])
    assert not (tmp_path / "out").exists()


def test_missing_source_is_preservation_failure_not_lost_report(tmp_path):
    result = diagnostic.preservation({tmp_path / "missing": "expected"}, {})
    assert result["originals_unchanged"] is False
    assert result["preservation_error"]


def test_changed_source_and_added_files_are_detected(tmp_path):
    source = tmp_path / "source.k"
    source.write_text("original")
    identities = {source: diagnostic.digest(source)}
    listing = diagnostic.directory_snapshot(identities)
    source.write_text("changed")
    (tmp_path / "unexpected").write_text("new")
    result = diagnostic.preservation(identities, listing)
    assert result["originals_unchanged"] is False
    assert result["directory_listing_unchanged"] is False


def test_windows_unicode_include_root_rejected_before_job_creation(tmp_path, monkeypatch):
    import importlib

    module = importlib.import_module("ls_prepost_mcp.service")
    monkeypatch.setattr(module, "_windows", lambda: True)
    monkeypatch.setattr(diagnostic.Settings, "native_executable", lambda _: tmp_path / "unused.exe")
    source = write_keyword_fixture(tmp_path / "中文")
    service = diagnostic.Service(diagnostic.Settings(tmp_path / "jobs", allowed_roots=(tmp_path,)))
    service.jobs.create = Mock(side_effect=AssertionError("Created job before path refusal"))
    with pytest.raises(ValueError, match="Non-ASCII.*INCLUDE"):
        service.inspect_model(str(source))
    service.jobs.create.assert_not_called()


@pytest.mark.parametrize("parent,include", [("ascii", True), ("中文", False)])
def test_path_guard_preserves_other_native_routes(tmp_path, monkeypatch, parent, include):
    import importlib

    module = importlib.import_module("ls_prepost_mcp.service")
    monkeypatch.setattr(module, "_windows", lambda: True)
    monkeypatch.setattr(diagnostic.Settings, "native_executable", lambda _: tmp_path / "unused.exe")
    source = write_keyword_fixture(tmp_path / parent)
    if not include:
        source = source.with_name("mesh.k")
    service = diagnostic.Service(diagnostic.Settings(tmp_path / "jobs", allowed_roots=(tmp_path,)))
    service.jobs.create = Mock(side_effect=RuntimeError("Allowed route reached job creation"))
    with pytest.raises(RuntimeError, match="Allowed route"):
        service.inspect_model(str(source))
    service.jobs.create.assert_called_once()


def test_lasso_204_tail_after_endmark_reproduces_extra_state(tmp_path):
    """Original data, no corpus bytes: preserve the upstream gap for its owner."""
    import struct

    import numpy as np

    pytest.importorskip("lasso")
    from lasso.dyna import ArrayType as A
    from lasso.dyna import D3plot

    plot = D3plot()
    coords = np.array([[0., 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]])
    plot.arrays.update({
        A.node_coordinates: coords, A.node_ids: np.arange(1, 5),
        A.element_shell_node_indexes: np.array([[0, 1, 2, 3]]),
        A.element_shell_part_indexes: np.array([0]), A.element_shell_ids: np.array([10]),
        A.part_titles_ids: np.array([1]), A.part_titles: np.array([b"shell".ljust(72)]),
        A.global_timesteps: np.array([0., 1.]),
        A.node_displacement: np.repeat(coords[None], 2, axis=0),
    })
    source = tmp_path / "d3plot"
    plot.write_d3plot(str(source), single_file=False)
    original = D3plot(str(source))
    assert original.arrays["timesteps"].tolist() == [0., 1.]
    # Use the existing reader's layout calculation, not a parallel parser.
    size = original._compute_n_bytes_per_state()
    wordsize = original.header.wordsize
    marker = struct.pack("<f" if wordsize == 4 else "<d", -999999.)
    state_file = tmp_path / "d3plot01"
    raw = state_file.read_bytes()
    assert raw[size:size + wordsize] == marker
    state_file.write_bytes(raw[:size + wordsize] + bytes(size) + b"\x01" + bytes(2048))
    service = diagnostic.Service(diagnostic.Settings(tmp_path / "jobs", allowed_roots=(tmp_path,)))
    observed = service.inspect_d3plot_database(str(source))
    assert observed["state_times"] == [0., -999999., 1.]
    result = diagnostic.state_comparison({"counts": {"states": 2}, "state_times": [0., 1.]}, observed)
    assert result["verdict"] == "backend_state_count_mismatch"
    assert result["reader_time_reversals"] == [2]


def write_keyword_fixture(directory):
    """Original four-node shell and plain INCLUDE for path-only comparisons."""
    directory.mkdir(parents=True)
    source = directory / "main.k"
    source.write_text("*KEYWORD\n*INCLUDE\nmesh.k\n*END\n", encoding="ascii")
    (directory / "mesh.k").write_text(
        "*KEYWORD\n*NODE\n1,0,0,0\n2,1,0,0\n3,1,1,0\n4,0,1,0\n"
        "*ELEMENT_SHELL\n1,1,1,2,3,4\n*PART\nshell\n1,1,1\n"
        "*SECTION_SHELL\n1,2\n0.1\n*MAT_ELASTIC\n1,1,1000,0.3\n*END\n", encoding="ascii")
    return source


@pytest.mark.native
@pytest.mark.parametrize("parent", ["ascii", "中文"])
def test_native_include_source_parent(tmp_path, pytestconfig, parent):
    if not pytestconfig.getoption("--run-native"):
        pytest.skip("Requires an explicit scheduled headless window")
    from pathlib import Path

    executable = pytestconfig.getoption("--native-executable")
    if not executable:
        pytest.fail("Explicit native executable required")
    source = write_keyword_fixture(tmp_path / parent)
    service = diagnostic.Service(diagnostic.Settings(tmp_path / "jobs", Path(executable), (tmp_path,), 120))
    tree, identities = diagnostic.input_tree(source, [source], keyword=True)
    listing = diagnostic.directory_snapshot(identities)
    try:
        if parent == "中文":
            import os

            if os.name == "nt":
                with pytest.raises(ValueError, match="Non-ASCII.*INCLUDE"):
                    service.inspect_model(str(source))
                return
        result = service.inspect_model(str(source))
        diagnostic.atomic_json(tmp_path / "inventory.json", result)
        assert result["status"] == "succeeded", result.get("error")
        assert result["data"]["counts"]["nodes"] == 4
        assert tree["ok"]
    finally:
        assert diagnostic.preservation(identities, listing) == {
            "originals_unchanged": True, "directory_listing_unchanged": True}
