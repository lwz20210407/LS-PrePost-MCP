"""Tests for Q11 geometric and physical measurements (LSPP F4 Measure tool)."""

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.measure import (
    MeasurementError,
    measure_angle,
    measure_clearance,
    measure_dihedral,
    measure_distance,
    measure_part_geometry_and_physics,
    measure_point_to_plane_distance,
)
from ls_prepost_mcp.service import Service


def test_measure_distance_and_components():
    p1 = np.array([10.0, 20.0, 30.0])
    p2 = np.array([13.0, 24.0, 30.0])  # dx=3, dy=4, dz=0 => dist=5

    res = measure_distance(p1, p2, node_ids=[101, 102], units="mm")
    assert res["distance"] == pytest.approx(5.0)
    assert res["dx"] == pytest.approx(3.0)
    assert res["dy"] == pytest.approx(4.0)
    assert res["dz"] == pytest.approx(0.0)
    assert res["node_ids"] == [101, 102]


def test_measure_angle_orthogonal_and_collinear():
    pv = np.array([0.0, 0.0, 0.0])
    p1 = np.array([1.0, 0.0, 0.0])
    p2 = np.array([0.0, 2.0, 0.0])

    res = measure_angle(p1, pv, p2, node_ids=[1, 2, 3])
    assert res["angle_degrees"] == pytest.approx(90.0)
    assert res["angle_radians"] == pytest.approx(np.pi / 2.0)


def test_measure_dihedral():
    p1 = np.array([0.0, 1.0, 0.0])
    p2 = np.array([0.0, 0.0, 0.0])
    p3 = np.array([1.0, 0.0, 0.0])
    p4 = np.array([1.0, 0.0, 1.0])  # Plane 2 is rotated 90 deg into Z

    res = measure_dihedral(p1, p2, p3, p4)
    assert res["angle_degrees"] == pytest.approx(90.0)


def test_measure_point_to_plane_distance():
    # Plane z = 0
    a = np.array([0.0, 0.0, 0.0])
    b = np.array([10.0, 0.0, 0.0])
    c = np.array([0.0, 10.0, 0.0])
    target = np.array([5.0, 5.0, 12.5])

    res = measure_point_to_plane_distance(target, a, b, c, units="mm")
    assert res["distance"] == pytest.approx(12.5)
    assert res["projected_point"] == pytest.approx([5.0, 5.0, 0.0])


def test_measure_part_volume_mass_inertia_and_rejection_without_density():
    # 8-node unit cube [0, 10] x [0, 10] x [0, 10] => Vol = 1000 mm^3
    nodes = {
        1: np.array([0.0, 0.0, 0.0]),
        2: np.array([10.0, 0.0, 0.0]),
        3: np.array([10.0, 10.0, 0.0]),
        4: np.array([0.0, 10.0, 0.0]),
        5: np.array([0.0, 0.0, 10.0]),
        6: np.array([10.0, 0.0, 10.0]),
        7: np.array([10.0, 10.0, 10.0]),
        8: np.array([0.0, 10.0, 10.0]),
    }
    elements = [[1, 2, 3, 4, 5, 6, 7, 8]]

    # 1. Volume
    res_vol = measure_part_geometry_and_physics(nodes, elements, measurement="volume", part_id=1)
    assert res_vol["total_volume"] == pytest.approx(1000.0)

    # 2. Rejection of mass measurement without density
    with pytest.raises(MeasurementError, match="explicit positive density"):
        measure_part_geometry_and_physics(nodes, elements, measurement="mass", density=None, units="kg")

    # 3. Rejection of mass without unit
    with pytest.raises(MeasurementError, match="explicit units"):
        measure_part_geometry_and_physics(nodes, elements, measurement="mass", density=7.85e-6, units="")

    # 4. Valid mass and center of mass
    res_mass = measure_part_geometry_and_physics(
        nodes, elements, measurement="mass", density=7.85e-6, units="kg", density_units="kg/mm^3", part_id=1
    )
    assert res_mass["total_mass"] == pytest.approx(1000.0 * 7.85e-6)

    res_com = measure_part_geometry_and_physics(
        nodes, elements, measurement="center_of_mass", density=7.85e-6, units="mm", density_units="kg/mm^3"
    )
    assert res_com["center_of_mass"] == pytest.approx([5.0, 5.0, 5.0])


def test_measure_clearance():
    # Set 1: centered around origin
    s1 = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    # Set 2: offset along X
    s2 = np.array([[5.0, 0.0, 0.0], [10.0, 0.0, 0.0]])

    res = measure_clearance(s1, s2, set1_ids=[1, 2], set2_ids=[10, 20], units="mm")
    # Closest pair is (1, 0, 0) and (5, 0, 0) => clearance = 4.0
    assert res["minimum_clearance"] == pytest.approx(4.0)
    assert res["closest_node_id_set1"] == 2
    assert res["closest_node_id_set2"] == 10


def test_service_measure_end_to_end(tmp_path):
    service = Service(Settings(tmp_path))

    res = service.measure(
        measurement="distance",
        node_coords=[[0.0, 0.0, 0.0], [0.0, 10.0, 0.0]],
        node_ids=[1, 2],
        units="mm",
    )

    assert res["status"] == "succeeded"
    data = res["data"]
    assert data["distance"] == 10.0
    assert data["units"] == "mm"
