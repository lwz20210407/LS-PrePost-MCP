"""I01 regressions: actual legacy entry points must not read unregistered families."""

import asyncio
import builtins
import os
from contextlib import nullcontext
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


@pytest.mark.parametrize("basename", ["(a+)+", "beam[1]", "beam{1}", "beam^", "beam$", "beam+"])
def test_regex_operators_reject_before_directory_enumeration(tmp_path, monkeypatch, basename):
    from ls_prepost_mcp.domain.results.family import plan_family

    _, source = fixture_service(tmp_path, basename)
    monkeypatch.setattr(os, "listdir", lambda *a: pytest.fail("Unsafe SDK expression reached directory matching"))
    with pytest.raises(ValueError, match="regex operators"):
        plan_family(source)


@pytest.mark.parametrize("basename", ["model.d3plot", "beam history", "beam-history", "beam#history", "beam_模型"])
def test_safe_fixed_width_sdk_subset_keeps_literal_families_supported(tmp_path, basename):
    from ls_prepost_mcp.domain.results.family import plan_family

    _, source = fixture_service(tmp_path, basename)
    assert plan_family(source).paths == (source, source.with_name(basename + "01"))


def test_fixed_width_prediction_matches_locked_sdk_on_admitted_names():
    import re

    from ls_prepost_mcp.domain.results.family import _sdk_continuation

    # Only harmless fixed-width prefixes; never compile the rejected operator inputs.
    for basename in ("d3plot", "model.d3plot", "beam history", "beam#history", "beam_模型"):
        for candidate in (basename + "01", basename + "١", basename + "01x", basename + "", "modelXd3plot02"):
            assert _sdk_continuation(basename, candidate) == bool(re.match(f"({basename})[0-9]+$", candidate))


