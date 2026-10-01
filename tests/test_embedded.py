"""Regression fixtures target ID/state/vector semantics, without a vendor runtime."""
import csv
import json
import sys
from types import SimpleNamespace

import pytest

from ls_prepost_mcp import embedded


@pytest.fixture
def model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def get_data(key, *args, **kw):
        data = {"node_ids": [91, 7], "num_states": 2, "state_times": [0, .5],
                "disp_x": [3, 0], "disp_y": [4, 6], "disp_z": [0, 8],
                "velo_x": [1, 4], "velo_y": [2, 5], "velo_z": [3, 6]}
        return data[key]
    monkeypatch.setitem(sys.modules, "DataCenter", SimpleNamespace(get_data=get_data, Type=SimpleNamespace(NODE=0)))
    monkeypatch.setitem(sys.modules, "LsPrePost", SimpleNamespace(switch_state=lambda state: None))
    return tmp_path


def invoke(directory, action, parameters):
    request = directory / "request.json"
    response = directory / "response.json"
    request.write_text(json.dumps({"job_id": "test", "action": action, "parameters": parameters}))
    embedded.run(str(request), str(response))
    return json.loads(response.read_text())


def test_user_ids_do_not_become_array_indices(model):
    r = invoke(model, "extract_nodal", {"quantity": "displacement", "node_ids": [7, 91], "state": 2, "units": "mm"})
    assert r["ok"]
    with (model / "nodal.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert [int(row["node_id"]) for row in rows] == [7, 91]
    assert [float(row["magnitude"]) for row in rows] == [10, 5]
    assert [float(row["time"]) for row in rows] == [.5, .5]


def test_velocity_uses_three_distinct_components(model):
    r = invoke(model, "node_history", {"quantity": "velocity", "node_ids": [91], "states": [1, 2], "units": "mm/ms"})
    assert r["ok"]
    row = r["data"]["preview"][0]
    assert row[3:6] == [1, 2, 3]
    assert row[6] == pytest.approx(14**.5)


def test_native_component_buffers_are_copied_before_next_call(model, monkeypatch):
    original = sys.modules["DataCenter"].get_data
    shared = [0.0, 0.0]
    def reused(key, *args, **kw):
        value = original(key, *args, **kw)
        if key.startswith("velo_"):
            shared[:] = value
            return shared
        return value
    monkeypatch.setattr(sys.modules["DataCenter"], "get_data", reused)
    r = invoke(model, "extract_nodal", {"quantity": "velocity", "node_ids": [91], "state": 1, "units": "mm/ms"})
    assert r["ok"]
    assert r["data"]["preview"][0][3:6] == [1, 2, 3]


def test_unverified_older_native_vector_abi_is_rejected(model, monkeypatch):
    monkeypatch.setattr(embedded, "sys", SimpleNamespace(version_info=(3, 9)))
    r = invoke(model, "extract_nodal", {"quantity": "displacement", "node_ids": [91], "state": 1, "units": "mm"})
    assert not r["ok"]
    assert "cross-checks" in r["error"]["message"]
    assert not (model / "nodal.csv").exists()


@pytest.mark.parametrize("ids,state", [([999], 1), ([91], 0), ([91], 3)])
def test_missing_entities_and_invalid_states_fail(model, ids, state):
    r = invoke(model, "extract_nodal", {"quantity": "displacement", "node_ids": ids, "state": state, "units": "mm"})
    assert not r["ok"]
    assert not (model / "nodal.csv").exists()


@pytest.mark.parametrize("fails", [False, True])
def test_history_restores_state_and_exports_entity_component_curves(model, monkeypatch, fails):
    original = sys.modules["DataCenter"].get_data
    current = [2]

    def get_data(key, *args, **kw):
        if key == "current_state":
            return current[0]
        if fails and key == "disp_x":
            raise RuntimeError("Native result unavailable")
        return original(key, *args, **kw)

    monkeypatch.setattr(sys.modules["DataCenter"], "get_data", get_data)
    monkeypatch.setattr(sys.modules["LsPrePost"], "switch_state", lambda state: current.__setitem__(0, state))
    monkeypatch.setattr(sys.modules["LsPrePost"], "execute_command", lambda command: None, raising=False)
    response = invoke(model, "node_history", dict(
        quantity="displacement", node_ids=[7, 91], states=[1, 2], units="mm",
        curve_components=["x", "magnitude"], time_unit="ms", preserve_state=True,
    ))
    assert current == [2]
    assert response["ok"] is not fails
    if fails:
        assert not (model / "nodal.csv").exists()
    else:
        assert response["data"]["state_restore_requested"] and not response["data"]["state_restored"]
        assert len(response["data"]["curves"]) == 4
        with (model / "node_7_magnitude.csv").open() as stream:
            samples = list(csv.DictReader(stream))
        assert [float(row["value"]) for row in samples] == [10, 10]
        assert [float(row["time"]) for row in samples] == [0, .5]


def test_scalar_curves_reject_reversed_physical_time_before_writing(model):
    response = invoke(model, "node_history", dict(
        quantity="displacement", node_ids=[7], states=[2, 1], units="mm", curve_components=["x"], time_unit="ms",
    ))
    assert not response["ok"] and "physical time" in response["error"]["message"]
    assert not (model / "nodal.csv").exists()


def test_native_cwd_reset_cannot_redirect_nodal_outputs(model, monkeypatch):
    import os

    foreign = model / "application-reset-directory"
    foreign.mkdir()
    monkeypatch.setattr(sys.modules["LsPrePost"], "switch_state", lambda _: os.chdir(foreign))
    response = invoke(model, "node_history", dict(
        quantity="displacement", node_ids=[7], states=[1, 2], units="mm", curve_components=["x"], time_unit="ms",
    ))
    assert response["ok"]
    assert (model / "nodal.csv").is_file() and (model / "node_7_x.csv").is_file()
    assert not list(foreign.iterdir())
