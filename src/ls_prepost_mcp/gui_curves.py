"""CSV-to-native-XYPlot rendering with numeric round-trip verification."""

import csv
import math
import re

import numpy as np

from .core.native_log import native_errors, read_delta
from .jobs import atomic_json, check_artifact, fingerprint, now
from .native import commands as nc
from .post_backend import write_csv
from .runner import record_batch_result, run_batch
from .windows_transport import WindowsCommandTransport

# Native token order is <Y scale>-<X scale>: "Lin-Log" draws a logarithmic X axis (4.13.4 batch probe).
AXES = {(False, False): "Lin-Lin", (True, False): "Lin-Log", (False, True): "Log-Lin", (True, True): "Log-Log"}
AXIS_RANGE_POLICY = ("Requested limits are sent to native XYPlot; it may widen them to the next tick (linear) "
                     "or decade-like boundary (logarithmic). Rendered extents are not read back.")


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
    return verify_curve_readback(path, [expected])[0]


def verify_curve_readback(path, expected_curves):
    lines = [line.strip() for line in path.read_text(encoding="utf8").splitlines() if line.strip()]
    offset, reports = 0, []
    for expected in expected_curves:
        if (offset >= len(lines) or not re.fullmatch(r"\d+", lines[offset])
                or int(lines[offset]) != len(expected) or offset + len(expected) >= len(lines)):
            raise ValueError("Native XY round-trip sample/curve count mismatch")
        rows = lines[offset+1:offset+1+len(expected)]
        values = np.asarray([[float(x.replace("D", "E")) for x in line.split()] for line in rows], dtype=float)
        reports.append(verify_xy_values(values, expected))
        offset += len(expected) + 1
    if offset != len(lines):
        raise ValueError("Native XY round-trip sample/curve count mismatch")
    return reports


def verify_xy_values(values, expected):
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


def curve_sources(service, path, x_column, y_column, x_unit, y_unit, curve_label, additional_curves):
    if additional_curves is not None and (not isinstance(additional_curves, list) or len(additional_curves) > 9):
        raise ValueError("Provide at most9 additional curves (10 total)")
    if additional_curves and curve_label is None:
        raise ValueError("Provide curve_label for the first curve in an overlay")
    records = [dict(path=path, x_column=x_column, y_column=y_column, label='Curve 1' if curve_label is None else curve_label,
                    x_unit=x_unit, y_unit=y_unit), *(additional_curves or [])]
    prepared, labels, total = [], set(), 0
    for record in records:
        if not isinstance(record, dict) or set(record) != {'path','x_column','y_column','label','x_unit','y_unit'}:
            raise ValueError("Each additional curve requires path,x_column,y_column,label,x_unit,y_unit")
        if record['x_unit'] != x_unit or record['y_unit'] != y_unit:
            raise ValueError("Overlay curves must declare identical axis units; convert explicitly first")
        label = plot_text(record['label'], 'curve label', 40)
        if label in labels:
            raise ValueError("Curve labels must be unique within an overlay")
        labels.add(label)
        source = service.settings.input_path(record['path'])
        identity = fingerprint(source)
        values = read_xy_csv(source, record['x_column'], record['y_column'])
        quantized = native_plot_values(values)
        total += len(values)
        if total > 500000:
            raise ValueError("Overlay exceeds500000 total sample budget")
        prepared.append(dict(spec=record, source=source, identity=identity, values=values, quantized=quantized))
    return prepared


def axis_options(x_range=None, y_range=None, x_log=False, y_log=False):
    if type(x_log) is not bool or type(y_log) is not bool:
        raise ValueError("x_log and y_log must be Boolean")
    options = dict(x_log=x_log, y_log=y_log, x_range=None, y_range=None)
    for axis, value, log in (("x", x_range, x_log), ("y", y_range, y_log)):
        if value is None:
            continue
        if (not isinstance(value, (list, tuple)) or len(value) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in value) or value[0] >= value[1]):
            raise ValueError(f"{axis}_range requires two ordered finite numbers [minimum, maximum]")
        if log and value[0] <= 0:
            raise ValueError(f"Logarithmic {axis}_range requires a positive minimum")
        options[axis + "_range"] = [float(value[0]), float(value[1])]
    return options


