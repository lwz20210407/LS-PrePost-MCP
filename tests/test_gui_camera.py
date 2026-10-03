import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.gui_controls import camera_commands
from ls_prepost_mcp.service import Service
from tools.run_gui_camera_acceptance import raster_equivalent_arrays


def test_camera_rotation_order_and_absolute_setters():
    rotations, after_fit = camera_commands(1.5, [0.1, -0.2], [15, 0, -30])
    assert rotations == ["rotang 15", "rx", "rotang -30", "rz"]
    assert after_fit[0] == "zoom 1.5"
    assert [float(v) for v in after_fit[1].split()[1:]] == [0.1, -0.2]


@pytest.mark.parametrize("arguments", [
    dict(zoom_scale=0), dict(zoom_scale=True), dict(zoom_scale=float("nan")),
    dict(pan_xy=[0]), dict(pan_xy=[False, 0]), dict(pan_xy=[0, float("inf")]),
    dict(rotation_xyz_degrees=[0, 361, 0]), dict(rotation_xyz_degrees=[0, "15", 0]),
])
def test_invalid_camera_requests_are_rejected_without_native_side_effects(tmp_path, arguments):
    with pytest.raises(ValueError):
        Service(Settings(tmp_path)).set_gui_display("missing", **arguments)
    assert not list(tmp_path.iterdir())


def test_raster_tolerance_does_not_accept_large_camera_or_color_changes():
    before = np.full((30,30,3),255,dtype=np.uint8)
    before[10:20,10:20] = [100,0,0]
    one = np.full_like(before,255)
    one[10:20,11:21] = [100,0,0]
    far = np.full_like(before,255)
    far[10:20,13:23] = [100,0,0]
    wrong_color = before.copy()
    wrong_color[10:20,10:20] = [0,100,0]
    assert raster_equivalent_arrays(before,one)
    assert not raster_equivalent_arrays(before,far)
    assert not raster_equivalent_arrays(before,wrong_color)
