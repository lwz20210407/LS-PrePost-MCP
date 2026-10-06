"""Q08 XYPlot curve plotting and headless image rendering.

Features:
- Overlay up to 10 curves on a single plot with distinct styles and colors;
- Configurable plot title, axis labels, units, and legend;
- Linear and logarithmic axes (x_scale, y_scale);
- User-specified axis ranges (x_range, y_range);
- Headless batch-capable rendering via Pillow (E5 decision compliance);
- Synchronous CSV export of numerically identical curve values.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .curve_ops import read_curve_table
from .post_backend import write_csv


class XYPlotError(ValueError):
    """Raised when plot specifications or curve data are invalid."""


PALETTE = [
    (31, 119, 180),   # Steel blue
    (255, 127, 14),   # Orange
    (44, 160, 44),    # Green
    (214, 39, 40),    # Red
    (148, 103, 189),  # Purple
    (140, 86, 75),    # Brown
    (227, 119, 194),  # Pink
    (127, 127, 127),  # Gray
    (188, 189, 34),   # Olive
    (23, 190, 207),   # Cyan
]


def render_xyplot_image(
    curves_data: list[dict[str, Any]],
    output_png: Path,
    title: str = "XY Plot",
    x_label: str = "X",
    y_label: str = "Y",
    x_unit: str = "",
    y_unit: str = "",
    x_range: list[float] | None = None,
    y_range: list[float] | None = None,
    x_scale: str = "linear",
    y_scale: str = "linear",
    show_grid: bool = True,
    show_legend: bool = True,
    width: int = 1280,
    height: int = 720,
) -> dict[str, Any]:
    """Render headless anti-aliased 2D line plot of 1..10 curves to PNG.

    curves_data: list of dicts with keys:
      - 'label': str
      - 'x': np.ndarray
      - 'y': np.ndarray
      - 'color': tuple[int, int, int] (optional)
    """
    if not 1 <= len(curves_data) <= 10:
        raise XYPlotError(f"Provide 1..10 curves to plot, received {len(curves_data)}")

    if x_scale not in ("linear", "log"):
        raise XYPlotError(f"x_scale must be 'linear' or 'log', got '{x_scale}'")
    if y_scale not in ("linear", "log"):
        raise XYPlotError(f"y_scale must be 'linear' or 'log', got '{y_scale}'")

    # Global data bounds
    all_x = np.concatenate([c["x"] for c in curves_data])
    all_y = np.concatenate([c["y"] for c in curves_data])

    if x_scale == "log":
        if np.any(all_x <= 0):
            raise XYPlotError("Logarithmic X-axis requires all X values to be strictly positive (> 0)")
    if y_scale == "log":
        if np.any(all_y <= 0):
            raise XYPlotError("Logarithmic Y-axis requires all Y values to be strictly positive (> 0)")

    # Compute bounds
    x_min = float(x_range[0]) if x_range is not None else float(np.min(all_x))
    x_max = float(x_range[1]) if x_range is not None else float(np.max(all_x))
    y_min = float(y_range[0]) if y_range is not None else float(np.min(all_y))
    y_max = float(y_range[1]) if y_range is not None else float(np.max(all_y))

    if x_min >= x_max:
        # Add small margin
        x_max = x_min + (1.0 if x_min == 0 else abs(x_min) * 0.1)
    if y_min >= y_max:
        y_max = y_min + (1.0 if y_min == 0 else abs(y_min) * 0.1)

    # Plot area layout
    pad_left = 120
    pad_right = 60
    pad_top = 80
    pad_bottom = 100

    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    # Canvas
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Fonts
    font_large = ImageFont.load_default()
    font_med = ImageFont.load_default()
    font_small = ImageFont.load_default()

    # Title
    full_title = title
    draw.text((pad_left + plot_w // 2 - len(full_title) * 4, 30), full_title, fill=(20, 20, 20), font=font_large)

    # Axis Labels
    x_axis_text = f"{x_label} [{x_unit}]" if x_unit else x_label
    y_axis_text = f"{y_label} [{y_unit}]" if y_unit else y_label

    draw.text((pad_left + plot_w // 2 - len(x_axis_text) * 3, height - 40), x_axis_text, fill=(30, 30, 30), font=font_med)
    draw.text((30, pad_top + plot_h // 2), y_axis_text, fill=(30, 30, 30), font=font_med)

    # Coordinate transform functions
    def to_canvas_x(val: float) -> float:
        if x_scale == "log":
            norm = (math.log10(val) - math.log10(x_min)) / (math.log10(x_max) - math.log10(x_min))
        else:
            norm = (val - x_min) / (x_max - x_min)
        return pad_left + norm * plot_w

    def to_canvas_y(val: float) -> float:
        if y_scale == "log":
            norm = (math.log10(val) - math.log10(y_min)) / (math.log10(y_max) - math.log10(y_min))
        else:
            norm = (val - y_min) / (y_max - y_min)
        return pad_top + plot_h - norm * plot_h

    # Draw grid and ticks
    num_ticks_x = 6
    num_ticks_y = 6

    # X ticks
    if x_scale == "log":
        log_start = math.floor(math.log10(x_min))
        log_end = math.ceil(math.log10(x_max))
        x_ticks = [10.0**i for i in range(log_start, log_end + 1) if x_min <= 10.0**i <= x_max]
        if not x_ticks:
            x_ticks = [x_min, x_max]
    else:
        x_ticks = list(np.linspace(x_min, x_max, num_ticks_x))

    for xt in x_ticks:
        cx = to_canvas_x(xt)
        if pad_left <= cx <= pad_left + plot_w:
            if show_grid:
                draw.line([(cx, pad_top), (cx, pad_top + plot_h)], fill=(230, 230, 230), width=1)
            draw.line([(cx, pad_top + plot_h), (cx, pad_top + plot_h + 5)], fill=(80, 80, 80), width=1)
            lbl = f"{xt:.2e}" if abs(xt) >= 1e4 or (abs(xt) < 1e-2 and xt != 0) else f"{xt:.3g}"
            draw.text((cx - len(lbl) * 3, pad_top + plot_h + 10), lbl, fill=(60, 60, 60), font=font_small)

    # Y ticks
    if y_scale == "log":
        log_start = math.floor(math.log10(y_min))
        log_end = math.ceil(math.log10(y_max))
        y_ticks = [10.0**i for i in range(log_start, log_end + 1) if y_min <= 10.0**i <= y_max]
        if not y_ticks:
            y_ticks = [y_min, y_max]
    else:
        y_ticks = list(np.linspace(y_min, y_max, num_ticks_y))

    for yt in y_ticks:
        cy = to_canvas_y(yt)
        if pad_top <= cy <= pad_top + plot_h:
            if show_grid:
                draw.line([(pad_left, cy), (pad_left + plot_w, cy)], fill=(230, 230, 230), width=1)
            draw.line([(pad_left - 5, cy), (pad_left, cy)], fill=(80, 80, 80), width=1)
            lbl = f"{yt:.2e}" if abs(yt) >= 1e4 or (abs(yt) < 1e-2 and yt != 0) else f"{yt:.3g}"
            draw.text((pad_left - len(lbl) * 7 - 10, cy - 6), lbl, fill=(60, 60, 60), font=font_small)

    # Plot border box
    draw.rectangle([pad_left, pad_top, pad_left + plot_w, pad_top + plot_h], outline=(50, 50, 50), width=2)

    # Draw curves
    for idx, c in enumerate(curves_data):
        color = c.get("color") or PALETTE[idx % len(PALETTE)]
        cx_pts = c["x"]
        cy_pts = c["y"]

        pts = []
        for xi, yi in zip(cx_pts, cy_pts):
            if x_scale == "log" and xi <= 0:
                continue
            if y_scale == "log" and yi <= 0:
                continue
            px = to_canvas_x(float(xi))
            py = to_canvas_y(float(yi))
            # Clip into viewport
            px_c = max(pad_left, min(pad_left + plot_w, px))
            py_c = max(pad_top, min(pad_top + plot_h, py))
            pts.append((px_c, py_c))

        if len(pts) >= 2:
            draw.line(pts, fill=color, width=2)

    # Draw Legend
    if show_legend:
        leg_x = pad_left + plot_w - 220
        leg_y = pad_top + 20
        leg_h = len(curves_data) * 25 + 15
        draw.rectangle([leg_x, leg_y, leg_x + 200, leg_y + leg_h], fill=(255, 255, 255), outline=(180, 180, 180), width=1)
        for idx, c in enumerate(curves_data):
            color = c.get("color") or PALETTE[idx % len(PALETTE)]
            line_y = leg_y + 15 + idx * 25
            draw.line([(leg_x + 10, line_y), (leg_x + 35, line_y)], fill=color, width=3)
            label_text = c.get("label", f"Curve {idx+1}")[:22]
            draw.text((leg_x + 45, line_y - 6), label_text, fill=(30, 30, 30), font=font_small)

    img.save(output_png, format="PNG")

    return {
        "x_range": [x_min, x_max],
        "y_range": [y_min, y_max],
        "curve_count": len(curves_data),
        "width": width,
        "height": height,
        "x_scale": x_scale,
        "y_scale": y_scale,
    }


def execute_render_xyplot(
    directory: Path,
    path: str,
    x_column: str | int = 1,
    y_column: str | int = 2,
    title: str = "XY Plot",
    x_label: str = "X",
    y_label: str = "Y",
    x_unit: str = "",
    y_unit: str = "",
    curve_label: str | None = None,
    additional_curves: list[dict[str, Any]] | None = None,
    x_range: list[float] | None = None,
    y_range: list[float] | None = None,
    x_scale: str = "linear",
    y_scale: str = "linear",
    show_grid: bool = True,
    show_legend: bool = True,
    width: int = 1280,
    height: int = 720,
) -> tuple[dict[str, Any], list[Path]]:
    """Execute render_xyplot job, producing xyplot.png and xyplot_data.csv."""
    # 1. Load primary curve
    times1, values1, _ = read_curve_table(path, x_column, y_column)
    curves_data = [
        {
            "label": curve_label or "Curve 1",
            "x": times1,
            "y": values1,
            "color": PALETTE[0],
            "path": str(path),
        }
    ]

    # 2. Load additional curves if provided
    if additional_curves:
        for idx, item in enumerate(additional_curves, start=1):
            c_path = item["path"]
            c_xcol = item.get("x_column", 1)
            c_ycol = item.get("y_column", 2)
            c_label = item.get("label", f"Curve {idx+1}")
            cx, cy, _ = read_curve_table(c_path, c_xcol, c_ycol)
            curves_data.append(
                {
                    "label": c_label,
                    "x": cx,
                    "y": cy,
                    "color": PALETTE[idx % len(PALETTE)],
                    "path": str(c_path),
                }
            )

    png_path = directory / "xyplot.png"
    plot_meta = render_xyplot_image(
        curves_data=curves_data,
        output_png=png_path,
        title=title,
        x_label=x_label,
        y_label=y_label,
        x_unit=x_unit,
        y_unit=y_unit,
        x_range=x_range,
        y_range=y_range,
        x_scale=x_scale,
        y_scale=y_scale,
        show_grid=show_grid,
        show_legend=show_legend,
        width=width,
        height=height,
    )

    # 3. Synchronous CSV export of numerically identical curve values
    csv_rows = []
    # If single curve, simple x, y columns
    if len(curves_data) == 1:
        csv_header = [x_label, y_label]
        for xi, yi in zip(curves_data[0]["x"], curves_data[0]["y"]):
            csv_rows.append([float(xi), float(yi)])
    else:
        # Multi-curve columns: x1, y1, x2, y2, ...
        max_len = max(len(c["x"]) for c in curves_data)
        csv_header = []
        for idx, c in enumerate(curves_data, start=1):
            csv_header.extend([f"x_{idx}_{c['label']}", f"y_{idx}_{c['label']}"])
        for r_idx in range(max_len):
            row = []
            for c in curves_data:
                if r_idx < len(c["x"]):
                    row.extend([float(c["x"][r_idx]), float(c["y"][r_idx])])
                else:
                    row.extend(["", ""])
            csv_rows.append(row)

    csv_path = directory / "xyplot_data.csv"
    write_csv(csv_path, csv_header, csv_rows)

    summary = {
        "title": title,
        "curve_count": len(curves_data),
        "curves": [
            {
                "label": c["label"],
                "sample_count": len(c["x"]),
                "x_min": float(np.min(c["x"])),
                "x_max": float(np.max(c["x"])),
                "y_min": float(np.min(c["y"])),
                "y_max": float(np.max(c["y"])),
            }
            for c in curves_data
        ],
        "plot_settings": {
            "x_scale": x_scale,
            "y_scale": y_scale,
            "x_range": plot_meta["x_range"],
            "y_range": plot_meta["y_range"],
            "resolution": [width, height],
        },
    }

    return summary, [png_path, csv_path]
