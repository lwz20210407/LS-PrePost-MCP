"""Engineering curves with explicit units, signs, time alignment and assumptions."""

import csv
import math
from pathlib import Path

import numpy as np

from .jobs import atomic_json, check_artifact
from .post_backend import write_csv

LENGTH_TO_MM = {"mm": 1.0, "m": 1000.0, "cm": 10.0, "um": 0.001}
FORCE_TO_N = {"N": 1.0, "kN": 1000.0, "MN": 1e6}


def read_curve(path, time_column="time", value_column="value"):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if (
            not reader.fieldnames
            or time_column not in reader.fieldnames
            or value_column not in reader.fieldnames
        ):
            raise ValueError("Curve must contain explicit time/value columns")
        rows = []
        for row in reader:
            rows.append([float(row[time_column]), float(row[value_column])])
            if len(rows) > 1000000:
                raise ValueError("Curve exceeds one million samples")
    a = np.asarray(rows, dtype=float)
    if len(a) < 2 or a.ndim != 2 or not np.isfinite(a).all() or np.any(np.diff(a[:, 0]) <= 0):
        raise ValueError("Each curve must be a finite single-entity history with strictly increasing time")
    return a[:, 0], a[:, 1]


def align(curves):
    lower = max(t[0] for t, v in curves)
    upper = min(t[-1] for t, v in curves)
    if lower >= upper:
        raise ValueError("Curves have no overlapping time interval")
    times = np.unique(
        np.concatenate([t[(t >= lower) & (t <= upper)] for t, v in curves] + [np.array([lower, upper])])
    )
    if len(times) > 1000000:
        raise ValueError("Aligned curve exceeds one million samples")
    return times, [np.interp(times, t, v) for t, v in curves]


def convert_samples(curve, conversion):
    time, values = curve
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        converted_time = time * conversion["time_factor"]
        converted_values = values * conversion["value_factor"]
    if not np.isfinite(converted_time).all() or not np.isfinite(converted_values).all():
        raise ValueError("Unit conversion produced nonfinite samples")
    if np.any((values != 0) & (converted_values == 0)) or np.any((time != 0) & (converted_time == 0)):
        raise ValueError("Unit conversion underflow would erase nonzero samples")
    if np.any(np.diff(converted_time) <= 0):
        raise ValueError("Unit conversion collapsed time resolution")
    return converted_time, converted_values


