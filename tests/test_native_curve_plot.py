import numpy as np
import pytest

from ls_prepost_mcp.gui_curves import native_plot_values, plot_text, read_xy_csv, verify_xy_readback


def test_hysteresis_csv_preserves_backtracking_and_column_choice(tmp_path):
    source = tmp_path / "loop.csv"
    source.write_text("time,u,F\n0,0,0\n1,2,3\n2,1,1\n3,0,0\n")
    values = read_xy_csv(source, "u", "F")
    assert values.tolist() == [[0, 0], [2, 3], [1, 1], [0, 0]]
    native = tmp_path / "native.xy"
    native.write_text("4\n0 0\n2 3\n1 1\n0 0\n")
    assert verify_xy_readback(native, values)["row_order_preserved"]
    with pytest.raises(ValueError, match="values"):
        verify_xy_readback(native, values[[0, 3, 2, 1]])


def test_native_single_precision_is_explicit_and_not_a_broad_comparison_tolerance(tmp_path):
    path = tmp_path / "native.xy"
    path.write_text("2\n0 0\n1.0000000149e-01 1\n")
    report = verify_xy_readback(path, np.array([[0.0, 0.0], [0.1, 1.0]]))
    assert report["native_storage_dtype"] == "float32"
    assert report["maximum_absolute_difference"] > 0
    path.write_text("2\n0 0\n1.00000004e-01 1\n")
    with pytest.raises(ValueError):
        verify_xy_readback(path, np.array([[0.0, 0.0], [0.1, 1.0]]))
    for value in (1e100, 1e-100, 1e-45):
        with pytest.raises(ValueError, match="float32|quantization"):
            native_plot_values(np.array([[0.0, 0.0], [value, 1.0]]))


@pytest.mark.parametrize(
    "text", ["x,x\n0,1\n1,2\n", "x,y\n0,nan\n1,2\n", "x,y\n0,1\n", "x,y\n0,1,extra\n1,2\n", "x,y\n0\n1,2\n"]
)
def test_ambiguous_nonfinite_or_incomplete_csv_is_rejected(tmp_path, text):
    source = tmp_path / "invalid.csv"
    source.write_text(text)
    with pytest.raises(ValueError):
        read_xy_csv(source, "x", "y")


@pytest.mark.parametrize(
    "text", ["3\n0 0\n1 1\n", "2\n0 0\n1 1\n2\n0 0\n1 1\n", "2\n0 0\n1 nan\n", "2\n0 0\n1 2\n"]
)
def test_native_readback_rejects_truncation_extra_curves_and_wrong_values(tmp_path, text):
    path = tmp_path / "native.xy"
    path.write_text(text)
    with pytest.raises(ValueError):
        verify_xy_readback(path, np.array([[0.0, 0.0], [1.0, 1.0]]))


@pytest.mark.parametrize("text", ['x"\nexit', "x\\y", "", "应力", "a" * 81])
def test_unvalidated_label_encoding_and_command_delimiters_are_rejected(text):
    with pytest.raises(ValueError):
        plot_text(text, "title", 80)


def test_multicurve_roundtrip_preserves_unequal_lengths_grids_and_order(tmp_path):
    from ls_prepost_mcp.gui_curves import verify_curve_readback

    curves = [np.array([[0.0, 0.0], [2.0, 3.0], [1.0, 1.0]]), np.array([[0.0, 2.0], [4.0, 6.0]])]
    path = tmp_path / "both.xy"
    path.write_text("3\n0 0\n2 3\n1 1\n2\n0 2\n4 6\n")
    report = verify_curve_readback(path, curves)
    assert [c["sample_count"] for c in report] == [3, 2]
    assert all(c["row_order_preserved"] for c in report)
    with pytest.raises(ValueError, match="count"):
        verify_curve_readback(path, curves[::-1])
    with pytest.raises(ValueError, match="count"):
        verify_curve_readback(path, curves[:1])
    path.write_text("3\n0 0\n2 3\n1 1\n2\n0 2\n")
    with pytest.raises(ValueError, match="count"):
        verify_curve_readback(path, curves)


@pytest.mark.parametrize("bad", ["unit", "label", "missing", "extra", "first_label", "number"])
def test_overlay_contract_rejects_ambiguous_sources_before_native_work(tmp_path, bad):
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.gui_curves import curve_sources
    from ls_prepost_mcp.service import Service

    path = tmp_path / "curve.csv"
    path.write_text("x,y\n0,0\n1,1\n")
    spec = dict(path=str(path), x_column="x", y_column="y", label="Second", x_unit="s", y_unit="N")
    label = "First"
    if bad == "unit":
        spec["y_unit"] = "kN"
    if bad == "label":
        spec["label"] = "First"
    if bad == "missing":
        del spec["x_column"]
    if bad == "extra":
        spec["guess_units"] = True
    if bad == "first_label":
        label = None
    with pytest.raises(ValueError):
        curve_sources(
            Service(Settings(tmp_path)),
            str(path),
            "x",
            "y",
            "s",
            "N",
            label,
            [spec] * (10 if bad == "number" else 1),
        )


