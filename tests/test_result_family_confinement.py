"""I01 regressions: actual legacy entry points must not read unregistered families."""

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


def fixture_service(tmp_path, basename="d3plot"):
    folder = tmp_path / "source"
    folder.mkdir()
    source = folder / basename
    source.write_bytes(b"owned discovery fixture main")
    source.with_name(basename + "01").write_bytes(b"owned continuation")
    return Service(Settings(tmp_path / "jobs", allowed_roots=(folder,))), source


def fake_database():
    return SimpleNamespace(header=SimpleNamespace(n_nodes=1, n_shells=0, n_solids=0), arrays={
        "timesteps": np.array([0.]), "node_ids": np.array([19]),
        "node_coordinates": np.array([[0., 0., 0.]]),
        "node_velocity": np.array([[[1., 2., 3.]]]),
    })


def test_family_planning_rejects_reader_regex_candidates_not_in_literal_family(tmp_path):
    service, source = fixture_service(tmp_path, "model.d3plot")
    (source.parent / "modelXd3plot02").write_bytes(b"not in the admitted literal family")
    with pytest.raises(ValueError, match="family|candidate|discovery"):
        service._result_family(str(source))


@pytest.mark.parametrize("entry", ["inspect_d3plot_database", "inspect_result_fields"])
def test_legacy_metadata_rejects_ambiguous_family_before_sdk(tmp_path, monkeypatch, entry):
    dyna = pytest.importorskip("lasso.dyna")
    service, source = fixture_service(tmp_path, "model.d3plot")
    (source.parent / "modelXd3plot02").write_bytes(b"unregistered candidate")
    monkeypatch.setattr(dyna, "D3plot", lambda *a, **k: pytest.fail("SDK construction before family admission"))
    with pytest.raises(ValueError, match="family|candidate|discovery"):
        getattr(service, entry)(str(source))
    assert not service.jobs.list()


@pytest.mark.parametrize("change", ["bytes", "add"])
def test_legacy_nodal_export_fails_when_continuation_family_changes(tmp_path, monkeypatch, change):
    dyna = pytest.importorskip("lasso.dyna")
    service, source = fixture_service(tmp_path)

    def changed_reader(*args, **kwargs):
        if change == "bytes":
            source.with_name("d3plot01").write_bytes(b"changed continuation content")
        else:
            source.with_name("d3plot02").write_bytes(b"new continuation")
        return fake_database()

    monkeypatch.setattr(dyna, "D3plot", changed_reader)
    result = service.extract_d3plot_nodal(str(source), [19], "velocity", [1], "m/s")
    assert result["status"] == "failed", "A changed result family must not publish a successful nodal CSV"
    assert result.get("error") and not result.get("artifacts")


def test_legacy_metadata_fails_when_continuation_changes_during_sdk(tmp_path, monkeypatch):
    dyna = pytest.importorskip("lasso.dyna")
    service, source = fixture_service(tmp_path)

    def changed_reader(*args, **kwargs):
        source.with_name("d3plot01").write_bytes(b"changed")
        return fake_database()

    monkeypatch.setattr(dyna, "D3plot", changed_reader)
    with pytest.raises(ValueError, match="changed|identity|family"):
        service.inspect_d3plot_database(str(source))


def test_plain_unrelated_directories_and_files_remain_supported(tmp_path):
    from ls_prepost_mcp.domain.results.family import plan_family

    service, source = fixture_service(tmp_path)
    (source.parent / "ordinary-folder").mkdir()
    (source.parent / "notes.txt").write_text("ordinary unrelated public file")
    assert service._result_family(str(source)) == [source, source.with_name("d3plot01")]
    assert plan_family(source).paths == (source, source.with_name("d3plot01"))


