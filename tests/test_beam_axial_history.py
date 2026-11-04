"""Q05 beam force is a stored scalar, joined through user IDs with validity intact."""
import csv
import hashlib
import os
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.results import lasso_backend as lb
from ls_prepost_mcp.service import Service


def arrays(alive=True):
    result = dict(timesteps=np.array([0., .5, 1.]), element_beam_ids=np.array([71, 19]),
                  element_beam_axial_force=np.array([[4., -8.], [5., -9.], [0., -10.]]))
    if alive:
        result["element_beam_is_alive"] = np.array([[1, 1], [1, 1], [0, 1]])
    return result


def test_beam_axial_history_uses_user_ids_not_positions_and_keeps_deleted_values():
    records = lb._history_from_arrays(arrays(), "beam", "axial_force", [19, 71])
    assert [row["entity"] for row in records] == [19, 71]
    assert records[0]["values"] == [-8., -9., -10.]
    assert records[1]["values"] == [4., 5., 0.]
    assert records[1]["alive"] == [True, True, False]
    assert records[1]["deleted_from_state"] == 3
    assert records[0]["source_array"] == "element_beam_axial_force"
    assert records[0]["coordinate_frame"] == "as stored"
    assert records[0]["sampling"]["kind"] == "stored_scalar"
    assert records[0]["sampling"]["index"] is None


def test_beam_axial_history_reads_only_force_time_and_alive_states(monkeypatch):
    def read(path, *, state_arrays):
        assert set(state_arrays) == {"timesteps", "element_beam_axial_force", "element_beam_is_alive"}
        return arrays()

    monkeypatch.setattr(lb, "_arrays", read)
    assert lb.history("owned fake input", "beam", "axial_force", [71])[0]["values"] == [4., 5., 0.]


def test_beam_axial_history_does_not_guess_alive_when_missing():
    record = lb._history_from_arrays(arrays(False), "beam", "axial_force", [71])[0]
    assert record["alive"] is None and record["deletion_status"] == "unknown"
    assert record["deleted_from_state"] is None


@pytest.mark.parametrize("point", [1, 2])
def test_beam_axial_force_never_interprets_stored_point_as_a_component(point):
    with pytest.raises(lb.ResultsError, match="stored_point.*scalar|scalar.*stored_point"):
        lb._history_from_arrays(arrays(), "beam", "axial_force", [71], stored_point=point)


@pytest.mark.parametrize("fault", ["missing_force", "vector", "wrong_states", "fractional_ids", "duplicate_ids", "id_matrix",
                                    "nonfinite", "not_numeric", "missing_ids"])
def test_beam_axial_history_refuses_missing_or_ambiguous_storage(fault):
    data = arrays()
    if fault == "missing_force":
        del data["element_beam_axial_force"]
    elif fault == "vector":
        data["element_beam_axial_force"] = np.ones((3, 2, 2))
    elif fault == "wrong_states":
        data["element_beam_axial_force"] = np.ones((2, 2))
    elif fault == "fractional_ids":
        data["element_beam_ids"] = np.array([71.5, 19.5])
    elif fault == "duplicate_ids":
        data["element_beam_ids"] = np.array([71, 71])
    elif fault == "id_matrix":
        data["element_beam_ids"] = np.array([[71, 19]])
    elif fault == "nonfinite":
        data["element_beam_axial_force"][0, 0] = np.nan
    elif fault == "missing_ids":
        del data["element_beam_ids"]
    else:
        data["element_beam_axial_force"] = np.full((3, 2), "not a force")
    with pytest.raises(lb.ResultsError):
        lb._history_from_arrays(data, "beam", "axial_force", [71])


def test_nonfinite_other_beam_does_not_contaminate_requested_finite_history():
    data = arrays()
    data["element_beam_axial_force"][0, 0] = np.nan
    assert lb._history_from_arrays(data, "beam", "axial_force", [19])[0]["values"] == [-8., -9., -10.]


def test_backend_sampling_metadata_is_not_shared_between_entity_records():
    records = lb._history_from_arrays(arrays(), "beam", "axial_force", [71, 19])
    records[0]["sampling"]["count"] = 999
    assert records[1]["sampling"]["count"] == 1


