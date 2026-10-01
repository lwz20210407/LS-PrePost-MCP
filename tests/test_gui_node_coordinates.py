import copy

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.gui_node_edit import verify_coordinates
from ls_prepost_mcp.service import Service


def mesh():
    return dict(
        nodes=[[1, 0, 0, 0], [2, 2, 0, 0], [3, 2, 1, 0], [4, 0, 1, 0]],
        elements=[dict(type="shell", id=100, nodes=[1, 2, 3, 4])],
        part_ids=[10],
        part_elements={"10": [100]},
        part_visibility={"10": False},
    )


def test_absolute_axis_targets_group_translations_and_preserve_other_axes(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))

    def edit(sid, action, arguments, commands, verify, precheck, snapshot_parameters=None):
        assert snapshot_parameters == dict(node_ids=[2, 3])
        before = mesh()
        precheck(before)
        native = commands(before, tmp_path)
        assert native.count("translate_model accept") == 1
        assert "translate_model 1.0 0.0 0.0" in native and native[-1] == "-m 10"
        after = copy.deepcopy(before)
        after["nodes"][1][1] = after["nodes"][2][1] = 3
        return verify(before, after)

    monkeypatch.setattr(service, "_gui_mesh_edit", edit)
    result = service.set_gui_node_coordinates(
        "s", [dict(id=n, coordinates=[3, None, None]) for n in (2, 3)], "mm"
    )
    assert result["changed_count"] == 2 and result["affected_element_count"] == 1
    assert result["unrequested_nodes_preserved"]


@pytest.mark.parametrize("change", ["target", "other", "topology", "part_flags"])
def test_absolute_coordinate_verification_rejects_collateral_changes(change):
    before, after = mesh(), mesh()
    after["nodes"][1][1] = 3
    if change == "target":
        after["nodes"][1][1] += 0.01
    elif change == "other":
        after["nodes"][0][2] += 0.00001
    elif change == "topology":
        after["elements"][0]["nodes"].reverse()
    else:
        after["part_visibility"]["10"] = True
    with pytest.raises(ValueError):
        verify_coordinates(before, after, {2: np.asarray([3, 0, 0])}, 1e-6)


@pytest.mark.parametrize(
    "nodes",
    [
        [],
        [dict(id=True, coordinates=[0, 1, 2])],
        [dict(id=1, coordinates=[None, None, None])],
        [dict(id=1, coordinates=[True, 0, 0])],
        [dict(id=1, coordinates=[float("inf"), 0, 0])],
        [dict(id=1, coordinates=[0, 0, 0])] * 2,
    ],
)
def test_invalid_coordinate_requests_do_not_create_jobs(tmp_path, nodes):
    service = Service(Settings(tmp_path))
    with pytest.raises(ValueError):
        service.set_gui_node_coordinates("s", nodes, "mm")
    assert not (tmp_path / "jobs").exists()