def require_log_samples(curves, options):
    for column, axis in ((0, "x"), (1, "y")):
        if options[axis + "_log"] and any(np.any(curve["quantized"][:, column] <= 0) for curve in curves):
            raise ValueError(f"Logarithmic {axis} axis requires every plotted {axis} sample to be positive")


def presentation_commands(prefix, title, x_label, y_label, x_unit, y_unit, labels, legend, legend_title=None,
                          options=None):
    commands = [
        prefix + f'title "{title}"',
        prefix + f'xtitle "{x_label} ({x_unit})"',
        prefix + f'ytitle "{y_label} ({y_unit})"',
        prefix + ("legend on" if legend else "legend off"),
        *([prefix + f'curvelegend {i+1}/1 "{label}"' for i, label in enumerate(labels)] if legend else []),
    ]
    if legend and legend_title is not None:
        commands.append(prefix + f'legendlabel "{legend_title}"')
    if options is not None:
        if options["x_log"] or options["y_log"]:
            commands.append(prefix + "axes " + AXES[options["x_log"], options["y_log"]])
        for axis in ("x", "y"):
            if options[axis + "_range"] is not None:
                low, high = options[axis + "_range"]
                commands += [prefix + f"{axis}min {low:.17g}", prefix + f"{axis}max {high:.17g}"]
    return commands


def axes_summary(options):
    return dict(x_scale="log" if options["x_log"] else "linear", y_scale="log" if options["y_log"] else "linear",
                requested_x_range=options["x_range"], requested_y_range=options["y_range"],
                native_axes_token=AXES[options["x_log"], options["y_log"]], range_policy=AXIS_RANGE_POLICY)


def write_combined_csv(path, curves):
    rows = [[i + 1, x, y] for i, curve in enumerate(curves) for x, y in curve["quantized"]]
    return write_csv(path, ["curve", "x", "y"], rows)


def xy_text(curves):
    return "".join(str(len(curve["values"])) + "\n" + "".join(f"{x:.17g},{y:.17g}\n" for x, y in curve["values"])
                   for curve in curves)


def plot_windows(transport):
    return {
        int(match[1])
        for row in transport.inspect_controls()
        if row["parent"] == 0
        and row["class_name"] == "wxWindowNR"
        and (match := re.fullmatch(r"PlotWindow-(\d+)", row["text"]))
    }


def check_plot_labels(title, x_label, y_label, x_unit, y_unit, legend_title=None):
    for name, value, maximum in [
        ("title", title, 80),
        ("x_label", x_label, 30),
        ("y_label", y_label, 30),
        ("x_unit", x_unit, 12),
        ("y_unit", y_unit, 12),
    ]:
        plot_text(value, name, maximum)
    if legend_title is not None:
        plot_text(legend_title, "legend_title", 40)


