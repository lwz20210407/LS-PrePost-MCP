import csv
from types import SimpleNamespace

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.result_validity import (
    PhysicalValidity,
    mask_from_database,
    reject_adaptive_family,
    scalar_statistics,
)
from ls_prepost_mcp.service import Service


def mask(codes=((2, 0), (0, 3))):
    return PhysicalValidity("solid", np.array([303, 101]), np.asarray(codes), {2: 0, 5: 1}, np.array([.2, .5]))


def test_material_codes_sparse_ids_and_reactivation_are_state_specific():
    status = mask()
    assert status.alive(2, 303) and not status.alive(2, 101)
    assert not status.alive(5, 303) and status.alive(5, 101)
    report = status.describe([101, 303], [5, 2])
    assert [s["state"] for s in report["states"]] == [5, 2]
    assert report["states"][0]["active_material_code_sample"] == [3]
    with pytest.raises(ValueError, match="times disagree"):
        status.check_time(2, .5)


@pytest.mark.parametrize("bad", [float("nan"), -1, .5, float("inf")])
def test_unknown_deletion_codes_are_not_cast_to_true(bad):
    with pytest.raises(ValueError, match="material codes"):
        mask(((2, bad), (0, 3)))


def test_missing_mask_and_node_visibility_are_not_element_validity():
    db = SimpleNamespace(header=SimpleNamespace(n_adapted_element_pairs=0, has_element_deletion_data=False), arrays={})
    with pytest.raises(ValueError, match="unavailable"):
        mask_from_database(db, {1: 0}, "solid")
    with pytest.raises(ValueError, match="nodal visibility"):
        mask_from_database(db, {1: 0}, "node")


def test_adaptive_family_detection_does_not_reject_numeric_state_files(tmp_path):
    source = tmp_path / "d3plot"
    source.touch()
    (tmp_path / "d3plot01").touch()
    reject_adaptive_family(source)
    (tmp_path / "d3plotaa").touch()
    with pytest.raises(ValueError, match="Adaptive mesh"):
        reject_adaptive_family(source)


def test_empty_statistics_and_ties_have_explicit_provenance():
    assert scalar_statistics([], ["s"])["s"] == dict(count=0, minimum=None, maximum=None)
    rows = [dict(state=5, entity_id=9, s=10), dict(state=2, entity_id=7, s=10)]
    stats = scalar_statistics(rows, ["s"])["s"]
    assert stats["maximum"] == dict(value=10., state=2, entity_id=7)


@pytest.mark.parametrize("policy,count,maximum", [("raw", 2, 999.), ("alive", 1, 10.)])
def test_rigid_shell_result_layout_uses_user_id_mask_alignment(tmp_path, monkeypatch, policy, count, maximum):
    pytest.importorskip("lasso")
    source = tmp_path / "d3plot"
    source.write_bytes(b"synthetic")
    values = np.zeros((1, 2, 1, 6))
    values[0, :, 0, 0] = [10., 999.]
    arrays = dict(element_shell_ids=np.array([10, 20, 30]), element_shell_part_indexes=np.array([0,1,0]),
                  part_material_type=np.array([1,20]), element_shell_stress=values,
                  element_shell_is_alive=np.array([[1.,2.,0.]]), timesteps=np.array([1.]))
    db = SimpleNamespace(arrays=arrays, header=SimpleNamespace(n_adapted_element_pairs=0, has_element_deletion_data=True))
    monkeypatch.setattr("ls_prepost_mcp.post_tools.selected_database", lambda *a: (db, {1:0}))
    result = Service(Settings(tmp_path)).extract_d3plot_stress(str(source), "shell", [30,10], [1], 1, "MPa", validity_policy=policy)
    assert result["status"] == "succeeded", result
    assert result["data"]["row_count"] == count
    assert result["data"]["statistics"]["von_mises"]["maximum"]["value"] == maximum


def test_deleted_nan_is_filtered_before_tensor_math_and_all_deleted_is_empty(tmp_path, monkeypatch):
    pytest.importorskip("lasso")
    source = tmp_path / "d3plot"
    source.write_bytes(b"synthetic")
    db = SimpleNamespace(arrays=dict(element_solid_ids=np.array([10]), element_solid_stress=np.full((1,1,1,6), np.nan),
                                    element_solid_is_alive=np.array([[0.]]), timesteps=np.array([1.])),
                         header=SimpleNamespace(n_adapted_element_pairs=0, has_element_deletion_data=True))
    monkeypatch.setattr("ls_prepost_mcp.post_tools.selected_database", lambda *a: (db, {1:0}))
    service = Service(Settings(tmp_path))
    result = service.extract_d3plot_stress(str(source), "solid", [10], [1], 1, "MPa", validity_policy="alive")
    assert result["status"] == "succeeded" and result["data"]["row_count"] == 0
    assert result["data"]["statistics"]["von_mises"]["maximum"] is None
    assert result["data"]["empty_reason"] == "all_requested_entities_deleted"
    assert service.extract_d3plot_stress(str(source), "solid", [10], [1], 1, "MPa")["status"] == "failed"


def test_native_deleted_nan_filtered_before_native_mises_comparison(tmp_path, monkeypatch):
    from ls_prepost_mcp.native_results import STRESS_KEYS
    source = tmp_path / "input" / "d3plot"
    source.parent.mkdir()
    source.write_bytes(b"synthetic")
    exe = tmp_path / "fake.exe"
    exe.touch()
    status = PhysicalValidity("solid", np.array([7,101]), np.array([[2.,0.]]), {2:0}, np.array([1.]))
    monkeypatch.setattr("ls_prepost_mcp.native_results.load_physical_validity", lambda *a: status)
    def execute(exe, command, directory, **kwargs):
        with (directory / "native.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["state", "time", "entity_id", *STRESS_KEYS, "von_mises"])
            writer.writerow([2,1,7,10,0,0,0,0,0,10])
            writer.writerow([2,1,101,*(["nan"]*7)])
        return dict(returncode=0, timed_out=False)
    monkeypatch.setattr("ls_prepost_mcp.native_results.execute", execute)
    result = Service(Settings(tmp_path / "jobs-root", exe, allowed_roots=(source.parent,))).extract_native_stress(
        str(source), "solid", [101,7], [2], "mid", "MPa", validity_policy="alive")
    assert result["status"] == "succeeded", result
    assert result["data"]["row_count"] == 1 and result["data"]["excluded_deleted_count"] == 1
    assert result["data"]["derived_statistics"]["von_mises"]["maximum"] == dict(value=10., state=2, entity_id=7)