def test_single_curve_column_names_remain_independent_of_optional_legend(tmp_path):
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.gui_curves import curve_sources
    from ls_prepost_mcp.service import Service

    path = tmp_path / "curve.csv"
    path.write_text("位移,载荷\n0,0\n1,1\n", encoding="utf8")
    curves = curve_sources(Service(Settings(tmp_path)), str(path), "位移", "载荷", "mm", "N", None, None)
    assert curves[0]["spec"]["y_column"] == "载荷"


def test_legacy_session_commands_are_unchanged_without_axis_options():
    from ls_prepost_mcp.gui_curves import presentation_commands

    assert presentation_commands("xyplot 3 ", "T", "u", "F", "mm", "N", ["A", "B"], True) == [
        'xyplot 3 title "T"', 'xyplot 3 xtitle "u (mm)"', 'xyplot 3 ytitle "F (N)"', "xyplot 3 legend on",
        'xyplot 3 curvelegend 1/1 "A"', 'xyplot 3 curvelegend 2/1 "B"']
    assert presentation_commands("xyplot 1 ", "T", "u", "F", "mm", "N", ["Curve 1"], False)[-1] == "xyplot 1 legend off"


@pytest.mark.parametrize("x_log,y_log,token", [(True, False, "Lin-Log"), (False, True, "Log-Lin"), (True, True, "Log-Log")])
def test_native_axes_token_is_y_scale_then_x_scale_and_precedes_limits(x_log, y_log, token):
    from ls_prepost_mcp.gui_curves import axis_options, presentation_commands

    options = axis_options([0.1, 10], [1, 1000], x_log, y_log)
    commands = presentation_commands("xyplot 1 ", "T", "u", "F", "mm", "N", ["A"], True, "Cases", options)
    assert commands[-6:] == ['xyplot 1 legendlabel "Cases"', "xyplot 1 axes " + token, "xyplot 1 xmin 0.10000000000000001",
                             "xyplot 1 xmax 10", "xyplot 1 ymin 1", "xyplot 1 ymax 1000"]
    linear = presentation_commands("xyplot 1 ", "T", "u", "F", "mm", "N", ["A"], True, None, axis_options(y_range=[-2, 3]))
    assert not any(" axes " in c for c in linear) and linear[-2:] == ["xyplot 1 ymin -2", "xyplot 1 ymax 3"]


@pytest.mark.parametrize("kwargs", [
    dict(x_range=[1, 1]), dict(x_range=[2, 1]), dict(y_range=[0, float("inf")]), dict(x_range=[1]),
    dict(x_range=["0", 1]), dict(x_range=[0, 1], x_log=True), dict(y_range=[-1, 1], y_log=True), dict(x_log=1)])
def test_invalid_axis_options_are_rejected(kwargs):
    from ls_prepost_mcp.gui_curves import axis_options

    with pytest.raises(ValueError):
        axis_options(**kwargs)


def xyplot_service(tmp_path, monkeypatch, native_writer=None):
    from PIL import Image

    from ls_prepost_mcp import gui_curves
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.core.contracts import JobResult
    from ls_prepost_mcp.service import Service

    executable = tmp_path / "lsprepost4.13.exe"
    executable.write_bytes(b"placeholder")
    monkeypatch.setattr(Settings, "native_executable", lambda self: executable)
    calls = []

    def fake_run_batch(exe, cfile, directory, *, timeout, graphics, operation, launch_mode="c"):
        calls.append(dict(cfile=cfile.read_text(encoding="utf-8"), graphics=graphics, operation=operation))
        blocks, lines = [], (directory / "curves.txt").read_text().splitlines()
        while lines:
            count = int(lines.pop(0))
            blocks.append([tuple(float(v) for v in lines.pop(0).split(",")) for _ in range(count)])
        text = (native_writer or native_text)(blocks)
        (directory / "native.xy").write_text(text)
        image = Image.new("RGB", (64, 48), "white")
        image.putpixel((3, 3), (255, 0, 0))
        image.save(directory / "plot.png")
        return JobResult(operation=operation, job_id=directory.name, status="unverified", backend="lsprepost", data={})

    monkeypatch.setattr(gui_curves, "run_batch", fake_run_batch)
    return Service(Settings(tmp_path / "jobs", None, (tmp_path,))), calls


def native_text(blocks):
    return "".join(f"{len(b):10d}\n" + "".join(f"{float(np.float32(x)):20.10e}{float(np.float32(y)):20.10e}\n"
                                              for x, y in b) for b in blocks)


