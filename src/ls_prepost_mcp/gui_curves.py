"""CSV-to-native-XYPlot rendering with numeric round-trip verification."""

import csv
import re

import numpy as np

from .config import command_path
from .jobs import atomic_json, check_artifact, fingerprint, now
from .post_backend import write_csv
from .programs import native_errors
from .windows_transport import WindowsCommandTransport


def plot_text(value, name, maximum):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(ord(c) < 32 or ord(c) > 126 or c in '\\"' for c in value)
    ):
        raise ValueError(
            f"{name} requires 1..{maximum} printable ASCII characters without quotes/backslashes"
        )
    return value


def read_xy_csv(path, x_column, y_column):
    if (
        not isinstance(x_column, str)
        or not isinstance(y_column, str)
        or not x_column
        or not y_column
        or x_column == y_column
    ):
        raise ValueError("Choose two distinct named numeric CSV columns")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("CSV requires unique named columns")
        if x_column not in reader.fieldnames or y_column not in reader.fieldnames:
            raise ValueError("Selected plot column is absent")
        rows = []
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError("Malformed CSV row")
            rows.append([float(row[x_column]), float(row[y_column])])
            if len(rows) > 100000:
                raise ValueError("A curve plot is bounded to 100000 samples")
    values = np.asarray(rows, dtype=float)
    if len(values) < 2 or not np.isfinite(values).all():
        raise ValueError("Curve plot requires at least two finite XY samples")
    # Hysteresis/backtracking is valid: preserve row order, never sort by X.
    return values


def native_plot_values(expected):
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        native = expected.astype(np.float32).astype(float)
    if not np.isfinite(native).all() or np.any((expected != 0) & (native == 0)):
        raise ValueError("Native XYPlot float32 storage would overflow or erase nonzero samples")
    relative = np.zeros_like(expected)
    np.divide(np.abs(native - expected), np.abs(expected), out=relative, where=expected != 0)
    if np.any(relative > np.finfo(np.float32).eps):
        raise ValueError("Native XYPlot subnormal quantization would exceed float32 relative precision")
    return native


def verify_xy_readback(path, expected):
    lines = [line.strip() for line in path.read_text(encoding="utf8").splitlines() if line.strip()]
    if (
        not lines
        or not re.fullmatch(r"\d+", lines[0])
        or int(lines[0]) != len(expected)
        or len(lines) != len(expected) + 1
    ):
        raise ValueError("Native XY round-trip sample/curve count mismatch")
    values = np.asarray(
        [[float(x.replace("D", "E")) for x in line.split()] for line in lines[1:]], dtype=float
    )
    quantized = native_plot_values(expected)
    if (
        values.shape != expected.shape
        or not np.isfinite(values).all()
        or not np.allclose(values, quantized, rtol=5e-11, atol=0)
    ):
        raise ValueError("Native plotted XY values do not match the requested columns/order")
    return dict(
        sample_count=len(values),
        native_storage_dtype="float32",
        relative_tolerance_to_native_storage=5e-11,
        absolute_tolerance=0,
        maximum_absolute_difference=float(np.max(np.abs(values - expected))),
        row_order_preserved=True,
    )


def plot_windows(transport):
    return {
        int(match[1])
        for row in transport.inspect_controls()
        if row["parent"] == 0
        and row["class_name"] == "wxWindowNR"
        and (match := re.fullmatch(r"PlotWindow-(\d+)", row["text"]))
    }