def test_control_character_candidates_reject_before_metadata_stat(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results.family import plan_family

    _, source = fixture_service(tmp_path)
    # Python regex '$' can accept a final LF; this layout is explicitly refused.
    monkeypatch.setattr(os, "listdir", lambda *a: [source.name, "d3plot01\n"])
    monkeypatch.setattr(Path, "is_file", lambda *a: pytest.fail("Control-name candidate reached stat"))
    with pytest.raises(ValueError, match="control-character"):
        plan_family(source)


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


@pytest.mark.parametrize("entry", ["inspect_d3plot_database", "extract_d3plot_nodal"])
def test_missing_optional_sdk_is_reported_before_whole_family_hash(tmp_path, monkeypatch, entry):
    from ls_prepost_mcp.domain.results import family

    service, source = fixture_service(tmp_path)
    original = builtins.__import__

    def absent(name, *args, **kwargs):
        if name == "lasso.dyna":
            raise ImportError("synthetic optional results dependency absent")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", absent)
    monkeypatch.setattr(family, "_fingerprint", lambda *a: pytest.fail("Unneeded SHA before missing SDK rejection"))
    with pytest.raises(ImportError, match="synthetic optional"):
        if entry == "inspect_d3plot_database":
            service.inspect_d3plot_database(str(source))
        else:
            service.extract_d3plot_nodal(str(source), [19], "velocity", [1], "m/s")
    assert not service.jobs.list()


def test_primary_allowed_root_check_precedes_optional_dependency_import(tmp_path, monkeypatch):
    service, _ = fixture_service(tmp_path)
    outside = tmp_path / "outside-d3plot"
    outside.write_bytes(b"denied input")
    original = builtins.__import__

    def absent(name, *args, **kwargs):
        if name == "lasso.dyna":
            pytest.fail("Dependency import preceded the primary input guard")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", absent)
    with pytest.raises(ValueError, match="outside"):
        service.inspect_d3plot_database(str(outside))


def test_legacy_nodal_scope_includes_artifact_verifier(tmp_path, monkeypatch):
    dyna = pytest.importorskip("lasso.dyna")
    import ls_prepost_mcp.service as service_module

    service, source = fixture_service(tmp_path)
    original = service_module.check_artifact
    monkeypatch.setattr(dyna, "D3plot", lambda *a, **kw: fake_database())

    def during_verification(*args, **kwargs):
        result = original(*args, **kwargs)
        source.with_name("d3plot01").write_bytes(b"changed during artifact verification")
        return result

    monkeypatch.setattr(service_module, "check_artifact", during_verification)
    result = service.extract_d3plot_nodal(str(source), [19], "velocity", [1], "m/s")
    assert result["status"] == "failed" and not result.get("artifacts")


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
    from ls_prepost_mcp.domain.results import family

    _, source = fixture_service(tmp_path)
    original = family._fingerprint

    def reported_identity(path, guard):
        result = original(path, guard)
        if path == source:
            result["size_bytes"] = 3 * 1024**3
        return result

    monkeypatch.setattr(family, "_fingerprint", reported_identity)
    with family.reading_family(source) as reader:
        # Only recorded size metadata is mocked: no huge/sparse file is created/read.
        assert reader.snapshot.records[0]["size_bytes"] == 3 * 1024**3
        assert reader.open(constructor=lambda *a, **k: "read") == "read"


def test_growing_hash_is_bounded_to_initial_size_plus_one(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import family

    source = tmp_path / "d3plot"
    source.write_bytes(b"A" * 128)
    original = Path.open
    observed = dict(read_bytes=0, appends=0)

    class GrowingRead:
        def __init__(self, stream):
            self.stream = stream

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def record(self, size):
            observed["read_bytes"] += size
            if size and observed["appends"] < 8:
                with original(source, "ab", buffering=0) as writer:
                    writer.write(b"B" * 8)
                observed["appends"] += 1

        def read(self, size=-1):
            data = self.stream.read(size)
            self.record(len(data))
            return data

        def readinto(self, buffer):
            count = self.stream.readinto(buffer)
            self.record(count)
            return count

    def growing_open(path, *args, **kwargs):
        stream = original(path, *args, **kwargs)
        return GrowingRead(stream) if path == source and args and args[0] == "rb" else stream

    monkeypatch.setattr(Path, "open", growing_open)
    with pytest.raises(ValueError, match="grew|changed"):
        family._fingerprint(source, lambda path: None)
    assert observed["appends"] > 0
    assert observed["read_bytes"] <= 129, "Hash chased appended bytes beyond its initial-size budget"


def test_stat_open_replacement_is_rejected_before_content_read(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import family

    source = tmp_path / "d3plot"
    source.write_bytes(b"original")
    original = Path.open
    read_calls = []

    class Unread:
        def __init__(self, stream):
            self.stream = stream

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def fileno(self):
            return self.stream.fileno()

        def read(self, size):
            read_calls.append(size)
            pytest.fail("Replacement identity was read before fstat validation")

        def readinto(self, buffer):
            read_calls.append(len(buffer))
            pytest.fail("Replacement identity was read before fstat validation")

    def switched_open(path, *args, **kwargs):
        if path == source and args and args[0] == "rb":
            source.rename(tmp_path / "original-preserved")
            source.write_bytes(b"replaced")
            return Unread(original(path, *args, **kwargs))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", switched_open)
    with pytest.raises(ValueError, match="between stat and open"):
        family._fingerprint(source, lambda path: None)
    assert not read_calls


def test_internal_state_admission_is_metadata_only_and_cannot_certify_results(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import family

    _, source = fixture_service(tmp_path)
    monkeypatch.setattr(family, "_fingerprint", lambda *a: pytest.fail("State budget admission must not SHA content"))
    with family._state_admission(source) as reader:
        assert not reader.snapshot.hashed
        assert reader.open(constructor=lambda *a, **k: "times", state_array_filter=["timesteps"]) == "times"
        for options in (dict(state_array_filter=["node_velocity"]), dict(state_array_filter=["timesteps"], state_filter={0}), {}):
            with pytest.raises(ValueError, match="only timestep"):
                reader.open(constructor=lambda *a, **k: pytest.fail("Nonmetadata SDK call"), **options)
        with pytest.raises(ValueError, match="cannot certify"), family.reading_family(source, snapshot=reader.snapshot):
            pytest.fail("Weak metadata identity was reused for output evidence")
        with pytest.raises(ValueError, match="cannot be reused"), family.reading_family(source):
            pytest.fail("Implicit strong scope reused an active weak identity")
        with pytest.raises(ValueError, match="cannot be reused"):
            family.open_d3plot(source, constructor=lambda *a, **k: pytest.fail("Weak public metadata call"),
                               state_array_filter=["timesteps"])


@pytest.mark.parametrize("active", [False, True])
@pytest.mark.parametrize("supplied", [False, True])
def test_narrow_nested_guard_stays_active_during_sdk_and_is_restored_after_error(tmp_path, active, supplied):
    from ls_prepost_mcp.domain.results import family

    _, source = fixture_service(tmp_path)
    blocked = source.parent / "unrelated-entry"
    checked = []

    def narrow(path):
        checked.append(path.name)
        if path == blocked:
            raise ValueError("outside nested policy")

    def new_entry(*args, **kwargs):
        blocked.write_bytes(b"owned fixture")
        return "reader"

    snapshot = family.plan_family(source).capture() if supplied else None
    with family.reading_family(source) if active else nullcontext():
        with pytest.raises(ValueError, match="outside nested policy"), family.reading_family(source, guard=narrow, snapshot=snapshot) as inner:
            inner.open(constructor=new_entry, state_array_filter=["timesteps"])
        assert blocked.name in checked
        assert family.open_d3plot(source, constructor=lambda *a, **k: "outer restored") == "outer restored"


@pytest.mark.parametrize("active", [False, True])
@pytest.mark.parametrize("supplied", [False, True])
@pytest.mark.parametrize("deny", [False, True])
def test_guard_policy_matrix_always_applies_and_ordinary_reads_are_strong(tmp_path, active, supplied, deny):
    from ls_prepost_mcp.domain.results import family

    _, source = fixture_service(tmp_path)
    snapshot = family.plan_family(source).capture() if supplied else None
    seen = []

    def guard(path):
        seen.append(path)
        if deny and path == source:
            raise ValueError("outside matrix policy")

    with family.reading_family(source) if active else nullcontext():
        if deny:
            with pytest.raises(ValueError, match="outside matrix policy"), family.reading_family(source, guard=guard, snapshot=snapshot):
                pytest.fail("The provided/active path discarded its current guard")
        else:
            with family.reading_family(source, guard=guard, snapshot=snapshot) as reader:
                assert reader.snapshot.hashed and all(len(row["sha256"]) == 64 for row in reader.snapshot.records)
                assert reader.open(constructor=lambda *a, **k: "strong") == "strong"
    assert source in seen


@pytest.mark.parametrize("entry", ["scalar", "tensor", "history", "overview", "entities"])
def test_new_continuation_during_business_export_never_publishes_success(tmp_path, monkeypatch, entry):
    pytest.importorskip("lasso.dyna")
    from tests.test_field_metrics import write_synthetic

    folder = tmp_path / "source"
    folder.mkdir()
    source = write_synthetic(folder / "d3plot")
    service = Service(Settings(tmp_path / "work", allowed_roots=(folder,)))

    def mutate_after(function):
        def wrapped(*args, **kwargs):
            result = function(*args, **kwargs)
            source.with_name("d3plot99").write_bytes(b"new continuation after the numerical reader returned")
            return result
        return wrapped

    if entry in ("scalar", "tensor"):
        from ls_prepost_mcp.domain.results import export

        monkeypatch.setattr(export, "export_field", mutate_after(export.export_field))
        result = service.extract_field(str(source), "solid", "stress" if entry == "tensor" else "von_mises",
                                       state=3, mask="all", units="MPa", output_format="csv")
    elif entry == "history":
        from ls_prepost_mcp import history_tools

        monkeypatch.setattr(history_tools, "write_csv", mutate_after(history_tools.write_csv))
        result = service.extract_history(str(source), "solid", "sxx", [10], units="MPa", time_units="s")
    elif entry == "overview":
        from ls_prepost_mcp import result_overview

        monkeypatch.setattr(result_overview, "_clock_artifacts", mutate_after(result_overview._clock_artifacts))
        result = service.result_info(str(source))
    else:
        from ls_prepost_mcp import entity_query

        monkeypatch.setattr(entity_query, "_describe", mutate_after(entity_query._describe))
        result = service.query_entities(str(source), {"entity_type": "node", "predicate": {"kind": "ids", "ids": [1]}},
                                        source_kind="d3plot")
    assert source.with_name("d3plot99").exists(), "The fixture must mutate after the actual reader phase"
    assert result["status"] == "failed" and not result.get("artifacts"), result


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


def test_provided_snapshot_cannot_discard_the_callers_narrower_guard(tmp_path):
    from ls_prepost_mcp.domain.results.family import plan_family, reading_family

    _, source = fixture_service(tmp_path)
    snapshot = plan_family(source).capture()
    checked = []

    def deny_source(path):
        checked.append(path)
        if path == source:
            raise ValueError("outside supplied policy")

    with pytest.raises(ValueError, match="outside supplied policy"), reading_family(source, guard=deny_source, snapshot=snapshot):
        pytest.fail("The snapshot discarded the caller's source guard")
    assert source in checked


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
