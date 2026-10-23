"""Q03 six-component extraction through the existing shared reader/exporter."""
import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.results import export as exp
from ls_prepost_mcp.domain.results import lasso_backend as lb
from ls_prepost_mcp.service import Service
from tests.test_field_metrics import write_synthetic

pytest.importorskip("lasso.dyna")


@pytest.fixture
def model(tmp_path):
    folder = tmp_path / "source"
    folder.mkdir()
    return write_synthetic(folder / "d3plot")


@pytest.mark.parametrize("family,parts,ids,expected", [
    ("solid", [7], [10, 20], [[200,0,0,0,0,0], [0,0,0,60,0,0]]),
    ("shell", [300], [101,102], [[300,0,0,0,0,0], [0,0,0,80,0,0]]),
])
def test_six_components_export_and_shared_readback(model, tmp_path, family, parts, ids, expected):
    service = Service(Settings(tmp_path / "work", allowed_roots=(model.parent,)))
    result = service.extract_field(str(model), family, "stress", state=3, mask="all",
                                   units="MPa", output_format="both", part_ids=parts)
    assert result["status"] == "succeeded", result.get("error")
    assert result["data"]["components"] == list(lb.STRESS)
    assert result["data"]["shape"] == [2,6]
    assert result["data"]["state"] == 3 and result["data"]["time"] == 1
    assert len(result["artifacts"]) == 2
    for artifact in result["artifacts"]:
        back = exp.read_field(artifact["path"])
        assert back["ids"].tolist() == ids
        np.testing.assert_array_equal(back["values"], expected)
        assert back["alive"].tolist() == [True,False]
        assert back["meta"]["components"] == list(lb.STRESS)
        assert back["meta"]["units"] == "MPa" and back["meta"]["state_index_base"] == 1
        assert back["meta"]["sampling"]["kind"] == "mean_stored_points"


def test_shared_reader_tensor_uses_one_existing_array_load(model, monkeypatch):
    original = lb._arrays
    calls = []

    def arrays(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(lb, "_arrays", arrays)
    result = lb.field(model, "solid", "stress", state=2, mask="all", part_ids=[7])
    assert len(calls) == 1 and result["values"].shape == (2,6)
    assert result["extrema"]["sxy"]["max"]["id"] == 20


@pytest.mark.parametrize("mask,expected", [("alive",[30,40]),("deleted",[])])
def test_tensor_masks_empty_shape_and_unknown_deletion(model, tmp_path, mask, expected):
    service = Service(Settings(tmp_path / "work", allowed_roots=(model.parent,)))
    result = service.extract_field(str(model), "solid", "stress", state=3, mask=mask,
                                   part_ids=[9], units="MPa", output_format="both")
    assert result["status"] == "succeeded", result.get("error")
    for artifact in result["artifacts"]:
        back = exp.read_field(artifact["path"])
        assert back["ids"].tolist() == expected and back["values"].shape == (len(expected),6)


def test_tensor_units_required_before_job_creation(model, tmp_path):
    service = Service(Settings(tmp_path / "work", allowed_roots=(model.parent,)))
    with pytest.raises(ValueError, match="units"):
        service.extract_field(str(model), "solid", "stress", mask="all")
    assert not service.jobs.list()


@pytest.mark.parametrize("fault", [None, "missing_id", "duplicate_id", "value", "state", "time", "failed"])
def test_native_check_compares_independent_export_without_replacing_reader_values(model, tmp_path, monkeypatch, fault):
    import csv
    import hashlib

    service = Service(Settings(tmp_path / "work", allowed_roots=(model.parent,)))

    def native(path, family, ids, states, fields, sampling, units):
        assert family == "solid" and ids == [10,20] and states == [3] and sampling == "mid"
        directory, manifest = service.jobs.create("native-test", {})
        output = directory / "results.csv"
        rows = [[3,1.,10,200.,0.,0.,0.,0.,0.], [3,1.,20,0.,0.,0.,60.,0.,0.]]
        if fault == "missing_id":
            rows.pop()
        elif fault == "duplicate_id":
            rows.append(rows[0])
        elif fault == "value":
            rows[0][3] = 999
        elif fault == "state":
            rows[0][0] = 2
        elif fault == "time":
            rows[0][1] = 0.5
        with output.open("w", newline="", encoding="utf8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["state", "time", "entity_id", *fields])
            writer.writerows(rows)
        return {"status": "failed" if fault == "failed" else "succeeded", "job_id": manifest["job_id"],
                "error": {"message":"native failed"} if fault == "failed" else None,
                "artifacts": [{"kind":"csv","path":str(output),"sha256":hashlib.sha256(output.read_bytes()).hexdigest()}]}

    monkeypatch.setattr(service, "extract_native_fields", native)
    result = service.extract_field(str(model), "solid", "stress", state=3, mask="all", units="MPa",
                                   part_ids=[7], native_check=True)
    assert result["status"] == ("failed" if fault else "succeeded")
    if fault:
        assert result["error"] and not result["artifacts"]
    else:
        assert result["data"]["native_comparison"]["max_absolute_error"] == 0
        assert result["data"]["backend"].startswith("lasso")
        assert result["data"]["native_comparison"]["backend"] == "lsprepost"


def test_stored_point_changes_values_without_claiming_layer_equivalence(model, tmp_path, monkeypatch):
    original = lb._arrays(model)
    stress = np.repeat(original["element_shell_stress"], 3, axis=2)
    stress[:,:,1,:] += 10
    stress[:,:,2,:] += 20
    original["element_shell_stress"] = stress
    monkeypatch.setattr(lb, "_arrays", lambda *a, **k: original)
    service = Service(Settings(tmp_path / "work", allowed_roots=(model.parent,)))
    rows=[]
    for point in (1,2,3):
        result = service.extract_field(str(model), "shell", "stress", state=3, mask="all", units="MPa", stored_point=point)
        assert result["status"] == "succeeded", result.get("error")
        rows.append(result["data"]["preview"]["values"])
        assert result["data"]["sampling"]["index"] == point
        assert result["data"]["sampling"]["native_layer_equivalence"] == "not inferred"
    assert rows[0] != rows[1] != rows[2]
    bad=service.extract_field(str(model), "shell", "stress", state=3, mask="all", units="MPa", stored_point=4)
    assert bad["status"] == "failed" and not bad["artifacts"]


def test_family_changes_cannot_publish_verified_tensor_artifacts(model, tmp_path, monkeypatch):
    service = Service(Settings(tmp_path / "work", allowed_roots=(model.parent,)))
    original = exp.export_field

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        model.write_bytes(model.read_bytes()+b"changed")
        return result

    monkeypatch.setattr(exp, "export_field", changed)
    result=service.extract_field(str(model), "solid", "stress", units="MPa", mask="all")
    assert result["status"] == "failed" and not result["artifacts"]
    assert "family changed" in result["error"]["message"]
