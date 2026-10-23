"""Q01 malformed native observations must remain JSON-safe diagnostic results."""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.domain.results import lasso_backend as lb
from ls_prepost_mcp.service import Service

REAL_OVERVIEW = lb.overview


@pytest.fixture
def service(tmp_path, monkeypatch):
    (tmp_path / "d3plot").write_bytes(b"controlled reader input")
    overview = dict(backend="test-reader", states=3, times=[0., .001, .002], time_range=[0., .002],
        variables=[], elements={}, parts=[], binout_files=[], binout_databases=[], binout_entries={},
        binout_split={}, ascii_files=[])
    monkeypatch.setattr(lb, "overview", lambda path: dict(overview))
    monkeypatch.setattr(lb, "header", lambda path: dict(neiph_solid=0, neips_shell_tshell=0, neipb_beam=0))
    return Service(Settings(tmp_path))


def _native(states=3, times=None):
    return dict(status="succeeded", job_id="native-observation", executable={"version": "test"},
                data=dict(counts=dict(states=states), state_times=times))


@pytest.mark.parametrize("times", [[float("nan"), .001, .002], [0., float("nan"), .002],
    [0., .001, float("inf")], [0., -float("inf"), .002], [0., "not-a-number", .002],
    [0., None, .002], [0., True, .002], [[0.], [.001], [.002]], "0,.001,.002", [0., 10 ** 400, .002]])
def test_invalid_native_times_return_partial_and_record_diagnostic(service, monkeypatch, tmp_path, times):
    monkeypatch.setattr(service, "inspect_model", lambda *args: _native(times=times))
    payload = service.result_info("d3plot", native_check=True)
    result = JobResult.model_validate_json(json.dumps(payload, allow_nan=False))
    assert result.status == "partial" and result.error["message"]
    assert result.check_status != "passed"
    assert result.data["times"] == [0., .001, .002]
    assert result.data["lsprepost"]["times"] is None
    assert result.data["lsprepost"]["job_id"] == "native-observation"
    record = json.loads((tmp_path / "jobs" / result.job_id / "job.json").read_text(encoding="utf-8"))
    assert record["status"] == "partial" and record["result"] == payload


@pytest.mark.parametrize("count", [float("nan"), float("inf"), True, "3", -1])
def test_invalid_native_state_count_does_not_escape_result_contract(service, monkeypatch, count):
    monkeypatch.setattr(service, "inspect_model", lambda *args: _native(states=count, times=[0., .001, .002]))
    result = JobResult.model_validate_json(json.dumps(service.result_info("d3plot", native_check=True), allow_nan=False))
    assert result.status == "partial" and result.error["message"]
    assert result.data["lsprepost"]["states"] is None
    assert result.check_status != "passed"


def test_finite_clock_difference_overflow_is_json_safe_disagreement(service, monkeypatch):
    original = lb.overview
    monkeypatch.setattr(lb, "overview", lambda path: {
        **original(path), "states": 2, "times": [-1.7e308, -1.6e308], "time_range": [-1.7e308, -1.6e308]})
    monkeypatch.setattr(service, "inspect_model", lambda *args: _native(2, [1.6e308, 1.7e308]))
    result = JobResult.model_validate_json(json.dumps(service.result_info("d3plot", native_check=True), allow_nan=False))
    assert result.status == "succeeded" and result.check_status == "failed"
    assert result.data["comparison"]["max_abs_time_difference"] is None
    assert result.data["comparison"]["times_equal"] is False


def _arrays(monkeypatch, ids=(20, 10), titles=(b"upper", b"lower")):
    data = {"timesteps": np.array([0., 1.]), "part_ids": np.array([10, 20]),
            "part_titles": np.array(titles)}
    if ids is not None:
        data["part_titles_ids"] = np.array(ids)
    monkeypatch.setattr(lb, "_arrays", lambda path: data)


def test_part_titles_are_joined_by_stored_id_not_position(tmp_path, monkeypatch):
    _arrays(monkeypatch)
    overview = lb.overview(tmp_path / "d3plot")
    assert overview["parts"] == [{"id": 10, "title": "lower"}, {"id": 20, "title": "upper"}]