def three_cases(tmp_path):
    rows = {"A": "0,0\n1,10\n2,18\n3,22\n", "B": "0,0\n1.5,12\n3,19\n", "C": "0,0\n1,8\n2,13\n1,9\n0,2\n"}
    curves = []
    for label, body in rows.items():
        path = tmp_path / f"case_{label}.csv"
        path.write_text("time,disp,force\n" + "".join(f"{i},{line}\n" for i, line in enumerate(body.splitlines())))
        curves.append(dict(path=str(path), x_column="disp", y_column="force", label="Case " + label,
                           x_unit="mm", y_unit="kN"))
    return curves


def test_render_xyplot_batch_exports_png_and_matching_csv_without_visible_gui(tmp_path, monkeypatch):
    import csv

    service, calls = xyplot_service(tmp_path, monkeypatch)
    curves = three_cases(tmp_path)
    result = service.render_xyplot(curves, "Three load cases", "Displacement", "Force", "mm", "kN",
                                   x_range=[0, 4], y_range=[0, 25], legend_title="Cases")
    assert result["status"] == "succeeded", result
    assert calls[0]["graphics"] is False and calls[0]["operation"] == "render_xyplot"
    cfile = calls[0]["cfile"].splitlines()
    assert cfile[:3] == ['open xydata "curves.txt"', "newplot", 'show "curves.txt" 0']
    assert 'xyplot 1 curvelegend 3/1 "Case C"' in cfile and "xyplot 1 xmax 4" in cfile and cfile[-1] == "exit"
    assert cfile[-3] == 'print png "plot.png" nogamma enlisted "PlotWindow-1"'
    data = result["data"]
    assert data["visible_gui"] is False and data["curve_count"] == 3
    assert [c["numeric_verification"]["sample_count"] for c in data["curves"]] == [4, 3, 5]
    assert data["axes"]["requested_x_range"] == [0.0, 4.0] and data["axes"]["x_scale"] == "linear"
    table = next(a for a in result["artifacts"] if a["path"].endswith("curves.csv"))
    with open(table["path"], newline="") as stream:
        rows = [(int(r["curve"]), float(r["x"]), float(r["y"])) for r in csv.DictReader(stream)]
    hysteresis = [(x, y) for curve, x, y in rows if curve == 3]
    assert hysteresis == [(0, 0), (1, 8), (2, 13), (1, 9), (0, 2)]
    assert data["png_csv_consistency"]["csv_sha256"] == table["sha256"]
    assert {a["kind"] for a in result["artifacts"]} >= {"png", "csv", "text"}


def test_render_xyplot_single_curve_uses_first_curve_reference(tmp_path, monkeypatch):
    service, calls = xyplot_service(tmp_path, monkeypatch)
    result = service.render_xyplot(three_cases(tmp_path)[1:2], "One", "u", "F", "mm", "kN", legend=False)
    assert result["status"] == "succeeded", result
    assert 'show "curves.txt~1" 0' in calls[0]["cfile"] and "xyplot 1 legend off" in calls[0]["cfile"]


def test_native_readback_mismatch_fails_the_batch_job(tmp_path, monkeypatch):
    service, _ = xyplot_service(tmp_path, monkeypatch, native_writer=lambda blocks: native_text(blocks[::-1]))
    result = service.render_xyplot(three_cases(tmp_path), "T", "u", "F", "mm", "kN")
    assert result["status"] == "failed" and "count" in result["error"]["message"]
    assert not any(a["path"].endswith("curves.csv") for a in result["artifacts"])


@pytest.mark.parametrize("bad", ["eleven", "unit", "keys", "log_zero", "log_range", "label", "empty"])
def test_render_xyplot_rejects_ambiguous_requests_before_native_work(tmp_path, monkeypatch, bad):
    service, calls = xyplot_service(tmp_path, monkeypatch)
    curves = three_cases(tmp_path)
    kwargs = {}
    if bad == "eleven":
        curves = [dict(c, label=f"C{i}") for i, c in enumerate((curves * 4)[:11])]
    if bad == "unit":
        curves[1]["y_unit"] = "N"
    if bad == "keys":
        curves[0]["guess_units"] = True
    if bad == "log_zero":
        kwargs = dict(x_log=True)
    if bad == "log_range":
        kwargs = dict(y_log=True, y_range=[0, 10])
    if bad == "label":
        curves[2]["label"] = curves[0]["label"]
    if bad == "empty":
        curves = []
    with pytest.raises(ValueError):
        service.render_xyplot(curves, "T", "u", "F", "mm", "kN", **kwargs)
    jobs = tmp_path / "jobs"
    assert calls == [] and (not jobs.exists() or not any(jobs.iterdir()))


def test_ten_curves_are_the_bound(tmp_path, monkeypatch):
    service, calls = xyplot_service(tmp_path, monkeypatch)
    base = three_cases(tmp_path)[0]
    result = service.render_xyplot([dict(base, label=f"C{i}") for i in range(10)], "T", "u", "F", "mm", "kN")
    assert result["status"] == "succeeded" and result["data"]["curve_count"] == 10
    assert 'xyplot 1 curvelegend 10/1 "C9"' in calls[0]["cfile"]
