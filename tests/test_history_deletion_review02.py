"""P1-6: a deleted sample cannot silently look like zero strain/stress."""
import csv
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.results import lasso_backend as lb
from ls_prepost_mcp.service import Service


def arrays():
    return {"timesteps": np.array([0., .5, 1.]), "element_solid_ids": np.array([365]),
            "element_solid_effective_plastic_strain": np.array([[.1], [.999], [0.]]),
            "element_solid_stress": np.array([[[10., 0., 0., 0., 0., 0.]],
                                               [[20., 0., 0., 0., 0., 0.]], [[0., 0., 0., 0., 0., 0.]]]),
            "element_solid_is_alive": np.array([[1.], [1.], [0.]])}


@pytest.mark.parametrize("quantity", ["effective_plastic_strain", "von_mises", "sxx"])
def test_element_history_returns_sample_alive_and_first_deleted_state(quantity):
    record = lb._history_from_arrays(arrays(), "solid", quantity, [365])[0]
    assert record.get("alive") == [True, True, False]
    assert record["deletion_status"] == "stored"
    assert record["deleted_from_state"] == 3
    assert record["values"][-1] == 0.  # retained as raw storage, explicitly invalid


def test_history_without_alive_data_is_unknown_not_all_active():
    data = arrays()
    del data["element_solid_is_alive"]
    record = lb._history_from_arrays(data, "solid", "sxx", [365])[0]
    assert record.get("deletion_status") == "unknown"
    assert record["alive"] is None and record["deleted_from_state"] is None


@pytest.mark.parametrize("bad", [np.array([[1.], [0.]]), np.array([[1.], [np.nan], [0.]])])
def test_invalid_alive_axis_cannot_be_ignored(bad):
    data = arrays()
    data["element_solid_is_alive"] = bad
    with pytest.raises(lb.ResultsError, match="alive|deletion"):
        lb._history_from_arrays(data, "solid", "sxx", [365])


def test_incomplete_scalar_result_axis_cannot_be_joined_to_a_larger_id_registry():
    data = arrays()
    data["element_solid_ids"] = np.array([365, 500])
    with pytest.raises(lb.ResultsError, match="axes|registry"):
        lb._history_from_arrays(data, "solid", "sxx", [365])


def test_history_requests_only_its_quantity_time_and_validity_state_arrays(monkeypatch):
    def requested(path, *, state_arrays=None):
        assert set(state_arrays or []) == {"timesteps", "element_solid_stress", "element_solid_is_alive"}
        return arrays()

    monkeypatch.setattr(lb, "_arrays", requested)
    assert lb.history("owned-injected-source", "solid", "sxx", [365])[0]["deleted_from_state"] == 3


@pytest.mark.parametrize("stored", [True, False], ids=["deleted", "unknown"])
def test_public_history_csv_exposes_alive_and_never_guesses_validity(tmp_path, monkeypatch, stored):
    data = arrays()
    if not stored:
        del data["element_solid_is_alive"]
    source = tmp_path / "d3plot"
    source.write_bytes(b"owned dummy source for the injected reader")
    original = source.read_bytes()
    monkeypatch.setattr(lb, "_arrays", lambda *a, **kw: data)
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    result = service.extract_history(str(source), "solid", "effective_plastic_strain", [365], units="1", time_units="s")
    assert result["status"] == "succeeded", result.get("error")
    artifact = result["artifacts"][0]
    with Path(artifact["path"]).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ["time", "value", "alive"]
        rows = list(reader)
    assert [r["alive"] for r in rows] == (["1", "1", "0"] if stored else ["", "", ""])
    assert [float(r["value"]) for r in rows] == [.1, .999, 0.]
    assert artifact["metadata"]["deletion_status"] == ("stored" if stored else "unknown")
    assert artifact["metadata"]["deleted_from_state"] == (3 if stored else None)
    assert result["warnings"]
    assert source.read_bytes() == original
