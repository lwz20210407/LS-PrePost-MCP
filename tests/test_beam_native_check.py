"""Q05 beam comparison: named 4.13 reference, bounded IO, never a new engine."""

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp import history_tools, runner
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.domain.results import lasso_backend as lb
from ls_prepost_mcp.engine import environment
from ls_prepost_mcp.native import versions
from ls_prepost_mcp.service import Service
from tests.test_beam_axial_history import arrays


@pytest.fixture
def case(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "d3plot"
    source.write_bytes(b"owned fake d3plot")
    (source_dir / "d3plot01").write_bytes(b"owned continuation")
    executable = tmp_path / "native.exe"
    executable.write_bytes(b"trusted fake binary")
    config = tmp_path / "lsppconf"
    config.write_bytes(b"trusted fake config")
    service = Service(Settings(tmp_path / "work", executable, (source_dir,), timeout=7))
    profile = dict(version="4.13", version_source="file_version_resource", resource_conflict=False)
    monkeypatch.setattr(Settings, "native_executable", lambda self: self.executable)
    monkeypatch.setattr(versions, "require_capability", lambda *a: dict(profile))
    monkeypatch.setattr(environment, "locate_config", lambda *a: config)
    monkeypatch.setattr(lb, "state_times", lambda *a: arrays()["timesteps"])
    monkeypatch.setattr(lb, "_arrays", lambda *a, **kw: arrays())
    context = dict(service=service, source=source, executable=executable, config=config,
                   profile=profile, executions=[], mutation=None, fault=None)

    def execute(executable, cfile, directory, **kwargs):
        context["executions"].append(dict(directory=directory, **kwargs))
        assert not kwargs["graphics"] and kwargs["timeout"] == 7
        assert 'runpython "beam-reference.py"' in cfile.read_text(encoding="utf8")
        plan = json.loads((directory / "beam-plan.json").read_text(encoding="utf8"))
        records = lb._history_from_arrays(arrays(), "beam", "axial_force", plan["entity_ids"])
        rows = [[state, r["time"][state-1], r["entity"], r["values"][state-1]]
                for state in plan["states"] for r in records]
        fault = context["fault"]
        if fault == "duplicate":
            rows[-1] = rows[0]
        elif fault == "missing":
            rows.pop()
        elif fault == "wrong_id":
            rows[0][2] = 999
        elif fault == "wrong_state":
            rows[0][0] = 0
        elif fault == "nonfinite":
            rows[0][3] = "nan"
        elif fault == "value":
            rows[0][3] += 1
        elif fault == "time":
            rows[0][1] += .1
        with (directory / "native-beam.csv").open("w", encoding="utf8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["state", "time", "entity_id", "axial_force"])
            writer.writerows(rows)
        marker = dict(complete=True, beam_count=2, state_count=3, field="axial_force",
                      entity_ids=plan["entity_ids"], requested_states=plan["states"],
                      ipt="binding default; semantics not independently identified",
                      python_version=[3, 11], rows=len(rows))
        if fault == "marker":
            marker["complete"] = False
        elif fault == "count":
            marker["beam_count"] = 3
        elif fault == "abi":
            marker["python_version"] = [3, 6]
        elif fault == "sampling":
            marker["ipt"] = "MID"
        if fault != "no_marker":
            (directory / "native-beam-marker.json").write_text(json.dumps(marker), encoding="utf8")
        if context["mutation"] is not None:
            context["mutation"](directory)
        if fault == "engine":
            return JobResult(operation=kwargs["operation"], job_id=directory.name, status="failed",
                             backend="lsprepost", error=dict(type="FakeError", message="engine diagnostic"))
        return JobResult(operation=kwargs["operation"], job_id=directory.name, status="unverified",
                         backend="lsprepost", data=dict(test_double=True))

    monkeypatch.setattr(runner, "run_batch", execute)
    return context


def extract(case, **kwargs):
    return case["service"].extract_history(str(case["source"]), "beam", "axial_force", [19, 71],
        units="N", time_units="ms", native_check=True, native_sampling="default", **kwargs)


def test_default_beam_native_check_uses_existing_batch_boundary_and_preserves_validity(case):
    result = extract(case)
    assert result["status"] == "succeeded", result.get("error")
    comparison = result["data"]["native_comparison"]
    assert comparison["max_absolute_error"] == comparison["max_time_absolute_error"] == 0
    assert comparison["native_sampling"] == "default"
    assert comparison["ipt"] == "binding default; semantics not independently identified"
    assert comparison["coordinate_frame"] == "as stored"
    assert comparison["native_channel"] == "embedded_python"
    assert len(case["executions"]) == 1
    manifest = case["service"].jobs.get(comparison["job_ids"][0])
    assert manifest["native_channel"] == "embedded_python"
    assert manifest["native_identity_checks"] and all(manifest["native_identity_checks"].values())
    assert (Path(manifest["job_directory"]) / "engine-result.json").is_file()
    curves = result["data"]["curves"]
    assert [r["entity_id"] for r in curves] == [19, 71]
    assert curves[1]["deleted_from_state"] == 3 and curves[1]["coordinate_frame"] == "as stored"


def test_lasso_beam_reference_reports_total_stored_registry_count():
    selected = lb._history_from_arrays(arrays(), "beam", "axial_force", [19])
    assert selected[0]["stored_entity_count"] == 2


@pytest.mark.parametrize("version,source,conflict", [
    ("4.10", "file_version_resource", False), ("4.13", "path_hint", False),
    (None, "path_hint", False), ("4.13", "file_version_resource", True),
])
def test_unsupported_beam_profiles_reject_before_family_or_lasso(case, monkeypatch, version, source, conflict):
    case["profile"].update(version=version, version_source=source, resource_conflict=conflict)
    monkeypatch.setattr(case["service"], "_result_family", lambda *a: pytest.fail("Unneeded family IO"))
    monkeypatch.setattr(lb, "_arrays", lambda *a, **kw: pytest.fail("Unneeded LASSO IO"))
    with pytest.raises(ValueError, match="4.13.*resource|resource.*4.13"):
        extract(case)
    assert not case["executions"] and not case["service"].jobs.list()


def test_state_budget_rejects_before_force_reads_hashes_or_staging(case, monkeypatch):
    monkeypatch.setattr(lb, "state_times", lambda *a: np.arange(1001, dtype=float))
    monkeypatch.setattr(lb, "_arrays", lambda *a, **kw: pytest.fail("Unneeded force read"))
    monkeypatch.setattr(history_tools, "_sha", lambda *a: pytest.fail("Unneeded family hash"))
    with pytest.raises(ValueError, match="1000 states"):
        extract(case)
    assert not case["executions"] and not case["service"].jobs.list()


def test_staging_budget_rejects_before_time_read_or_hash(case, monkeypatch):
    from ls_prepost_mcp import native_results

    monkeypatch.setattr(native_results, "exceeds_staging_limit", lambda *a: True)
    monkeypatch.setattr(lb, "state_times", lambda *a: pytest.fail("Unneeded times read"))
    monkeypatch.setattr(history_tools, "_sha", lambda *a: pytest.fail("Unneeded family hash"))
    with pytest.raises(ValueError, match="1000 files / 2 GiB"):
        extract(case)
    assert not case["executions"] and not case["service"].jobs.list()


@pytest.mark.parametrize("fault", ["duplicate", "missing", "wrong_id", "wrong_state", "nonfinite",
    "value", "time", "marker", "count", "abi", "sampling", "no_marker", "engine"])
def test_unverified_native_outputs_never_publish_verified_curves(case, fault):
    case["fault"] = fault
    result = extract(case)
    assert result["status"] == "failed", result
    assert result["error"]["message"] and not result["artifacts"]
    assert len(case["executions"]) == 1
    if fault == "engine":
        assert "engine diagnostic" in result["error"]["message"]


@pytest.mark.parametrize("target", ["source", "staged", "source_listing", "staged_listing", "binary", "config"])
def test_native_identity_failures_preserve_failed_status(case, target):
    def mutate(directory):
        paths = dict(source=case["source"], staged=directory / "d3plot",
                     source_listing=case["source"].parent / "unexpected.txt",
                     staged_listing=directory / "d3plot02", binary=case["executable"], config=case["config"])
        paths[target].write_bytes(b"changed")
    case["mutation"] = mutate
    result = extract(case)
    assert result["status"] == "failed" and not result["artifacts"]
    assert "identity" in result["error"]["message"].lower()


def test_source_change_during_history_read_is_rejected_before_native(case, monkeypatch):
    def read(*a, **kw):
        case["source"].write_bytes(b"changed before staging")
        return arrays()
    monkeypatch.setattr(lb, "_arrays", read)
    result = extract(case)
    assert result["status"] == "failed" and not case["executions"]


def test_full_sha_guard_does_not_accept_metadata_only_large_file_fingerprints(case, monkeypatch):
    from ls_prepost_mcp import native_results

    # Model the generic >64 MiB shortcut without allocating a large file.
    monkeypatch.setattr(native_results, "fingerprint", lambda path:
        dict(path=str(path), size=65*1024**2, mtime_ns=1, sha256=None))
    case["mutation"] = lambda directory: case["source"].write_bytes(b"modified despite metadata-only identity")
    result = extract(case)
    assert result["status"] == "failed" and not result["artifacts"]
    assert "input_family_unchanged" in result["error"]["message"]


def test_history_time_registry_must_match_the_admission_snapshot(case, monkeypatch):
    monkeypatch.setattr(lb, "state_times", lambda *a: np.array([0., .5, 2.]))
    result = extract(case)
    assert result["status"] == "failed" and "state times changed" in result["error"]["message"]
    assert not case["executions"]


@pytest.mark.parametrize("quantity", ["effective_plastic_strain", "sxx"])
def test_other_beam_quantities_remain_rejected_without_lasso(case, monkeypatch, quantity):
    monkeypatch.setattr(case["service"], "_result_family", lambda *a: pytest.fail("Unneeded family IO"))
    monkeypatch.setattr(lb, "_arrays", lambda *a, **kw: pytest.fail("Unneeded state IO"))
    with pytest.raises(ValueError, match="axial_force"):
        case["service"].extract_history(str(case["source"]), "beam", quantity, [71], units="N",
                                       time_units="s", native_check=True, native_sampling="default")
    assert not case["executions"]


def test_default_native_sampling_still_applies_the_input_guard(case):
    with pytest.raises(ValueError, match="outside"):
        case["service"].extract_history(str(case["executable"]), "beam", "axial_force", [71],
            units="N", time_units="s", native_check=True, native_sampling="default")
    assert not case["executions"]


def test_mid_sampling_remains_rejected_before_family_loading(case, monkeypatch):
    monkeypatch.setattr(case["service"], "_result_family", lambda *a: pytest.fail("Unneeded family IO"))
    with pytest.raises(ValueError, match="native_sampling='default'"):
        case["service"].extract_history(str(case["source"]), "beam", "axial_force", [71],
            units="N", time_units="s", native_check=True)
    assert not case["executions"]


@pytest.mark.parametrize("fault", [None, "ids", "count", "force_axis", "nan"])
def test_reference_script_copies_borrowed_vectors_and_uses_named_default(tmp_path, monkeypatch, fault):
    import sys
    from types import SimpleNamespace

    from ls_prepost_mcp.native_beam_history import script

    monkeypatch.chdir(tmp_path)
    plan = dict(beam_count=2, state_count=3, entity_ids=[19, 71], states=[1, 2, 3])
    (tmp_path / "beam-plan.json").write_text(json.dumps(plan), encoding="utf8")
    shared, calls = [], []

    def get_data(name, **kwargs):
        calls.append((name, kwargs))
        shared[:] = [999, 999]
        if name == "num_beam_elements":
            return 9 if fault == "count" else 2
        if name == "num_states":
            return 3
        if name == "element_ids":
            shared[:] = [71, 71] if fault == "ids" else [71, 19]
        elif name == "state_times":
            shared[:] = [0., .5, 1.]
        elif name == "axial_force":
            assert kwargs == dict(type="BEAM", ist=kwargs["ist"])  # no numeric selector or ipt
            shared[:] = arrays()["element_beam_axial_force"][kwargs["ist"]-1].tolist()
            if fault == "force_axis":
                shared.pop()
            elif fault == "nan":
                shared[0] = float("nan")
        else:
            pytest.fail("Unexpected DataCenter field: " + name)
        return shared

    monkeypatch.setitem(sys.modules, "DataCenter", SimpleNamespace(Type=SimpleNamespace(BEAM="BEAM"), get_data=get_data))
    if fault is None:
        exec(compile(script(), "beam-reference.py", "exec"), {})
        with (tmp_path / "native-beam.csv").open(newline="", encoding="utf8") as stream:
            rows = list(csv.DictReader(stream))
        assert [float(row["time"]) for row in rows] == [0., 0., .5, .5, 1., 1.]
        assert [float(row["axial_force"]) for row in rows] == [-8., 4., -9., 5., -10., 0.]
        assert len([name for name, _ in calls if name == "axial_force"]) == 3
    else:
        with pytest.raises(ValueError):
            exec(compile(script(), "beam-reference.py", "exec"), {})
        marker = json.loads((tmp_path / "native-beam-marker.json").read_text(encoding="utf8"))
        assert marker["complete"] is False and marker["error"]


def test_reference_checks_runtime_vector_abi_before_data_reads(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from ls_prepost_mcp.native_beam_history import script

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(versions, "MINIMUM_VECTOR_ABI", (99, 0))
    monkeypatch.setitem(sys.modules, "DataCenter", SimpleNamespace(
        get_data=lambda *a, **kw: pytest.fail("Unverified ABI read a vector")))
    with pytest.raises(RuntimeError, match="ABI"):
        exec(compile(script(), "beam-reference.py", "exec"), {})