def test_titles_without_stored_title_ids_are_not_guessed(tmp_path, monkeypatch):
    _arrays(monkeypatch, ids=None)
    overview = lb.overview(tmp_path / "d3plot")
    assert all(part["title"] is None for part in overview["parts"])
    assert overview["warnings"]


def test_title_mapping_warning_reaches_public_result(service, monkeypatch):
    original = lb.overview
    monkeypatch.setattr(lb, "overview", lambda path: {**original(path), "warnings": ["Missing title IDs"]})
    result = JobResult.model_validate(service.result_info("d3plot"))
    assert "Missing title IDs" in result.warnings


def test_overview_keeps_every_time_beyond_the_old_2000_state_cutoff(tmp_path, monkeypatch):
    times = np.linspace(0., 2., 2001)
    monkeypatch.setattr(lb, "_arrays", lambda path: {"timesteps": times})
    overview = lb.overview(tmp_path / "d3plot")
    assert overview["states"] == 2001
    assert overview["times"] == times.tolist()


@pytest.mark.parametrize("native_check", [False, True])
def test_long_inventory_is_complete_and_comparable(service, monkeypatch, native_check):
    times = np.linspace(0., 2., 2001)
    monkeypatch.setattr(lb, "overview", REAL_OVERVIEW)
    monkeypatch.setattr(lb, "_arrays", lambda path: {"timesteps": times})
    monkeypatch.setattr(service, "inspect_model", lambda *args: _native(2001, times.tolist()))
    result = JobResult.model_validate(service.result_info("d3plot", native_check=native_check))
    assert result.status == "succeeded", result.error
    assert result.data["times"] == times.tolist()
    assert not any("2000" in message for message in result.warnings)
    if native_check:
        assert result.data["comparison"]["times_equal"]
        assert result.check_status == "passed"


@pytest.mark.parametrize("ids", [(10, 10), (10,), (10, 0), (10, 1.5)])
def test_ambiguous_or_malformed_title_identity_is_degraded(tmp_path, monkeypatch, ids):
    _arrays(monkeypatch, ids=ids)
    result = lb.overview(tmp_path / "d3plot")
    assert all(part["title"] is None for part in result["parts"]) and result["warnings"]


@pytest.mark.parametrize("corpus_id,states,parts", [
    ("result.ansys__example-data.result_files.d3plot_projectile", 16, 2),
    ("shell_d3plot", 7, 4),
    ("result.hu-shuhan__editOpeniGame.test.Format_Validation_Test.lsdyna.Bolt_B_Explicit", 102, 7),
])
def test_public_overview_preserves_inventory_and_source(tmp_path, corpus_id, states, parts):
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        pytest.skip("Set LSPP_CORPUS_DIR to use registered public overview cases")
    pytest.importorskip("lasso.dyna")

    from tools.fetch_corpus import entries, load_registry, plain_path, resolve

    root = Path(location)
    source = plain_path(resolve(entries(load_registry())[corpus_id], root))
    if source.is_dir():
        source = source / "d3plot"
    family = [p for p in source.parent.iterdir() if p.is_file() and (
        p.name == source.name or p.name.startswith(source.name) and p.name[len(source.name):].isdigit())]
    before = {}
    for path in family:
        with path.open("rb") as stream:
            before[path] = hashlib.file_digest(stream, "sha256").hexdigest()
    listing = sorted(p.name for p in source.parent.iterdir())
    result = JobResult.model_validate(Service(Settings(tmp_path / "jobs", allowed_roots=(root,)))
                                     .result_info(str(source)))
    assert result.status == "succeeded", result.error
    assert result.data["states"] == states and len(result.data["parts"]) == parts
    assert result.data["part_title_mapping"] in ("stored_user_ids", "internal_ordinal", "absent", "unconfirmed")
    for path, sha in before.items():
        with path.open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == sha
    assert sorted(p.name for p in source.parent.iterdir()) == listing