def test_candidate_policy_runs_before_stat_including_unrelated_sdk_metadata(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results.family import plan_family

    _, source = fixture_service(tmp_path)
    forbidden = source.parent / "unrelated-target"
    forbidden.write_bytes(b"opaque fixture; do not stat this candidate")
    is_file = Path.is_file
    events = []

    def guard(path):
        events.append(("guard", path.name))
        if path == forbidden:
            raise ValueError("outside allowed roots")

    def checked_is_file(path):
        assert path != forbidden, "SDK candidate stat preceded its root policy"
        events.append(("stat", path.name))
        return is_file(path)

    monkeypatch.setattr(Path, "is_file", checked_is_file)
    with pytest.raises(ValueError, match="outside"):
        plan_family(source, guard)
    assert ("guard", forbidden.name) in events and not [event for event in events if event[0] == "stat"]


@pytest.mark.parametrize("path", [r"\\uncontacted.invalid\share\d3plot", r"\\.\GLOBALROOT\d3plot"])
def test_network_and_device_paths_reject_before_listing_or_stat(monkeypatch, path):
    from ls_prepost_mcp.domain.results.family import plan_family

    monkeypatch.setattr(os, "listdir", lambda *a: pytest.fail("Network listing must never run"))
    monkeypatch.setattr(Path, "is_file", lambda *a: pytest.fail("Network stat must never run"))
    with pytest.raises(ValueError, match="Network|device"):
        plan_family(path)


def test_all_sizes_use_streamed_hash_and_same_size_mtime_rewrite_is_detected(tmp_path):
    from ls_prepost_mcp.domain.results.family import plan_family

    _, source = fixture_service(tmp_path)
    continuation = source.with_name("d3plot01")
    snapshot = plan_family(source).capture()
    original_stat = continuation.stat()
    continuation.write_bytes(b"X" * original_stat.st_size)
    os.utime(continuation, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    with pytest.raises(ValueError, match="identity changed"):
        snapshot.verify()
    assert all(len(row["sha256"]) == 64 for row in snapshot.records)


def test_nested_sdk_constructions_share_one_streamed_before_after_snapshot(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import family

    _, source = fixture_service(tmp_path)
    fingerprint = family._fingerprint
    hashed = []

    def observed(path, guard):
        hashed.append(path.name)
        return fingerprint(path, guard)

    monkeypatch.setattr(family, "_fingerprint", observed)
    with family.reading_family(source) as reader:
        for _ in range(3):
            assert family.open_d3plot(source, constructor=lambda *a, **k: "observed") == "observed"
        assert reader.snapshot.plan.source == source
    assert hashed == ["d3plot", "d3plot01", "d3plot", "d3plot01"]


def test_non_native_reader_does_not_inherit_native_two_gib_limit(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results.family import reading_family

    _, source = fixture_service(tmp_path)
    original = Path.stat

    def reported_stat(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path != source:
            return result
        return SimpleNamespace(st_size=3 * 1024**3, st_mode=result.st_mode, st_mtime_ns=result.st_mtime_ns,
                               st_ino=result.st_ino, st_dev=result.st_dev)

    monkeypatch.setattr(Path, "stat", reported_stat)
    with reading_family(source) as reader:
        # Only stat metadata is mocked: no huge/sparse file is created or read.
        assert reader.snapshot.records[0]["size_bytes"] == 3 * 1024**3
        assert reader.open(constructor=lambda *a, **k: "read") == "read"


def test_internal_state_admission_is_metadata_only_and_cannot_certify_results(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import family

    _, source = fixture_service(tmp_path)
    monkeypatch.setattr(family, "_fingerprint", lambda *a: pytest.fail("State budget admission must not SHA content"))
    with family._state_admission(source) as reader:
        assert not reader.snapshot.hashed
        assert family.open_d3plot(source, constructor=lambda *a, **k: "times", state_array_filter=["timesteps"]) == "times"
        for options in (dict(state_array_filter=["node_velocity"]), dict(state_array_filter=["timesteps"], state_filter={0}), {}):
            with pytest.raises(ValueError, match="only timestep"):
                family.open_d3plot(source, constructor=lambda *a, **k: pytest.fail("Nonmetadata SDK call"), **options)
        with pytest.raises(ValueError, match="cannot certify"), family.reading_family(source, snapshot=reader.snapshot):
            pytest.fail("Weak metadata identity was reused for output evidence")


def test_state_admission_still_rechecks_membership_and_stat_identity(tmp_path):
    from ls_prepost_mcp.domain.results.family import _state_admission

    _, source = fixture_service(tmp_path)
    with pytest.raises(ValueError, match="membership changed"), _state_admission(source):
        source.with_name("d3plot02").write_bytes(b"new metadata candidate")


def test_wrong_source_snapshot_is_never_reused(tmp_path):
    from ls_prepost_mcp.domain.results.family import plan_family, reading_family

    _, source = fixture_service(tmp_path)
    snapshot = plan_family(source).capture()
    with pytest.raises(ValueError, match="different source"), reading_family(source.with_name("d3plot01"), snapshot=snapshot):
        pytest.fail("A foreign snapshot was admitted")


@pytest.mark.parametrize("profile", ["full", "compact"])
def test_registered_mcp_legacy_entry_keeps_family_guard(tmp_path, monkeypatch, profile):
    dyna = pytest.importorskip("lasso.dyna")
    from mcp.server.fastmcp.exceptions import ToolError

    from ls_prepost_mcp.server import build_server

    service, source = fixture_service(tmp_path, "model.d3plot")
    (source.parent / "modelXd3plot02").write_bytes(b"extra")
    monkeypatch.setattr(dyna, "D3plot", lambda *a, **k: pytest.fail("MCP reached an unadmitted SDK reader"))
    server = build_server(service.settings, profile)
    operation, arguments = "inspect_d3plot_database", dict(path=str(source))
    if profile == "compact":
        operation, arguments = "lspp_run_operation", dict(operation=operation, execution="direct", arguments=arguments)
    with pytest.raises(ToolError, match="family|discovery"):
        asyncio.run(server.call_tool(operation, arguments))
    assert not service.jobs.list()
