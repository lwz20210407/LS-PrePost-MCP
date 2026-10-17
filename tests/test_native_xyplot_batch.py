"""Q08 no-graphics native XYPlot acceptance on original public CSV curves."""

import csv
import hashlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageChops

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service

pytestmark = pytest.mark.native


@pytest.fixture
def xyplot_case(tmp_path, pytestconfig):
    if not pytestconfig.getoption("--run-native"):
        pytest.skip("Native regression requires explicit --run-native")
    executable = pytestconfig.getoption("--native-executable")
    if not executable:
        if pytestconfig.getoption("--native-strict"):
            pytest.fail("Q08 native XYPlot requires an LS-PrePost executable")
        pytest.skip("Set --native-executable or LSPP_ENGINE_EXECUTABLE for Q08 native XYPlot")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    # Job manifests and artifacts stay under the external --native-output basetemp.
    return Service(Settings(tmp_path / "jobs", Path(executable), (inputs,), timeout=120)), inputs


def write_curve(directory, name, rows):
    path = directory / (name + ".csv")
    path.write_text("disp,force\n" + "".join(f"{x!r},{y!r}\n" for x, y in rows), encoding="utf8")
    return path


def spec(path, label):
    return dict(path=str(path), x_column="disp", y_column="force", label=label, x_unit="mm", y_unit="kN")


def native_blocks(path):
    lines = [line.split() for line in path.read_text(encoding="utf8").splitlines() if line.strip()]
    blocks = []
    while lines:
        count = int(lines.pop(0)[0])
        blocks.append([(float(x), float(y)) for x, y in lines[:count]])
        del lines[:count]
    return blocks


def artifact(result, suffix):
    return Path(next(a["path"] for a in result["artifacts"] if a["path"].endswith(suffix)))


def check_png_matches_csv(result, expected_curves):
    assert result["status"] == "succeeded", result
    assert result["data"]["visible_gui"] is False and result["route"] == "batch"
    table = artifact(result, "curves.csv")
    with table.open(newline="") as stream:
        rows = [(int(r["curve"]), float(r["x"]), float(r["y"])) for r in csv.DictReader(stream)]
    native = native_blocks(artifact(result, "native.xy"))
    assert len(native) == len(expected_curves) == result["data"]["curve_count"]
    for number, (expected, readback) in enumerate(zip(expected_curves, native), 1):
        exported = np.array([(x, y) for curve, x, y in rows if curve == number])
        storage = np.asarray(expected, dtype=float).astype(np.float32).astype(float)
        assert np.array_equal(exported, storage)
        assert np.allclose(np.asarray(readback), exported, rtol=5e-11, atol=0)
    png = artifact(result, "plot.png")
    consistency = result["data"]["png_csv_consistency"]
    assert consistency["png_sha256"] == hashlib.sha256(png.read_bytes()).hexdigest()
    assert consistency["csv_sha256"] == hashlib.sha256(table.read_bytes()).hexdigest()
    with Image.open(png) as image:
        colors = image.convert("RGB").getcolors(1 << 20)
    assert colors and len(colors) > len(expected_curves)
    return png


def test_three_load_cases_force_displacement_batch_png_and_csv(xyplot_case):
    service, inputs = xyplot_case
    cases = {
        "Case A": [(0.0, 0.0), (0.5, 6.25), (1.0, 11.0), (2.0, 17.5), (3.0, 20.0)],
        "Case B": [(0.0, 0.0), (0.75, 8.0), (2.25, 15.5), (3.5, 16.0)],
        "Case C": [(0.0, 0.0), (1.0, 9.0), (2.0, 14.0), (1.0, 7.5), (0.0, 1.5), (1.5, 10.0)],
    }
    curves = [spec(write_curve(inputs, label.replace(" ", "_"), rows), label) for label, rows in cases.items()]
    result = service.render_xyplot(curves, "Three load cases", "Displacement", "Force", "mm", "kN",
                                   x_range=[0, 4], y_range=[0, 25], legend_title="Load case")
    check_png_matches_csv(result, list(cases.values()))
    assert [c["label"] for c in result["data"]["curves"]] == list(cases)


def test_ten_curves_log_axes_and_ranges_change_the_native_png(xyplot_case):
    service, inputs = xyplot_case
    rows = [[(x, (k + 1) * x ** 1.5) for x in (0.2, 0.5, 1.0, 2.0, 5.0, 8.0)[: 3 + k % 4]] for k in range(10)]
    curves = [spec(write_curve(inputs, f"c{k}", r), f"C{k + 1}") for k, r in enumerate(rows)]
    common = ("Ten curves", "Displacement", "Force", "mm", "kN")
    linear = check_png_matches_csv(service.render_xyplot(curves, *common), rows)
    loglog = check_png_matches_csv(service.render_xyplot(curves, *common, x_log=True, y_log=True), rows)
    ranged = service.render_xyplot(curves, *common, x_log=True, y_log=True, x_range=[0.1, 10], y_range=[0.1, 1000])
    ranged_png = check_png_matches_csv(ranged, rows)
    assert ranged["data"]["axes"]["native_axes_token"] == "Log-Log"
    with Image.open(linear) as a, Image.open(loglog) as b, Image.open(ranged_png) as c:
        assert ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is not None
        assert ImageChops.difference(b.convert("RGB"), c.convert("RGB")).getbbox() is not None


def test_single_curve_and_semilog_axes(xyplot_case):
    service, inputs = xyplot_case
    rows = [(0.0, 1.0), (1.0, 10.0), (2.0, 100.0), (3.0, 1000.0)]
    path = write_curve(inputs, "growth", rows)
    for kwargs in (dict(y_log=True, legend=False), dict(x_range=[0.5, 2.5])):
        check_png_matches_csv(service.render_xyplot([spec(path, "Growth")], "Growth", "Time", "Force", "mm", "kN",
                                                    **kwargs), [rows])