def export_curve_plot(service, session_id, path, x_column, y_column, title, x_label, y_label, x_unit, y_unit,
                      curve_label=None, additional_curves=None, *, action="export_gui_curve_plot", options=None,
                      legend=None, legend_title=None, extra_parameters=None):
    check_plot_labels(title, x_label, y_label, x_unit, y_unit, legend_title)
    curves = curve_sources(service, path, x_column, y_column, x_unit, y_unit, curve_label, additional_curves)
    if options is not None:
        require_log_samples(curves, options)
    quantized = curves[0]['quantized']
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
    if curve_label is not None:
        parameters['curve_label'] = curve_label
    if additional_curves is not None:
        parameters['additional_curves'] = additional_curves
    if extra_parameters:
        parameters = dict(extra_parameters)
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
        directory, manifest = service.jobs.create(action, dict(session_id=session_id, **parameters))
        manifest.update(
            status="running",
            started_at=now(),
            session_id=session_id,
            job_directory=str(directory),
            backend="lsprepost-native-xyplot",
            inputs=[curve['identity'] for curve in curves],
            process=meta["process"],
        )
        xy = directory / ("curve_" + manifest["job_id"] + ".txt")
        xy.write_text(xy_text(curves), encoding="ascii")
        log = manager.directory(session_id) / "lspost.msg"
        offset = log.stat().st_size if log.exists() else 0
        try:
            reference = xy.name + ('~1' if len(curves) == 1 else '')
            create = [nc.open_xydata(xy), "newplot", f'show "{reference}" 0']
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
                *presentation_commands(prefix, title, x_label, y_label, x_unit, y_unit,
                                       [curve["spec"]["label"] for curve in curves],
                                       len(curves) > 1 or curve_label is not None if legend is None else legend,
                                       legend_title, options),
                nc.print_png(directory / "plot.png", mode="nogamma", window=f"PlotWindow-{plot_id}"),
                nc.save_xypair(directory / "native.xy", plot_id),
            ]
            atomic_json(directory / "commands.json", create + commands)
            finished = manager.dispatch(session_id, "inspect_model", {}, native_commands=commands)
            manifest["export_request"] = {k: v for k, v in finished.items() if k != "data"}
            if finished["status"] != "succeeded":
                raise ValueError("Native plot export failed")
            text = read_delta(log, offset, existed=True)
            (directory / "native-plot.log").write_text(text, encoding="utf8")
            if native_errors(text):
                raise ValueError("Native plot diagnostics reported errors")
            numeric_curves = verify_curve_readback(directory / "native.xy", [curve['values'] for curve in curves])
            numeric = numeric_curves[0]
            for key in ("counts", "part_ids", "current_state"):
                if finished["data"][key] != before["data"][key]:
                    raise ValueError("Plot export changed the native model inventory/state")
            if any(fingerprint(curve['source']) != curve['identity'] for curve in curves):
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
                    plot_scope="one_curve_from_explicit_CSV_columns" if len(curves) == 1 else "multiple_curves_explicit_CSV_columns",
                    curve_count=len(curves),
                    curves=[dict(number=i+1, label=curve['spec']['label'], source=curve['identity'],
                                 columns=dict(x=curve['spec']['x_column'], y=curve['spec']['y_column']),
                                 numeric_verification=numeric_curves[i]) for i, curve in enumerate(curves)],
                    resampled=False,
                    source_units_inferred=False,
                    model_inventory_and_state_preserved=True,
                    existing_plot_ids=sorted(old_windows),
                ),
            )
            for i, curve in enumerate(curves[1:], 2):
                manifest['artifacts'].append(write_csv(directory/f'plotted-{i}.csv', ['x','y'], curve['quantized']))
            if options is not None:
                manifest["data"].update(axes=axes_summary(options), legend_title=legend_title)
                manifest["artifacts"].append(write_combined_csv(directory / "curves.csv", curves))
        except Exception as exc:
            manifest.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
        manifest["finished_at"] = now()
        atomic_json(directory / "job.json", manifest)
        manager.journal(session_id, dict(action=action, parameters=parameters, result=manifest))
        return manifest


def xyplot_sources(service, curves, x_unit, y_unit):
    if not isinstance(curves, list) or not 1 <= len(curves) <= 10:
        raise ValueError("render_xyplot requires 1..10 curves")
    keys = {'path', 'x_column', 'y_column', 'label', 'x_unit', 'y_unit'}
    if any(not isinstance(curve, dict) or set(curve) != keys for curve in curves):
        raise ValueError("Each curve requires path,x_column,y_column,label,x_unit,y_unit")
    if any(curve['x_unit'] != x_unit or curve['y_unit'] != y_unit for curve in curves):
        raise ValueError("Every curve must declare the plot axis units exactly; convert explicitly first")
    first = curves[0]
    return curve_sources(service, first['path'], first['x_column'], first['y_column'], x_unit, y_unit,
                         first['label'], curves[1:] or None)


