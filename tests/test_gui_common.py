import math

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.gui_common import check_measurement
from ls_prepost_mcp.service import Service


def test_native_distance_and_height_are_not_confused():
    data = dict(node_positions=[[10, 1., 2., 3.], [30, 4., 6., 15.]],
                native_values=[[13., 3., 4., 12.]])
    result = check_measurement(data, "height", "z", "")
    assert result["distance"] == 13 and result["height"] == result["signed_height"] == 12
    data["native_values"][0][0] = 12.
    with pytest.raises(ValueError, match="distance/components"):
        check_measurement(data, "distance", "z", "")


def test_circle_center_must_come_from_a_matching_native_message():
    data = dict(node_positions=[[1, 0., 0., 0.], [2, 2., 0., 0.], [3, 0., 4., 0.]],
                native_values=[[math.sqrt(5)]])
    text = "Radius formed by 1 2 3 = 2.23607, center: 1,2,0\n"
    result = check_measurement(data, "circle3", "z", text)
    assert result["center"] == [1, 2, 0] and result["center_backend"] == "lsprepost-message-log"
    for bad in ("", text+text, text.replace("1,2,0", "7,2,0")):
        with pytest.raises(ValueError):
            check_measurement(data, "circle3", "z", bad)


def test_native_angle_preserves_uninterpreted_projected_components():
    data = dict(node_positions=[[11, 1., 0., 0.], [22, 0., 0., 0.], [33, 0., 1., 0.]],
                native_values=[[90., 90., 0., 0.]])
    assert check_measurement(data, "angle3", "z", "")["angle_degrees"] == 90
    data["native_values"][0][0] = 45.
    with pytest.raises(ValueError, match="angle"):
        check_measurement(data, "angle3", "z", "")


@pytest.mark.parametrize("mode,ids,state,axis", [
    ("height", [1], None, "z"), ("circle3", [1, 2, 3], True, "z"),
    ("other", [1, 2], None, "z"), ("distance", [1, True], None, "z"),
    ("height", [1, 2], None, "zz"),
])
def test_invalid_measurements_fail_before_launch(tmp_path, mode, ids, state, axis):
    with pytest.raises(ValueError):
        Service(Settings(tmp_path)).measure_gui_geometry("missing", mode, ids, "mm", axis=axis, state=state)
    assert not (tmp_path/"sessions").exists()
