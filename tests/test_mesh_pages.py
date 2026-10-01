import json
import sys
from types import SimpleNamespace

import pytest

from ls_prepost_mcp import embedded
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


def run_page(tmp_path, monkeypatch, kind, offset, limit):
    calls = []
    size = 300006
    # SDK-style non-sliceable array: accidental whole-array copying fails.
    class NativeArray:
        def __init__(self, scale):
            self.scale = scale

        def __len__(self):
            return size

        def __getitem__(self, i):
            assert type(i) is int and offset <= i < min(offset + limit, size)
            return (i + 1) * self.scale

    def get(key, **kwargs):
        calls.append((key, kwargs))
        if key in ("num_nodes", "num_elements"):
            return size
        if key in ("num_states", "current_state"):
            return 1
        if key == "validpart_ids":
            return [1]
        if key == "state_times":
            return [0.0]
        if key in ("node_ids", "element_ids"):
            return NativeArray(10)
        if key in ("node_x", "node_y", "node_z"):
            return NativeArray({"node_x": 1, "node_y": 2, "node_z": 3}[key])
        if key == "element_connectivity":
            return [1, 2, 3, 4, 4, 4, 4, 4]
        raise AssertionError(key)

    monkeypatch.setitem(sys.modules, "DataCenter", SimpleNamespace(
        get_data=get, Type=SimpleNamespace(NODE=0, SHELL=1, SOLID=2, BEAM=3)))
    monkeypatch.setitem(sys.modules, "LsPrePost", SimpleNamespace())
    request, response = tmp_path / "request.json", tmp_path / "response.json"
    request.write_text(json.dumps(dict(job_id="page", action="gui_mesh_page", parameters=dict(
        entity_type=kind, offset=offset, limit=limit))))
    embedded.run(str(request), str(response))
    return json.loads(response.read_text()), calls


def test_large_model_connectivity_reads_only_requested_page(tmp_path, monkeypatch):
    result, calls = run_page(tmp_path, monkeypatch, "solid", 300000, 1000)
    assert result["ok"], result
    data = result["data"]
    assert data["total"] == 300006 and data["returned"] == 6
    assert data["next_offset"] is None
    assert data["elements"][0]["id"] == 3000010
    assert sum(k == "element_connectivity" for k, _ in calls) == 6
    assert not any(k.startswith("node_") for k, _ in calls)


def test_node_page_materializes_only_coordinate_slice(tmp_path, monkeypatch):
    result, _ = run_page(tmp_path, monkeypatch, "node", 20000, 2)
    assert result["ok"], result
    assert result["data"]["nodes"] == [[200010, 20001, 40002, 60003], [200020, 20002, 40004, 60006]]
    assert result["data"]["next_offset"] == 20002


def test_page_past_end_is_empty(tmp_path, monkeypatch):
    result, calls = run_page(tmp_path, monkeypatch, "solid", 400000, 10)
    assert result["ok"]
    assert result["data"]["elements"] == [] and result["data"]["next_offset"] is None
    assert not any(k == "element_connectivity" for k, _ in calls)


@pytest.mark.parametrize("kwargs", [dict(entity_type="tet"), dict(entity_type="node", offset=True),
    dict(entity_type="node", limit=5001), dict(entity_type="node", offset=-1), dict(offset=10)])
def test_invalid_page_rejected_before_native_launch(tmp_path, kwargs):
    with pytest.raises(ValueError):
        Service(Settings(tmp_path)).inspect_gui_mesh("absent", **kwargs)
    assert not (tmp_path / "jobs").exists()
