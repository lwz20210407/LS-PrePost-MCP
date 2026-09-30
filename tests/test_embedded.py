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
