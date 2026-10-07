"""G01 opt-in native check: identical set_view requests in one owned GUI session render identical pixels.

Needs --run-native, --native-gui (an authorized visible window) and --native-executable. Never runs in CI.
"""

import os
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.view_state import compare_png_pixels

pytestmark = pytest.mark.native

PLATE = """*KEYWORD
*TITLE
G01 original view fixture
*NODE
1,0.0,0.0,0.0
2,10.0,0.0,0.0
3,20.0,0.0,0.0
4,0.0,10.0,0.0
5,10.0,10.0,0.0
6,20.0,10.0,0.0
*SECTION_SHELL
1,2,,,,,,,
1.0,1.0,1.0,1.0
*MAT_ELASTIC
1,7.85e-9,210000.0,0.3
*PART
left
1,1,1
*PART
right
2,1,1
*ELEMENT_SHELL
1,1,1,2,5,4
2,2,2,3,6,5
*END
"""

CASES = {
    "standard_rotation_zoom_pan": dict(view="front", projection="parallel", rotation_xyz_degrees=[15, 0, -30],
                                       zoom_scale=2.0, pan_xy=[0.1, -0.05]),
    "fit": dict(view="isometric", projection="perspective", fit=True),
}


@pytest.fixture
def gui_service(pytestconfig, tmp_path):
    if not pytestconfig.getoption("--run-native") or not pytestconfig.getoption("--native-gui"):
        pytest.skip("G01 pixel identity needs --run-native and an authorized --native-gui window")
    executable = pytestconfig.getoption("--native-executable")
    if not executable or os.name != "nt":
        pytest.skip("Set --native-executable on Windows")
    model = tmp_path / "plate.k"
    model.write_text(PLATE, encoding="ascii")
    service = Service(Settings(tmp_path, Path(executable), (), 90))
    session = service.start_gui_session()["session_id"]
    try:
        assert service.open_in_gui_session(session, str(model))["status"] == "succeeded"
        yield service, session
    finally:
        service.close_gui_session(session, save_checkpoint=False)


@pytest.mark.parametrize("case", sorted(CASES))
def test_identical_requests_render_identical_pixels(gui_service, case):
    service, session = gui_service
    first = service.set_view("session", session_id=session, **CASES[case])
    second = service.set_view("session", session_id=session, **CASES[case])
    assert first["status"] == second["status"] == "succeeded"
    assert first["job_id"] != second["job_id"]
    comparison = compare_png_pixels(first["artifacts"][0]["path"], second["artifacts"][0]["path"])
    assert comparison["identical"], comparison


def test_preset_restore_after_perturbation_renders_identical_pixels(gui_service):
    service, session = gui_service
    saved = service.set_view("session", session_id=session, save_preset_name="g01native",
                             **CASES["standard_rotation_zoom_pan"])
    service.set_view("session", session_id=session, view="top", zoom_scale=0.5, capture=False)
    restored = service.set_view("session", session_id=session, restore_preset_name="g01native")
    comparison = compare_png_pixels(saved["artifacts"][0]["path"], restored["artifacts"][0]["path"])
    assert comparison["identical"], comparison