class EngineeringTools:
    def convert_history_units(
        self,
        path: str,
        value_unit: str,
        output_value_unit: str,
        time_unit: str,
        output_time_unit: str,
        time_column: str = "time",
        value_column: str = "value",
    ) -> dict:
        """Convert one scalar history with explicit compatible mechanical units, including time. Returns time,value CSV and exact-factor provenance. No unit inference, temperature offsets or mixed-entity curves."""
        from .units import curve_conversion

        conversion = curve_conversion(time_unit, value_unit, output_time_unit, output_value_unit)
        source = self.settings.input_path(path)

        def work(directory):
            times, values = convert_samples(read_curve(source, time_column, value_column), conversion)
            artifact = write_csv(directory / "curve.csv", ["time", "value"], zip(times, values))
            return dict(backend="explicit-unit-math", row_count=len(times), unit_contract=conversion), [
                artifact
            ]

        return self._post_job(
            "convert_history_units",
            dict(
                units=output_value_unit,
                unit_contract=conversion,
                time_column=time_column,
                value_column=value_column,
            ),
            [source],
            work,
        )

    def build_tensile_curves(
        self,
        force_curve: str,
        displacement_curve: str,
        area: float,
        gauge_length: float,
        force_unit: str,
        length_unit: str,
        time_unit: str,
        reference_displacement_curve: str | None = None,
        force_sign: int = 1,
        displacement_sign: int = 1,
        true_conversion: bool = False,
    ) -> dict:
        """Build force-displacement and engineering stress-strain from aligned histories. Area uses length_unit squared; optional true conversion assumes uniform incompressible deformation before necking."""
        if force_unit not in FORCE_TO_N or length_unit not in LENGTH_TO_MM:
            raise ValueError("Unsupported force/length unit")
        if (
            not all(math.isfinite(v) and v > 0 for v in (area, gauge_length))
            or force_sign not in (-1, 1)
            or displacement_sign not in (-1, 1)
        ):
            raise ValueError("Positive area/gauge length and signs ±1 required")
        if not isinstance(time_unit, str) or not time_unit.strip():
            raise ValueError("Explicit shared time unit required")
        paths = [self.settings.input_path(force_curve), self.settings.input_path(displacement_curve)]
        if reference_displacement_curve:
            paths.append(self.settings.input_path(reference_displacement_curve))

        def work(directory):
            times, values = align([read_curve(p) for p in paths])
            force = values[0] * FORCE_TO_N[force_unit] * force_sign
            displacement = (
                (values[1] - (values[2] if len(values) > 2 else 0))
                * LENGTH_TO_MM[length_unit]
                * displacement_sign
            )
            strain = displacement / (gauge_length * LENGTH_TO_MM[length_unit])
            stress = force / (area * LENGTH_TO_MM[length_unit] ** 2)
            energy = np.concatenate(([0.0], np.cumsum((force[1:] + force[:-1]) / 2 * np.diff(displacement))))
            header = [
                "time",
                "force_N",
                "displacement_mm",
                "engineering_strain",
                "engineering_stress_MPa",
                "work_N_mm",
            ]
            arrays = [times, force, displacement, strain, stress, energy]
            assumptions = []
            if true_conversion:
                if np.any(strain <= -1):
                    raise ValueError("Logarithmic conversion requires engineering strain > -1")
                header += ["true_strain_uniform", "true_stress_MPa_uniform"]
                arrays += [np.log1p(strain), stress * (1 + strain)]
                assumptions = [
                    "Uniform incompressible deformation; conversion is not valid after localized necking"
                ]
            artifact = write_csv(directory / "tensile.csv", header, zip(*arrays))
            data = dict(
                force_unit="N",
                displacement_unit="mm",
                stress_unit="MPa",
                time_unit=time_unit,
                alignment="Union of samples within common interval; linear interpolation, no extrapolation",
                relative_displacement=bool(reference_displacement_curve),
                assumptions=assumptions,
                row_count=len(times),
                peak_force_N=float(force.max()),
                peak_engineering_stress_MPa=float(stress.max()),
                work_N_mm=float(energy[-1]),
                work_J=float(energy[-1] / 1000),
            )
            return data, [artifact]

        return self._post_job(
            "build_tensile_curves",
            dict(
                units=f"{force_unit};{length_unit};{time_unit}",
                area=area,
                gauge_length=gauge_length,
                force_sign=force_sign,
                displacement_sign=displacement_sign,
                true_conversion=true_conversion,
            ),
            paths,
            work,
        )

    def combine_history_curves(
        self,
        paths: list[str],
        operation: str,
        units: str,
        source_units: list[dict] | None = None,
        time_unit: str | None = None,
    ) -> dict:
        """Sum/average/subtract scalar histories without extrapolation. Optional source_units=[{time,value},...] explicitly converts each curve to units/time_unit before alignment. Without metadata, matching units are caller assumptions, not validated."""
        from .units import curve_conversion

        if not 2 <= len(paths) <= 100 or operation not in ("sum", "mean", "difference"):
            raise ValueError("Provide 2..100 histories and sum/mean/difference")
        if operation == "difference" and len(paths) != 2:
            raise ValueError("Difference requires two curves")
        conversions = None
        if source_units is not None:
            if (
                not isinstance(source_units, list)
                or len(source_units) != len(paths)
                or any(not isinstance(s, dict) or set(s) != {"time", "value"} for s in source_units)
            ):
                raise ValueError("source_units requires one {time,value} declaration per input curve")
            conversions = [curve_conversion(s["time"], s["value"], time_unit, units) for s in source_units]
            source_units = [dict(time=c["source_time_unit"], value=c["source_value_unit"]) for c in conversions]
        elif time_unit is not None:
            raise ValueError("Provide per-source units before specifying a converted output time unit")
        sources = [self.settings.input_path(p) for p in paths]

        def work(directory):
            curves = [read_curve(p) for p in sources]
            if conversions is not None:
                curves = [convert_samples(c, unit) for c, unit in zip(curves, conversions)]
            times, values = align(curves)
            result = (
                np.sum(values, axis=0)
                if operation == "sum"
                else np.mean(values, axis=0)
                if operation == "mean"
                else values[0] - values[1]
            )
            artifact = write_csv(directory / "curve.csv", ["time", "value"], zip(times, result))
            return dict(
                operation=operation,
                row_count=len(times),
                alignment="common interval, linear interpolation",
                unit_contract=dict(
                    mode="declared_conversion" if conversions is not None else "assumed_shared",
                    output_value_unit=units,
                    output_time_unit=time_unit,
                    dimensional_compatibility_checked=conversions is not None,
                    source_unit_labels_verified=False,
                    conversions=conversions,
                ),
            ), [artifact]

        return self._post_job(
            "combine_history_curves",
            dict(operation=operation, units=units, source_units=source_units, time_unit=time_unit),
            sources,
            work,
        )

    def assess_energy_balance(
        self,
        kinetic_curve: str,
        internal_curve: str,
        units: str,
        hourglass_curve: str | None = None,
        external_work_curve: str | None = None,
        kinetic_ratio_limit: float = 0.05,
        hourglass_ratio_limit: float = 0.05,
    ) -> dict:
        """Report KE/|IE| and HG/|IE| with undefined zero-denominator states. Optional work balance is a partial selected-energy budget, not a solver certification."""
        if not all(math.isfinite(x) and x >= 0 for x in (kinetic_ratio_limit, hourglass_ratio_limit)):
            raise ValueError("Nonnegative finite screening limits required")
        sources = [self.settings.input_path(kinetic_curve), self.settings.input_path(internal_curve)]
        if hourglass_curve:
            sources.append(self.settings.input_path(hourglass_curve))
        if external_work_curve:
            sources.append(self.settings.input_path(external_work_curve))

        def work(directory):
            times, values = align([read_curve(p) for p in sources])
            ke, ie = values[:2]
            hg = values[2] if hourglass_curve else np.zeros_like(ke)
            denominator = np.abs(ie)
            floor = max(float(denominator.max()) * 1e-12, np.finfo(float).tiny)
            defined = denominator > floor
            ratio = np.divide(np.abs(ke), denominator, out=np.zeros_like(ke), where=defined)
            hratio = np.divide(np.abs(hg), denominator, out=np.zeros_like(hg), where=defined)
            rows = (
                [
                    t,
                    k,
                    e,
                    h if hourglass_curve else None,
                    float(r) if ok else None,
                    float(hr) if ok and hourglass_curve else None,
                    int(ok),
                ]
                for t, k, e, h, r, hr, ok in zip(times, ke, ie, hg, ratio, hratio, defined)
            )
            artifact = write_csv(
                directory / "energy.csv",
                ["time", "kinetic", "internal", "hourglass", "ke_ie_ratio", "hg_ie_ratio", "ratio_defined"],
                rows,
                {"hourglass", "ke_ie_ratio", "hg_ie_ratio"},
            )
            data = dict(
                defined_rows=int(defined.sum()),
                undefined_rows=int((~defined).sum()),
                kinetic_exceedances=int(((ratio > kinetic_ratio_limit) & defined).sum()),
                hourglass_exceedances=int(((hratio > hourglass_ratio_limit) & defined).sum())
                if hourglass_curve
                else None,
                hourglass_supplied=bool(hourglass_curve),
                quasistatic_certified=False,
                scope="Screening only; denominator floor is scale-relative; omitted energies are not inferred",
            )
            if external_work_curve:
                work = values[-1]
                selected = ke + ie + hg
                residual = (selected - selected[0]) - (work - work[0])
                data["selected_energy_max_residual"] = float(np.max(np.abs(residual)))
                data["balance_note"] = (
                    "Includes only supplied KE/IE/HG; damping, contact, eroded, thermal and other terms may be missing"
                )
            atomic_json(directory / "summary.json", data)
            return data, [artifact, check_artifact(directory / "summary.json", "json")]

        return self._post_job(
            "assess_energy_balance",
            dict(
                units=units,
                kinetic_ratio_limit=kinetic_ratio_limit,
                hourglass_ratio_limit=hourglass_ratio_limit,
            ),
            sources,
            work,
        )

    def native_energy_postprocess(
        self, path: str, units: str, include_hourglass: bool = False, include_external_work: bool = False
    ) -> dict:
        """Extract named GLSTAT energies through native SCLBinout, then screen ratios and an optional partial work budget. Single binout file; missing requested energies fail explicitly."""
        quantities = ["kinetic_energy", "internal_energy"]
        if include_hourglass:
            quantities.append("hourglass_energy")
        if include_external_work:
            quantities.append("external_work")
        stages = {}
        for quantity in quantities:
            stage = self.extract_native_binout_curve(path, "glstat", quantity, units)
            stages[quantity] = stage
            if stage["status"] != "succeeded":
                return dict(status="failed", stages=stages, error="Native energy extraction failed")

        def output(name):
            return stages[name]["artifacts"][0]["path"] if name in stages else None

        result = self.assess_energy_balance(
            output("kinetic_energy"),
            output("internal_energy"),
            units,
            output("hourglass_energy"),
            output("external_work"),
        )
        result["native_stage_job_ids"] = {k: v["job_id"] for k, v in stages.items()}
        atomic_json(Path(result["job_directory"]) / "job.json", result)
        return result

    def native_tensile_postprocess(
        self,
        force_path: str,
        nodout_path: str,
        force_database: str,
        force_component: int,
        force_entity_id: int,
        top_node: int,
        bottom_node: int,
        displacement_component: int,
        area: float,
        gauge_length: float,
        force_unit: str,
        length_unit: str,
        time_unit: str,
        force_sign: int = 1,
        displacement_sign: int = 1,
    ) -> dict:
        """Complete native ASCII extraction -> relative gauge displacement -> force/displacement/stress/strain workflow, with explicit entity/component/units and source preservation."""
        if displacement_component not in (1, 2, 3):
            raise ValueError("NODOUT displacement component must be 1=X,2=Y,3=Z")
        force = self.extract_native_ascii_curve(
            force_path, force_database, force_component, force_unit, force_entity_id
        )
        top = self.extract_native_ascii_curve(
            nodout_path, "nodout", displacement_component, length_unit, top_node
        )
        bottom = self.extract_native_ascii_curve(
            nodout_path, "nodout", displacement_component, length_unit, bottom_node
        )
        stages = [force, top, bottom]
        if any(r["status"] != "succeeded" for r in stages):
            return dict(
                status="failed",
                stages=stages,
                error="Native history extraction failed; no derived engineering curve produced",
            )
        result = self.build_tensile_curves(
            force["artifacts"][0]["path"],
            top["artifacts"][0]["path"],
            area,
            gauge_length,
            force_unit,
            length_unit,
            time_unit,
            bottom["artifacts"][0]["path"],
            force_sign,
            displacement_sign,
        )
        result["native_stage_job_ids"] = [r["job_id"] for r in stages]
        atomic_json(Path(result["job_directory"]) / "job.json", result)
        return result

    def curve_ops(
        self,
        path: str,
        operation: str,
        units: str = "",
        secondary_path: str | None = None,
        cfc: int = 60,
        custom_cutoff_hz: float | None = None,
        dt: float | None = None,
        num_points: int | None = None,
        time_column: str | int = 1,
        value_column: str | int = 2,
        secondary_time_column: str | int = 1,
        secondary_value_column: str | int = 2,
        delimiter: str = "comma",
        skip_rows: int = 1,
    ) -> dict:
        """Perform operations on numeric history curves: SAE J211/Butterworth filtering, resampling, FFT spectrum, cross plot, true stress-strain, differentiation, integration, or summary statistics."""
        from .curve_ops import (
            compute_fft,
            cross_plot,
            curve_summary,
            differentiate_curve,
            engineering_to_true_stress_strain,
            integrate_curve,
            read_curve_table,
            resample_curve,
            sae_j211_filter,
        )

        source = self.settings.input_path(path)
        sources = [source]
        secondary_source = None
        if secondary_path:
            secondary_source = self.settings.input_path(secondary_path)
            sources.append(secondary_source)

        def work(directory):
            times, values, _ = read_curve_table(source, time_column, value_column, delimiter, skip_rows)
            artifacts = []

            if operation in ("filter", "sae_filter", "sae"):
                filtered, meta = sae_j211_filter(times, values, cfc=cfc, custom_cutoff_hz=custom_cutoff_hz)
                artifact = write_csv(directory / "curve.csv", ["time", "value"], zip(times, filtered))
                artifacts.append(artifact)
                summary = {
                    "operation": "sae_filter",
                    "filter_metadata": meta,
                    "summary": curve_summary(times, filtered),
                    "input_units": units,
                    "output_units": units,
                }
            elif operation == "resample":
                new_t, new_v, meta = resample_curve(times, values, dt=dt, num_points=num_points)
                artifact = write_csv(directory / "curve.csv", ["time", "value"], zip(new_t, new_v))
                artifacts.append(artifact)
                summary = {
                    "operation": "resample",
                    "resample_metadata": meta,
                    "summary": curve_summary(new_t, new_v),
                    "input_units": units,
                    "output_units": units,
                }
            elif operation == "fft":
                freqs, amps, meta = compute_fft(times, values)
                artifact = write_csv(directory / "fft.csv", ["frequency_hz", "amplitude"], zip(freqs, amps))
                artifacts.append(artifact)
                summary = {
                    "operation": "fft",
                    "fft_metadata": meta,
                    "input_units": units,
                }
            elif operation == "cross_plot":
                if not secondary_source:
                    raise ValueError("cross_plot operation requires secondary_path for Y-curve")
                t2, v2, _ = read_curve_table(
                    secondary_source, secondary_time_column, secondary_value_column, delimiter, skip_rows
                )
                t_com, x_aln, y_aln, meta = cross_plot(times, values, t2, v2)
                artifact = write_csv(directory / "cross_plot.csv", ["time", "x", "y"], zip(t_com, x_aln, y_aln))
                artifacts.append(artifact)
                summary = {
                    "operation": "cross_plot",
                    "cross_plot_metadata": meta,
                    "input_units": units,
                }
            elif operation == "true_stress_strain":
                if secondary_source:
                    _, eng_stress, _ = read_curve_table(
                        secondary_source, secondary_time_column, secondary_value_column, delimiter, skip_rows
                    )
                    eng_strain = values
                else:
                    eng_strain = times
                    eng_stress = values
                t_strain, t_stress, meta = engineering_to_true_stress_strain(eng_strain, eng_stress)
                artifact = write_csv(
                    directory / "true_stress_strain.csv",
                    ["engineering_strain", "engineering_stress", "true_strain", "true_stress"],
                    zip(eng_strain, eng_stress, t_strain, t_stress),
                )
                artifacts.append(artifact)
                summary = {
                    "operation": "true_stress_strain",
                    "conversion_metadata": meta,
                }
            elif operation == "differentiate":
                deriv = differentiate_curve(times, values)
                artifact = write_csv(directory / "curve.csv", ["time", "value"], zip(times, deriv))
                artifacts.append(artifact)
                summary = {
                    "operation": "differentiate",
                    "summary": curve_summary(times, deriv),
                    "input_units": units,
                    "output_units": f"{units} / time" if units else "",
                }
            elif operation == "integrate":
                integ = integrate_curve(times, values)
                artifact = write_csv(directory / "curve.csv", ["time", "value"], zip(times, integ))
                artifacts.append(artifact)
                summary = {
                    "operation": "integrate",
                    "summary": curve_summary(times, integ),
                    "input_units": units,
                    "output_units": f"{units} * time" if units else "",
                }
            elif operation == "summary":
                artifact = write_csv(directory / "curve.csv", ["time", "value"], zip(times, values))
                artifacts.append(artifact)
                summary = {
                    "operation": "summary",
                    "summary": curve_summary(times, values),
                    "input_units": units,
                }
            else:
                raise ValueError(f"Unsupported curve operation: '{operation}'")

            atomic_json(directory / "summary.json", summary)
            artifacts.append(check_artifact(directory / "summary.json", "json"))
            return summary, artifacts

        unit_label = units.strip() if (isinstance(units, str) and units.strip()) else "dimensionless"
        return self._post_job(
            "curve_ops",
            dict(
                path=str(source),
                operation=operation,
                units=unit_label,
                cfc=cfc,
                custom_cutoff_hz=custom_cutoff_hz,
                dt=dt,
                num_points=num_points,
            ),
            sources,
            work,
        )

    def render_xyplot(
        self,
        path: str,
        x_column: str | int = 1,
        y_column: str | int = 2,
        title: str = "XY Plot",
        x_label: str = "X",
        y_label: str = "Y",
        x_unit: str = "",
        y_unit: str = "",
        curve_label: str = "Curve 1",
        additional_curves: list[dict] | None = None,
        x_range: list[float] | None = None,
        y_range: list[float] | None = None,
        x_scale: str = "linear",
        y_scale: str = "linear",
        show_grid: bool = True,
        show_legend: bool = True,
        width: int = 1280,
        height: int = 720,
    ) -> dict:
        """Render publication-grade XYPlot of up to 10 curves in headless batch context, producing PNG and identical CSV."""
        from .xyplot import execute_render_xyplot

        source = self.settings.input_path(path)
        sources = [source]
        if additional_curves:
            for item in additional_curves:
                sources.append(self.settings.input_path(item["path"]))

        def work(directory):
            summary, files = execute_render_xyplot(
                directory=directory,
                path=str(source),
                x_column=x_column,
                y_column=y_column,
                title=title,
                x_label=x_label,
                y_label=y_label,
                x_unit=x_unit,
                y_unit=y_unit,
                curve_label=curve_label,
                additional_curves=additional_curves,
                x_range=x_range,
                y_range=y_range,
                x_scale=x_scale,
                y_scale=y_scale,
                show_grid=show_grid,
                show_legend=show_legend,
                width=width,
                height=height,
            )
            artifacts = [
                check_artifact(files[0], "png"),
                check_artifact(files[1], "csv"),
            ]
            atomic_json(directory / "summary.json", summary)
            artifacts.append(check_artifact(directory / "summary.json", "json"))
            return summary, artifacts

        unit_label = f"{x_unit};{y_unit}".strip(";") or "dimensionless"
        return self._post_job(
            "render_xyplot",
            dict(
                path=str(source),
                title=title,
                x_label=x_label,
                y_label=y_label,
                x_unit=x_unit,
                y_unit=y_unit,
                units=unit_label,
                x_scale=x_scale,
                y_scale=y_scale,
            ),
            sources,
            work,
        )

    def extract_history(
        self,
        source: str,
        entity_type: str,
        entity_ids: list[int] | None = None,
        quantity: str = "displacement",
        components: list[str] | None = None,
        units: str = "",
    ) -> dict:
        """Extract multi-entity time histories across node, element, part, and global modes."""
        from .history import extract_history as run_extract_history

        db_path = self.settings.input_path(source)

        def work(directory):
            summary, headers, rows = run_extract_history(
                source=db_path,
                entity_type=entity_type,
                entity_ids=entity_ids,
                quantity=quantity,
                components=components,
                units=units,
            )
            csv_path = directory / "history.csv"
            artifacts = [write_csv(csv_path, headers, rows)]
            atomic_json(directory / "summary.json", summary)
            artifacts.append(check_artifact(directory / "summary.json", "json"))
            return summary, artifacts

        unit_label = units.strip() if (isinstance(units, str) and units.strip()) else "raw"
        return self._post_job(
            "extract_history",
            dict(
                source=str(db_path),
                entity_type=entity_type,
                entity_ids=entity_ids,
                quantity=quantity,
                components=components,
                units=unit_label,
            ),
            [db_path],
            work,
        )

    def measure(
        self,
        measurement: str,
        model: str | None = None,
        node_coords: list[list[float]] | None = None,
        node_ids: list[int] | None = None,
        nodes: dict[int, list[float]] | None = None,
        elements: list[list[int]] | None = None,
        part_id: int | None = None,
        density: float | None = None,
        thickness: float | None = None,
        units: str = "mm",
        density_units: str = "",
        clearance_set1: list[list[float]] | None = None,
        clearance_set2: list[list[float]] | None = None,
    ) -> dict:
        """Measure geometry or physical properties (F4 inspection tool): distance, angle, dihedral, area, volume, mass, inertia, clearance."""
        from .measure import (
            measure_angle,
            measure_clearance,
            measure_dihedral,
            measure_distance,
            measure_part_geometry_and_physics,
            measure_point_to_plane_distance,
        )

        sources = []
        if model:
            sources.append(self.settings.input_path(model))

        def work(directory):
            if measurement == "distance":
                if not node_coords or len(node_coords) != 2:
                    raise ValueError("Distance measurement requires 2 coordinates")
                res = measure_distance(node_coords[0], node_coords[1], node_ids, units=units)
            elif measurement == "angle":
                if not node_coords or len(node_coords) != 3:
                    raise ValueError("Angle measurement requires 3 coordinates (p1, vertex, p3)")
                res = measure_angle(node_coords[0], node_coords[1], node_coords[2], node_ids)
            elif measurement == "dihedral":
                if not node_coords or len(node_coords) != 4:
                    raise ValueError("Dihedral measurement requires 4 coordinates")
                res = measure_dihedral(node_coords[0], node_coords[1], node_coords[2], node_coords[3], node_ids)
            elif measurement == "point_to_plane_distance":
                if not node_coords or len(node_coords) != 4:
                    raise ValueError("point_to_plane_distance requires target point and 3 plane points")
                res = measure_point_to_plane_distance(
                    node_coords[0], node_coords[1], node_coords[2], node_coords[3], units=units
                )
            elif measurement in ("area", "volume", "mass", "center_of_mass", "inertia"):
                if not nodes or not elements:
                    raise ValueError(f"{measurement} measurement requires nodes and elements dictionary")
                nodes_arr = {int(k): np.asarray(v, dtype=float) for k, v in nodes.items()}
                res = measure_part_geometry_and_physics(
                    nodes_arr,
                    elements,
                    measurement=measurement,
                    density=density,
                    thickness=thickness,
                    units=units,
                    density_units=density_units,
                    part_id=part_id,
                )
            elif measurement == "clearance":
                if clearance_set1 is None or clearance_set2 is None:
                    raise ValueError("Clearance measurement requires clearance_set1 and clearance_set2")
                res = measure_clearance(np.asarray(clearance_set1), np.asarray(clearance_set2), units=units)
            else:
                raise ValueError(f"Unsupported measurement type: '{measurement}'")

            atomic_json(directory / "summary.json", res)
            artifacts = [check_artifact(directory / "summary.json", "json")]
            return res, artifacts

        unit_label = units.strip() if (isinstance(units, str) and units.strip()) else "mm"
        return self._post_job(
            "measure",
            dict(
                measurement=measurement,
                part_id=part_id,
                units=unit_label,
                density=density,
            ),
            sources,
            work,
        )
