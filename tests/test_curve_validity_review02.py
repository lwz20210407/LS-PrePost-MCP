"""A Q05 deleted/unknown sample must not silently become a Q07 measurement."""
import csv

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


def source(tmp_path, flag, name="history", *, with_alive=True):
    path = tmp_path / (name + ".csv")
    with path.open("w", encoding="utf8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["time", "value", *(["alive"] if with_alive else [])])
        writer.writerows([i * .001, float(i), *([flag if i == 10 else "1"] if with_alive else [])]
                         for i in range(40))
    return path


def invoke(service, path, operation):
    return service.curve_ops([dict(name="history", path=str(path), time_unit="s", value_unit="N")],
                             [dict(operation, input="history", output="result")])


@pytest.mark.parametrize("flag", ["0", "", "2"])
@pytest.mark.parametrize("operation", [dict(op="integrate"), dict(op="sae_filter", cfc=60),
                                       dict(op="resample", dt=.002)])
def test_deleted_unknown_or_malformed_alive_cannot_enter_curve_arithmetic(tmp_path, flag, operation):
    path = source(tmp_path, flag)
    before = path.read_bytes()
    result = invoke(Service(Settings(tmp_path)), path, operation)
    assert result["status"] == "failed", "Deleted/unknown data were silently used as active measurements"
    assert "alive" in result["error"]["message"] and "11" in result["error"]["message"]
    assert not result["artifacts"] and before == path.read_bytes()


@pytest.mark.parametrize("tool", ["convert", "combine", "tensile"])
def test_legacy_arithmetic_uses_the_same_validity_gate(tmp_path, tool):
    path, other = source(tmp_path, "0"), source(tmp_path, "1", "other")
    service = Service(Settings(tmp_path))
    if tool == "convert":
        result = service.convert_history_units(str(path), "N", "kN", "s", "ms")
    elif tool == "combine":
        result = service.combine_history_curves([str(path), str(other)], "difference", "N")
    else:
        result = service.build_tensile_curves(str(path), str(other), area=1, gauge_length=1,
                                              force_unit="N", length_unit="mm", time_unit="s")
    assert result["status"] == "failed" and "alive" in result["error"]["message"]
    assert not result["artifacts"]


@pytest.mark.parametrize("with_alive", [True, False])
def test_validity_provenance_survives_a_multistep_curve_chain(tmp_path, with_alive):
    path = source(tmp_path, "1", with_alive=with_alive)
    service = Service(Settings(tmp_path))
    result = service.curve_ops([dict(name="h", path=str(path), time_unit="s", value_unit="N")],
        [dict(op="integrate", input="h", output="work"),
         dict(op="differentiate", input="work", output="recovered")])
    assert result["status"] == "succeeded", result.get("error")
    for step in result["data"]["steps"]:
        validity = step["input_validity"]["h"]
        assert validity["status"] == ("all_samples_alive" if with_alive else "not_declared")
        assert validity["samples"] == 40 and validity["samples_removed"] == 0
    assert all(a["metadata"]["input_validity"] == result["data"]["steps"][0]["input_validity"]
               for a in result["artifacts"])
    with open(result["artifacts"][0]["path"], encoding="utf8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    column = result["artifacts"][0]["metadata"]["columns"][1]
    np.testing.assert_allclose([float(row[column]) for row in rows], .001 * np.arange(40.) ** 2 / 2)


def test_ambiguous_alive_header_is_rejected(tmp_path):
    path = tmp_path / "ambiguous.csv"
    path.write_text("time,value,alive,alive\n0,1,0,1\n1,2,0,1\n", encoding="utf8")
    result = invoke(Service(Settings(tmp_path)), path, dict(op="integrate"))
    assert result["status"] == "failed" and "alive" in result["error"]["message"]
    assert not result["artifacts"]


@pytest.mark.parametrize("deletion_data", [True, False])
def test_extracted_element_history_cannot_lose_validity_in_curve_ops(tmp_path, monkeypatch, deletion_data):
    from ls_prepost_mcp.domain.results import lasso_backend as lb

    path = tmp_path / "d3plot"
    path.write_bytes(b"owned fake reader; arrays supplied below")
    arrays = dict(timesteps=np.array([0., .5, 1.]), element_solid_ids=np.array([365]),
                  element_solid_effective_plastic_strain=np.array([[.1], [.999], [0.]]))
    if deletion_data:
        arrays["element_solid_is_alive"] = np.array([[1.], [1.], [0.]])
    monkeypatch.setattr(lb, "_arrays", lambda *args, **kwargs: arrays)
    service = Service(Settings(tmp_path))
    history = service.extract_history(str(path), "solid", "effective_plastic_strain", [365],
                                       units="1", time_units="s")
    assert history["status"] == "succeeded", history.get("error")
    artifact = history["artifacts"][0]
    output = service.curve_ops([dict(name="strain", path=artifact["path"], time_unit="s", value_unit="1")],
        [dict(op="integrate", input="strain", output="integral")])
    assert output["status"] == "failed" and "alive" in output["error"]["message"]
    assert not output["artifacts"]