def render_xyplot(service, curves, title, x_label, y_label, x_unit, y_unit, x_range=None, y_range=None,
                  x_log=False, y_log=False, legend=True, legend_title=None, session_id=None):
    if type(legend) is not bool:
        raise ValueError("legend must be Boolean")
    options = axis_options(x_range, y_range, x_log, y_log)
    check_plot_labels(title, x_label, y_label, x_unit, y_unit, legend_title)
    prepared = xyplot_sources(service, curves, x_unit, y_unit)
    require_log_samples(prepared, options)
    parameters = dict(curves=curves, title=title, x_label=x_label, y_label=y_label, x_unit=x_unit, y_unit=y_unit,
                      x_range=x_range, y_range=y_range, x_log=x_log, y_log=y_log, legend=legend,
                      legend_title=legend_title)
    if session_id is not None:
        first = curves[0]
        return export_curve_plot(service, session_id, first['path'], first['x_column'], first['y_column'], title,
                                 x_label, y_label, x_unit, y_unit, first['label'], curves[1:] or None,
                                 action="render_xyplot", options=options, legend=legend, legend_title=legend_title,
                                 extra_parameters=parameters)
    return render_batch(service, prepared, title, x_label, y_label, x_unit, y_unit, options, legend, legend_title,
                        parameters)


def render_batch(service, curves, title, x_label, y_label, x_unit, y_unit, options, legend, legend_title, parameters):
    executable = service.settings.native_executable()
    directory, manifest = service.jobs.create("render_xyplot", parameters)
    manifest.update(status="running", started_at=now(), job_directory=str(directory), route="batch",
                    backend="lsprepost-native-xyplot-batch", executable=fingerprint(executable),
                    inputs=[curve['identity'] for curve in curves])
    try:
        (directory / "curves.txt").write_text(xy_text(curves), encoding="ascii")
        reference = "curves.txt" + ("~1" if len(curves) == 1 else "")
        prefix = "xyplot 1 "
        commands = [
            nc.open_xydata("curves.txt"), "newplot", f'show "{reference}" 0',
            *presentation_commands(prefix, title, x_label, y_label, x_unit, y_unit,
                                   [curve["spec"]["label"] for curve in curves], legend, legend_title, options),
            nc.print_png("plot.png", mode="nogamma", window="PlotWindow-1"),
            nc.save_xypair("native.xy", 1),
            "exit",
        ]
        nc.write_cfile(directory / "commands.cfile", commands)
        execution = run_batch(executable, directory / "commands.cfile", directory, timeout=service.settings.timeout,
                              graphics=False, operation="render_xyplot")
        record_batch_result(execution, manifest, directory)
        numeric = verify_curve_readback(directory / "native.xy", [curve['values'] for curve in curves])
        if any(fingerprint(curve['source']) != curve['identity'] for curve in curves):
            raise ValueError("Source CSV changed during native plot export")
        png = check_artifact(directory / "plot.png", "png")
        native_xy = check_artifact(directory / "native.xy", "text")
        table = write_combined_csv(directory / "curves.csv", curves)
        manifest["artifacts"] += [png, table, native_xy, check_artifact(directory / "commands.cfile", "text")]
        manifest.update(
            status="succeeded",
            data=dict(
                plot_id=1,
                curve_count=len(curves),
                title=title,
                labels=dict(x=f"{x_label} ({x_unit})", y=f"{y_label} ({y_unit})"),
                declared_units=dict(x=x_unit, y=y_unit),
                legend=legend,
                legend_title=legend_title,
                axes=axes_summary(options),
                curves=[dict(number=i + 1, label=curve['spec']['label'], source=curve['identity'],
                             columns=dict(x=curve['spec']['x_column'], y=curve['spec']['y_column']),
                             numeric_verification=numeric[i]) for i, curve in enumerate(curves)],
                csv_columns=dict(curve="1-based curve number in legend order", x=x_unit, y=y_unit),
                png_csv_consistency=dict(
                    same_native_plot_window=True,
                    readback_after_png=True,
                    csv_equals_native_readback="per-curve float32 storage check, rtol 5e-11, absolute tolerance 0",
                    png_sha256=png.get("sha256"), csv_sha256=table.get("sha256"),
                    native_xy_sha256=native_xy.get("sha256"),
                ),
                visible_gui=False,
                resampled=False,
                source_units_inferred=False,
            ),
        )
    except Exception as exc:
        manifest.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
    manifest["finished_at"] = now()
    atomic_json(directory / "job.json", manifest)
    return manifest
