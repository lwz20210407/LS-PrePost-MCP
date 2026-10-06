"""Q08 visible-session render_xyplot acceptance; needs --run-native --native-gui in an approved GUI window."""

import hashlib
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service

pytestmark = [pytest.mark.native, pytest.mark.gui]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def gui_case(tmp_path, pytestconfig):
    unavailable = pytest.fail if pytestconfig.getoption("--native-strict") else pytest.skip
    if not pytestconfig.getoption("--run-native"):
        pytest.skip("Native regression requires explicit --run-native")
    if not pytestconfig.getoption("--native-gui"):
        unavailable("Requires an operator-approved --native-gui window")
    executable, fixture = pytestconfig.getoption("--native-executable"), pytestconfig.getoption("--native-fixture")
    if not executable or not fixture or not (Path(fixture) / "input.k").is_file():
        unavailable("Set --native-executable and a --native-fixture directory containing input.k")
    model = Path(fixture) / "input.k"
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    service = Service(Settings(tmp_path / "jobs", Path(executable), (Path(fixture), inputs), timeout=120))
    started = service.start_gui_session()
    sid = started["session_id"]
    before = digest(model)
    try:
        opened = service.open_in_gui_session(sid, str(model), discard=True)
        assert opened["status"] == "succeeded", opened
        yield service, sid, inputs
    finally:
        closed = service.close_gui_session(sid, save_checkpoint=False)
        assert closed["state"] == "closed", closed
        assert digest(model) == before


def write_curve(directory, name, rows):
    path = directory / (name + ".csv")
    path.write_text("disp,force\n" + "".join(f"{x!r},{y!r}\n" for x, y in rows), encoding="utf8")
    return path


def spec(path, label):
    return dict(path=str(path), x_column="disp", y_column="force", label=label, x_unit="mm", y_unit="kN")


def check_session_result(result, curve_count):
    assert result["status"] == "succeeded", result
    assert result["route"] == "session" and result["data"]["visible_gui"] is True
    assert result["data"]["curve_count"] == curve_count
    names = {Path(a["path"]).name: a for a in result["artifacts"]}
    assert set(names) == {"plot.png", "curves.csv", "native.xy"}
    consistency = result["data"]["png_csv_consistency"]
    assert consistency["png_sha256"] == digest(names["plot.png"]["path"])
    assert consistency["csv_sha256"] == digest(names["curves.csv"]["path"])
    assert consistency["native_xy_sha256"] == digest(names["native.xy"]["path"])


def test_visible_session_plots_ranges_log_axes_and_replays_a_recording(gui_case):
    service, sid, inputs = gui_case
    cases = {
        "Case A": [(0.0, 0.0), (0.5, 6.25), (1.0, 11.0), (2.0, 17.5), (3.0, 20.0)],
        "Case B": [(0.0, 0.0), (0.75, 8.0), (2.25, 15.5), (3.5, 16.0)],
        "Case C": [(0.0, 0.0), (1.0, 9.0), (2.0, 14.0), (1.0, 7.5), (0.0, 1.5), (1.5, 10.0)],
    }
    curves = [spec(write_curve(inputs, k.replace(" ", "_"), rows), k) for k, rows in cases.items()]
    sources = {c["path"]: digest(c["path"]) for c in curves}
    first = service.render_xyplot(curves, "Three load cases", "Displacement", "Force", "mm", "kN",
                                  x_range=[0, 4], y_range=[0, 25], legend_title="Load case", session_id=sid)
    check_session_result(first, 3)
    with pytest.raises(ValueError):
        service.render_xyplot(curves, "T", "u", "F", "mm", "kN", y_log=True, session_id=sid)

    rows = [[(x, (k + 1) * x ** 1.5) for x in (0.2, 0.5, 1.0, 2.0, 5.0, 8.0)[: 3 + k % 4]] for k in range(10)]
    ten = [spec(write_curve(inputs, f"c{k}", r), f"C{k + 1}") for k, r in enumerate(rows)]
    loglog = service.render_xyplot(ten, "Ten curves", "Displacement", "Force", "mm", "kN", x_log=True, y_log=True,
                                   x_range=[0.1, 10], y_range=[0.1, 1000], session_id=sid)
    check_session_result(loglog, 10)
    assert loglog["data"]["axes"]["native_axes_token"] == "Log-Log"

    growth = write_curve(inputs, "growth", [(0.0, 1.0), (1.0, 10.0), (2.0, 50.0), (3.0, 80.0), (4.0, 100.0)])
    second = write_curve(inputs, "second", [(0.0, 2.0), (2.0, 20.0), (4.0, 90.0)])
    replacement = write_curve(inputs, "replacement", [(0.0, 3.0), (1.0, 5.0), (2.0, 30.0), (3.0, 60.0)])
    assert service.start_session_recording(sid)["recording"]
    recorded = service.render_xyplot([spec(growth, "Growth"), spec(second, "Second")], "Semilog", "Time", "Force",
                                     "mm", "kN", y_log=True, y_range=[1, 100], session_id=sid)
    check_session_result(recorded, 2)
    report = service.stop_session_recording(sid)
    assert report["status"] == "succeeded" and report["managed_steps"] == 1, report
    workflow = json.loads(Path(report["workflow"]).read_text(encoding="utf8"))
    assert [s["action"] for s in workflow["steps"]] == ["render_xyplot"]
    template = service.parameterize_workflow(report["workflow"], [dict(step_id="step1", path=["curves", 1, "path"],
                                                                       parameter="second_curve")])
    replayed = service.run_workflow(template["artifacts"][0]["path"], dict(second_curve=str(replacement)),
                                    session_id=sid)
    assert replayed["status"] == "succeeded", replayed
    step = replayed["data"]["steps"]["step1"]
    check_session_result(step, 2)
    assert step["data"]["axes"]["y_scale"] == "log"
    assert [c["numeric_verification"]["sample_count"] for c in step["data"]["curves"]] == [5, 4]
    assert step["data"]["plot_id"] not in (first["data"]["plot_id"], loglog["data"]["plot_id"],
                                           recorded["data"]["plot_id"])
    first_xy = next(a["path"] for a in first["artifacts"] if a["path"].endswith("native.xy"))
    assert digest(first_xy) == first["data"]["png_csv_consistency"]["native_xy_sha256"]
    assert all(digest(path) == value for path, value in sources.items())