@pytest.mark.parametrize("alive", [True, False], ids=["stored_validity", "unknown_validity"])
def test_public_beam_axial_history_exports_named_force_and_validity(tmp_path, monkeypatch, alive):
    source = tmp_path / "d3plot"
    source.write_bytes(b"owned source; reader injected")
    original = source.read_bytes()
    monkeypatch.setattr(lb, "_arrays", lambda *args, **kwargs: arrays(alive))
    service = Service(Settings(tmp_path / "jobs", allowed_roots=(tmp_path,)))
    result = service.extract_history(str(source), "beam", "axial_force", [19, 71], units="N", time_units="ms")
    assert result["status"] == "succeeded", result.get("error")
    assert [curve["entity_id"] for curve in result["data"]["curves"]] == [19, 71]
    for artifact in result["artifacts"]:
        meta = artifact["metadata"]
        assert meta["source_array"] == "element_beam_axial_force"
        assert meta["coordinate_frame"] == "as stored"
        assert meta["units"] == {"time": "ms", "value": "N"}
        with Path(artifact["path"]).open(encoding="utf8", newline="") as stream:
            reader = csv.DictReader(stream)
            assert reader.fieldnames == ["time", "value", "alive"]
            rows = list(reader)
        expected = [-8., -9., -10.] if meta["entity_id"] == 19 else [4., 5., 0.]
        assert [float(row["value"]) for row in rows] == expected
        flags = ["1", "1", "1"] if meta["entity_id"] == 19 else ["1", "1", "0"]
        assert [row["alive"] for row in rows] == (flags if alive else ["", "", ""])
    assert source.read_bytes() == original


def test_beam_native_check_is_explicitly_unsupported_without_starting_a_native_job(tmp_path, monkeypatch):
    source = tmp_path / "d3plot"
    source.write_bytes(b"owned source; reader injected")
    monkeypatch.setattr(lb, "_arrays", lambda *args, **kwargs: arrays())
    service = Service(Settings(tmp_path / "jobs", allowed_roots=(tmp_path,)))
    monkeypatch.setattr(service, "extract_native_fields", lambda *a, **kw: pytest.fail("No native beam mapping exists"))
    result = service.extract_history(str(source), "beam", "axial_force", [71], units="N", time_units="s",
                                     native_check=True)
    assert result["status"] == "failed"
    assert "Native beam history comparison is unsupported" in result["error"]["message"]
    assert not result["artifacts"]


@pytest.mark.parametrize("units,time_units", [("MPa", "s"), ("J", "s"), ("N", "mm")])
def test_known_wrong_dimensions_are_rejected_before_a_beam_job(tmp_path, units, time_units):
    service = Service(Settings(tmp_path / "jobs", allowed_roots=(tmp_path,)))
    with pytest.raises(ValueError, match="force value unit and a time unit"):
        service.extract_history(str(tmp_path / "unused-d3plot"), "beam", "axial_force", [71],
                                units=units, time_units=time_units)
    assert service.jobs.list() == []


@pytest.mark.parametrize("units,time_units", [("kN", "ms"), ("kg*mm/ms^2", "s"), ("model_force", "model_time")])
def test_force_units_are_declared_not_converted_or_inferred(tmp_path, monkeypatch, units, time_units):
    source = tmp_path / "d3plot"
    source.write_bytes(b"owned source; reader injected")
    monkeypatch.setattr(lb, "_arrays", lambda *args, **kwargs: arrays())
    service = Service(Settings(tmp_path / "jobs", allowed_roots=(tmp_path,)))
    result = service.extract_history(str(source), "beam", "axial_force", [19],
                                     units=units, time_units=time_units)
    assert result["status"] == "succeeded", result.get("error")
    meta = result["artifacts"][0]["metadata"]
    assert meta["quantity_dimension"] == "force"
    assert meta["units"] == {"time": time_units, "value": units}
    with Path(result["artifacts"][0]["path"]).open(encoding="utf8", newline="") as stream:
        assert [float(row["value"]) for row in csv.DictReader(stream)] == [-8., -9., -10.]
    if units == "model_force":
        assert meta["unit_validation"] == dict(value="caller_declared_unverified", time="caller_declared_unverified")
        assert any("without dimensional verification" in warning for warning in result["warnings"])
    else:
        assert all(value == "dimension_checked; scale not converted" for value in meta["unit_validation"].values())


def test_public_scalar_beam_force_rejects_a_stored_point_before_creating_a_job(tmp_path):
    service = Service(Settings(tmp_path / "jobs", allowed_roots=(tmp_path,)))
    with pytest.raises(ValueError, match="stored_point.*scalar"):
        service.extract_history(str(tmp_path / "unused-d3plot"), "beam", "axial_force", [71],
                                units="N", time_units="s", stored_point=1)
    assert service.jobs.list() == []


@pytest.mark.parametrize("ids", [[True], [71.5], ["71"], [71, 71]])
def test_beam_force_requires_unambiguous_requested_user_ids(ids):
    with pytest.raises(lb.ResultsError, match="unique positive user IDs"):
        lb._history_from_arrays(arrays(), "beam", "axial_force", ids)