def export_curve_plot(service, session_id, path, x_column, y_column, title, x_label, y_label, x_unit, y_unit):
    for name, value, maximum in [
        ("title", title, 80),
        ("x_label", x_label, 30),
        ("y_label", y_label, 30),
        ("x_unit", x_unit, 12),
        ("y_unit", y_unit, 12),
    ]:
        plot_text(value, name, maximum)
    source = service.settings.input_path(path)
    identity = fingerprint(source)
    values = read_xy_csv(source, x_column, y_column)
    quantized = native_plot_values(values)
    parameters = dict(
        path=path,
        x_column=x_column,
        y_column=y_column,
        title=title,
        x_label=x_label,
        y_label=y_label,
        x_unit=x_unit,
        y_unit=y_unit,
    )
    manager = service._session_manager()
    with manager.lock(session_id):
        meta = service._visible_mesh_session(session_id, manager, allow_results=True)
        transport = WindowsCommandTransport(meta["process"]["pid"])
        old_windows = plot_windows(transport)
        if len(old_windows) >= 32:
            raise ValueError("Close unused native plot windows before creating more than32")
        before = manager.dispatch(session_id, "inspect_model", {})
        if before["status"] != "succeeded":
            return before
        directory, manifest = service.jobs.create(
            "export_gui_curve_plot", dict(session_id=session_id, **parameters)
        )
        manifest.update(
            status="running",
            started_at=now(),
            session_id=session_id,
            job_directory=str(directory),
            backend="lsprepost-native-xyplot",
            inputs=[identity],
            process=meta["process"],
        )
        xy = directory / ("curve_" + manifest["job_id"] + ".txt")
        xy.write_text(
            str(len(values)) + "\n" + "".join(f"{x:.17g},{y:.17g}\n" for x, y in values), encoding="ascii"
        )
        log = manager.directory(session_id) / "lspost.msg"
        offset = log.stat().st_size if log.exists() else 0
        try:
            create = ["open xydata " + command_path(xy), "newplot", f'show "{xy.name}~1" 0']
            created = manager.dispatch(session_id, "inspect_model", {}, native_commands=create)
            manifest["create_request"] = {k: v for k, v in created.items() if k != "data"}
            if created["status"] != "succeeded":
                raise ValueError("Native XYPlot creation failed")
            current = plot_windows(transport)
            new = current - old_windows
            if len(new) != 1 or not old_windows <= current:
                raise ValueError("Cannot identify exactly one new native plot window")
            plot_id = new.pop()
            prefix = f"xyplot {plot_id} "
            commands = [
                prefix + f'title "{title}"',
                prefix + f'xtitle "{x_label} ({x_unit})"',
                prefix + f'ytitle "{y_label} ({y_unit})"',
                prefix + "legend off",
                "print png "
                + command_path(directory / "plot.png")
                + f' nogamma enlisted "PlotWindow-{plot_id}"',
                prefix + "savefile xypair " + command_path(directory / "native.xy") + " 1 all",
            ]
            atomic_json(directory / "commands.json", create + commands)
            finished = manager.dispatch(session_id, "inspect_model", {}, native_commands=commands)
            manifest["export_request"] = {k: v for k, v in finished.items() if k != "data"}
            if finished["status"] != "succeeded":
                raise ValueError("Native plot export failed")
            with log.open("rb") as stream:
                stream.seek(offset)
                text = stream.read().decode("utf8", errors="replace")
            (directory / "native-plot.log").write_text(text, encoding="utf8")
            if native_errors(text):
                raise ValueError("Native plot diagnostics reported errors")
            numeric = verify_xy_readback(directory / "native.xy", values)
            for key in ("counts", "part_ids", "current_state"):
                if finished["data"][key] != before["data"][key]:
                    raise ValueError("Plot export changed the native model inventory/state")
            if fingerprint(source) != identity:
                raise ValueError("Source CSV changed during native plot export")
            png = check_artifact(directory / "plot.png", "png")
            csv_artifact = write_csv(directory / "plotted.csv", ["x", "y"], quantized)
            manifest.update(
                status="succeeded",
                artifacts=[png, csv_artifact, check_artifact(directory / "native.xy", "text")],
                data=dict(
                    plot_id=plot_id,
                    numeric_verification=numeric,
                    source_columns=dict(x=x_column, y=y_column),
                    declared_units=dict(x=x_unit, y=y_unit),
                    title=title,
                    labels=dict(x=f"{x_label} ({x_unit})", y=f"{y_label} ({y_unit})"),
                    plot_scope="one_curve_from_explicit_CSV_columns",
                    source_units_inferred=False,
                    model_inventory_and_state_preserved=True,
                    existing_plot_ids=sorted(old_windows),
                ),
            )
        except Exception as exc:
            manifest.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
        manifest["finished_at"] = now()
        atomic_json(directory / "job.json", manifest)
        manager.journal(
            session_id, dict(action="export_gui_curve_plot", parameters=parameters, result=manifest)
        )
        return manifest
