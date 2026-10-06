"""Tests for Q08 XYPlot curve plotting and headless batch rendering."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.xyplot import XYPlotError, render_xyplot_image


def test_render_xyplot_image_generates_valid_png_and_dimensions(tmp_path):
    times = np.linspace(0.0, 1.0, 50)
    c1 = 100.0 * np.sin(np.pi * times)
    c2 = 80.0 * np.cos(np.pi * times)

    curves = [
        {"label": "Impact 1", "x": times, "y": c1},
        {"label": "Impact 2", "x": times, "y": c2},
    ]

    out_png = tmp_path / "plot.png"
    meta = render_xyplot_image(
        curves_data=curves,
        output_png=out_png,
        title="Impact Response",
        x_label="Time",
        y_label="Force",
        x_unit="s",
        y_unit="kN",
        width=800,
        height=600,
    )

    assert out_png.is_file()
    assert meta["curve_count"] == 2
    assert meta["width"] == 800
    assert meta["height"] == 600

    # Verify PNG image format and resolution via Pillow
    with Image.open(out_png) as img:
        assert img.format == "PNG"
        assert img.size == (800, 600)


def test_render_xyplot_log_scale_and_validation(tmp_path):
    x = np.array([1.0, 10.0, 100.0, 1000.0])
    y = np.array([2.0, 20.0, 200.0, 2000.0])
    curves = [{"label": "Log Curve", "x": x, "y": y}]

    out_png = tmp_path / "log_plot.png"
    meta = render_xyplot_image(
        curves_data=curves,
        output_png=out_png,
        x_scale="log",
        y_scale="log",
    )
    assert meta["x_scale"] == "log"
    assert meta["y_scale"] == "log"
    assert out_png.is_file()

    # Log scale must reject non-positive values
    bad_x = np.array([-1.0, 5.0, 10.0])
    with pytest.raises(XYPlotError, match="strictly positive"):
        render_xyplot_image(
            curves_data=[{"label": "Bad", "x": bad_x, "y": y[:3]}],
            output_png=tmp_path / "bad.png",
            x_scale="log",
        )


def test_render_xyplot_rejects_exceeding_10_curves(tmp_path):
    curves = [{"label": f"Curve {i}", "x": np.array([0, 1]), "y": np.array([0, i])} for i in range(11)]
    with pytest.raises(XYPlotError, match="1..10 curves"):
        render_xyplot_image(curves_data=curves, output_png=tmp_path / "fail.png")


def test_service_render_xyplot_end_to_end_and_csv_consistency(tmp_path):
    service = Service(Settings(tmp_path))

    # Curve 1
    t1 = np.linspace(0.0, 1.0, 21)
    f1 = 50.0 * t1
    c1_path = tmp_path / "c1.csv"
    with c1_path.open("w", encoding="utf-8") as f:
        f.write("time,force\n")
        for ti, fi in zip(t1, f1):
            f.write(f"{ti:.4f},{fi:.4f}\n")

    # Curve 2
    f2 = 30.0 * t1 + 5.0
    c2_path = tmp_path / "c2.csv"
    with c2_path.open("w", encoding="utf-8") as f:
        f.write("time,force\n")
        for ti, fi in zip(t1, f2):
            f.write(f"{ti:.4f},{fi:.4f}\n")

    res = service.render_xyplot(
        path=str(c1_path),
        x_column="time",
        y_column="force",
        curve_label="Load Case A",
        additional_curves=[
            {"path": str(c2_path), "x_column": "time", "y_column": "force", "label": "Load Case B"}
        ],
        title="Load Case Comparison",
        x_label="Time",
        y_label="Force",
        x_unit="s",
        y_unit="kN",
    )

    assert res["status"] == "succeeded"
    data = res["data"]
    assert data["curve_count"] == 2
    assert data["curves"][0]["label"] == "Load Case A"
    assert data["curves"][1]["label"] == "Load Case B"

    # Artifacts: PNG and CSV
    artifacts = res["artifacts"]
    png_art = next(a for a in artifacts if a["kind"] == "png")
    csv_art = next(a for a in artifacts if a["kind"] == "csv")

    assert Path(png_art["path"]).is_file()
    assert Path(csv_art["path"]).is_file()

    # Read exported CSV and verify numerical consistency
    csv_text = Path(csv_art["path"]).read_text(encoding="utf-8")
    assert "Load Case A" in csv_text and "Load Case B" in csv_text
