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


class EngineeringTools:
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

    def combine_history_curves(self, paths: list[str], operation: str, units: str) -> dict:
        """Sum, average or subtract aligned scalar histories without extrapolation. Use e.g. nodal reaction-force sums; units must already match."""
        if not 2 <= len(paths) <= 100 or operation not in ("sum", "mean", "difference"):
            raise ValueError("Provide 2..100 histories and sum/mean/difference")
        if operation == "difference" and len(paths) != 2:
            raise ValueError("Difference requires two curves")
        sources = [self.settings.input_path(p) for p in paths]

        def work(directory):
            times, values = align([read_curve(p) for p in sources])
            result = (
                np.sum(values, axis=0)
                if operation == "sum"
                else np.mean(values, axis=0)
                if operation == "mean"
                else values[0] - values[1]
            )
            artifact = write_csv(directory / "curve.csv", ["time", "value"], zip(times, result))
            return dict(
                operation=operation, row_count=len(times), alignment="common interval, linear interpolation"
            ), [artifact]

        return self._post_job("combine_history_curves", dict(operation=operation, units=units), sources, work)

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