def test_beam_force_retains_shared_input_family_identity_check(tmp_path, monkeypatch):
    source = tmp_path / "d3plot"
    source.write_bytes(b"before")
    def read(*args, **kwargs):
        source.write_bytes(b"changed during read")
        return arrays()
    monkeypatch.setattr(lb, "_arrays", read)
    service = Service(Settings(tmp_path / "jobs", allowed_roots=(tmp_path,)))
    result = service.extract_history(str(source), "beam", "axial_force", [71], units="N", time_units="s")
    assert result["status"] == "failed"
    assert "changed during extraction" in result["error"]["message"]


def test_beam_axial_history_roundtrips_an_actual_d3plot_with_sparse_ids(tmp_path):
    dyna = pytest.importorskip("lasso.dyna")
    from tests.test_field_metrics import write_synthetic

    seed = write_synthetic(tmp_path / "seed-d3plot")
    plot = dyna.D3plot(str(seed))
    kind = dyna.ArrayType
    plot.arrays[kind.element_beam_ids] = np.array([71, 19])
    plot.arrays[kind.element_beam_part_indexes] = np.array([0, 1])
    plot.arrays[kind.element_beam_node_indexes] = np.array([[0, 1, 2, 0, 0], [3, 4, 5, 0, 0]])
    plot.arrays[kind.element_beam_axial_force] = arrays()["element_beam_axial_force"]
    plot.arrays[kind.element_beam_is_alive] = arrays()["element_beam_is_alive"].astype(float)
    root = tmp_path / "beam"
    root.mkdir()
    source = root / "d3plot"
    plot.write_d3plot(str(source))
    record = lb.history(source, "beam", "axial_force", [19, 71])
    assert [row["entity"] for row in record] == [19, 71]
    assert record[0]["values"] == [-8., -9., -10.]
    assert record[1]["values"] == [4., 5., 0.]
    assert record[1]["alive"] == [True, True, False]


@pytest.mark.parametrize("corpus_id", [
    "result.ansys__example-data.result_files.d3plot_beam",
    "result.open-lasso-python__lasso-python.test.test_data.d3plot_beamip",
])
def test_public_beam_axial_history_equals_stored_lasso_columns(tmp_path, corpus_id):
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        pytest.skip("Set LSPP_CORPUS_DIR for existing registered public beam data")
    dyna = pytest.importorskip("lasso.dyna")
    import yaml

    manifest = yaml.safe_load((Path(__file__).parent / "corpus/manifest.yaml").read_text(encoding="utf8"))
    entry = next(row for rows in manifest.values() if isinstance(rows, list)
                 for row in rows if isinstance(row, dict) and row.get("id") == corpus_id)
    source = Path(location) / entry["path"] / "d3plot"
    assert source.is_file(), "Registered public beam data was requested but is unavailable"
    service = Service(Settings(tmp_path / "jobs", allowed_roots=(Path(location),)))
    family = service._result_family(str(source))

    def fingerprint():
        result = {}
        for path in family:
            with path.open("rb") as stream:
                result[path.name] = hashlib.file_digest(stream, "sha256").hexdigest()
        return result

    before = fingerprint()
    names = dyna.ArrayType
    plot = dyna.D3plot(str(source), state_array_filter=[names.global_timesteps, names.element_beam_axial_force,
                                                     names.element_beam_is_alive])
    raw = np.asarray(plot.arrays[names.element_beam_axial_force])
    stored_ids = np.asarray(plot.arrays[names.element_beam_ids])
    assert raw.ndim == 2 and stored_ids.ndim == 1 and raw.shape[1] == stored_ids.size
    nonzero = np.flatnonzero(np.any(raw != 0, axis=0))
    pick = list(dict.fromkeys([int(nonzero[0]) if nonzero.size else 0, stored_ids.size - 1]))[::-1]
    ids = [int(stored_ids[index]) for index in pick]
    records = lb.history(source, "beam", "axial_force", ids)
    assert [record["entity"] for record in records] == ids
    for index, record in zip(pick, records):
        np.testing.assert_array_equal(record["values"], raw[:, index])
        np.testing.assert_array_equal(record["time"], plot.arrays[names.global_timesteps])
        if names.element_beam_is_alive in plot.arrays:
            assert record["alive"] == (plot.arrays[names.element_beam_is_alive][:, index] != 0).tolist()
        else:
            assert record["deletion_status"] == "unknown" and record["alive"] is None
    result = service.extract_history(str(source), "beam", "axial_force", ids,
                                     units="caller_force_units", time_units="caller_time_units")
    assert result["status"] == "succeeded", result.get("error")
    for index, artifact in zip(pick, result["artifacts"]):
        assert artifact["metadata"]["unit_validation"]["value"] == "caller_declared_unverified"
        with Path(artifact["path"]).open(encoding="utf8", newline="") as stream:
            values = [float(row["value"]) for row in csv.DictReader(stream)]
        np.testing.assert_array_equal(values, raw[:, index])
    assert fingerprint() == before
