"""Q07 target tool ``curve_ops`` on ``domain.results.curves``, returning JobResult/v1.

Inputs are explicit CSV histories with declared time and value units. Operations run in order; each
reads named curves and adds a new name, and every result is written as ``<name>.csv`` to the job
directory with its formula, parameters and units in the result data (Q07 acceptance). Inputs are
never modified. No LS-PrePost.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .core.contracts import Artifact, CheckResult, JobResult
from .jobs import atomic_json, fingerprint

BACKEND = "python-curves"
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
RESERVED = re.compile(r"(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])", re.IGNORECASE)  # Windows device names
INPUT_KEYS = {"name", "path", "time_unit", "value_unit", "time_column", "value_column"}


@dataclass(frozen=True)
class _Op:
    sources: tuple[str, ...]
    required: tuple[str, ...]
    optional: tuple[str, ...]
    abscissa: str | None  # the abscissa every source must have; None: any
    run: Callable
    ordinate: str | None = None  # the ordinate every source must have; None: any


def _units(curve) -> dict:
    return {"t_unit": curve.meta["units"]["t"], "y_unit": curve.meta["units"]["y"]}


def _cross(x, y, p):
    from .domain.results import curves as cv

    if x.meta["units"]["t"] != y.meta["units"]["t"]:
        raise cv.CurveError(f"x is in {x.meta['units']['t']} and y in {y.meta['units']['t']}: convert one "
                            "time axis first (convert_units)")
    return cv.cross_plot(x.t, x.y, y.t, y.y, t_unit=x.meta["units"]["t"], x_unit=x.meta["units"]["y"],
                         y_unit=y.meta["units"]["y"])


def _ops() -> dict[str, _Op]:
    from .domain.results import curves as cv

    def convert(c, p):
        return cv.convert_units(c.t, c.y, **_units(c), to_t_unit=p.get("abscissa_unit"),
                                to_y_unit=p.get("value_unit"), axes=(c.meta["abscissa"], c.meta["ordinate"]))

    def engineering(c, p):
        return cv.engineering_stress_strain(c.t, c.y, p["area"], p["gauge_length"], length_unit=p["length_unit"],
                                            displacement_unit=c.meta["units"]["t"], force_unit=c.meta["units"]["y"])

    return {
        "convert_units": _Op(("input",), (), ("abscissa_unit", "value_unit"), None, convert),
        "resample": _Op(("input",), ("dt",), (), "time", lambda c, p: cv.resample(c.t, c.y, p["dt"], **_units(c))),
        "differentiate": _Op(("input",), (), (), None, lambda c, p: cv.differentiate(
            c.t, c.y, **_units(c), abscissa=c.meta["abscissa"])),
        "integrate": _Op(("input",), (), ("initial",), None, lambda c, p: cv.integrate(
            c.t, c.y, p.get("initial", 0.0), **_units(c), abscissa=c.meta["abscissa"])),
        "sae_filter": _Op(("input",), ("cfc",), ("padding",), "time", lambda c, p: cv.sae_filter(
            c.t, c.y, p["cfc"], **_units(c), padding=p.get("padding", "odd"))),
        "butterworth_filter": _Op(("input",), ("order", "cutoff_hz"), ("padding",), "time",
                                  lambda c, p: cv.butterworth_filter(c.t, c.y, p["order"], p["cutoff_hz"], **_units(c),
                                                                     padding=p.get("padding", "odd"))),
        "spectrum": _Op(("input",), (), (), "time", lambda c, p: cv.spectrum(c.t, c.y, **_units(c))),
        "cross_plot": _Op(("x", "y"), (), (), "time", _cross),
        "engineering_stress_strain": _Op(("input",), ("area", "gauge_length", "length_unit"), (), "x", engineering),
        "true_stress_strain": _Op(("input",), (), (), "engineering_strain", lambda c, p: cv.true_stress_strain(
            c.t, c.y, strain_unit=c.meta["units"]["t"], stress_unit=c.meta["units"]["y"]), "engineering_stress"),
    }


def _plan(inputs: list[dict], operations: list[dict]) -> None:
    """Refuse a malformed request before a job directory exists."""
    if not isinstance(inputs, list) or not 1 <= len(inputs) <= 20:
        raise ValueError("Give 1..20 input curves")
    if not isinstance(operations, list) or not 1 <= len(operations) <= 50:
        raise ValueError("Give 1..50 operations")
    names: dict[str, str] = {}  # casefolded -> declared: <name>.csv must not collide on Windows
    for item in inputs:
        if not isinstance(item, dict) or not {"name", "path", "time_unit", "value_unit"} <= item.keys():
            raise ValueError("Each input needs name, path, time_unit and value_unit")
        if set(item) - INPUT_KEYS:
            raise ValueError(f"Unknown input keys {sorted(set(item) - INPUT_KEYS)}; allowed: {sorted(INPUT_KEYS)}")
        if not isinstance(item["path"], str):
            raise ValueError("An input path must be a string")
        _new_name(item["name"], names)
    ops = _ops()
    for index, step in enumerate(operations):
        if not isinstance(step, dict) or not isinstance(step.get("op"), str) or step["op"] not in ops:
            raise ValueError(f"Operation {index}: 'op' must be one of {sorted(ops)}")
        spec = ops[step["op"]]
        allowed = {"op", "output", *spec.sources, *spec.required, *spec.optional}
        missing = sorted({"output", *spec.sources, *spec.required} - step.keys())
        if missing or set(step) - allowed:
            raise ValueError(f"Operation {index} ({step['op']}): missing {missing}, unknown "
                             f"{sorted(set(step) - allowed)}; allowed: {sorted(allowed)}")
        for key in spec.sources:
            if not isinstance(step[key], str) or names.get(step[key].casefold()) != step[key]:
                raise ValueError(f"Operation {index}: curve {step[key]!r} is not defined before it")
        _new_name(step["output"], names)


def _new_name(name: object, names: dict[str, str]) -> None:
    """Register a curve name; names equal up to case are refused because each output is written to
    ``<name>.csv`` and Windows file names ignore case (one file would overwrite the other)."""
    if not isinstance(name, str) or not NAME.fullmatch(name) or RESERVED.fullmatch(name) or name in names.values():
        raise ValueError(f"Curve name {name!r} must be a new identifier (letter, then letters/digits/_; <= 64; "
                         "not a Windows device name)")
    if name.casefold() in names:
        raise ValueError(f"Curve name {name!r} differs only in case from {names[name.casefold()]!r}; outputs are "
                         "files named <name>.csv and Windows file names ignore case")
    names[name.casefold()] = name


class CurveTargetTools:
    """Mixed into Service: needs ``self.jobs`` and ``self._input`` (ModelTargetTools: UNC and device
    paths are refused before the path is resolved, then ``settings.input_path`` confines it)."""

    def curve_ops(self, inputs: list[dict], operations: list[dict]) -> dict:
        """Q07: curve operations on CSV histories; every result is a CSV with formula, parameters and units.

        inputs: [{"name", "path", "time_unit" (s/ms/us/ns), "value_unit", "time_column"="time",
        "value_column"="value"}]; time must increase strictly. operations run in order, each with a new
        "output" name: convert_units(input, abscissa_unit?, value_unit?), resample(input, dt in the
        curve's time unit; filter before coarsening), differentiate(input), integrate(input, initial?),
        sae_filter(input, cfc, padding?), butterworth_filter(input, order, cutoff_hz, padding?),
        spectrum(input), cross_plot(x, y), engineering_stress_strain(input = cross_plot of force on
        displacement, area in length_unit^2, gauge_length in length_unit, length_unit),
        true_stress_strain(input = engineering curve). Filters and spectra need uniform sampling;
        padding "odd" (default) or "constant". True stress-strain is valid only for uniform
        deformation. Formulas: domain/results/curves.py."""
        from .domain.results.curves import CurveError
        from .engineering import read_curve

        _plan(inputs, operations)
        sources = [self._input(item["path"]) for item in inputs]
        directory, manifest = self.jobs.create("curve_ops", {"inputs": inputs, "operations": operations})
        curves, steps, artifacts, warnings, error, ops = {}, [], [], [], None, _ops()
        before = after = None
        try:
            before = [fingerprint(path) for path in sources]
            for item, path, identity in zip(inputs, sources, before):
                curves[item["name"]] = _input_curve(item, path, read_curve)
                steps.append({"output": item["name"], "input_file": identity, **curves[item["name"]].meta})
            for index, step in enumerate(operations):
                spec = ops[step["op"]]
                try:
                    curve = _step(spec, step, curves)
                    artifact = _write(directory, step["output"], curve)
                except CurveError as failure:
                    raise CurveError(f"operation {index} ({step['op']} -> {step['output']}): {failure}") from None
                curves[step["output"]] = curve
                artifacts.append(artifact)
                warnings += _warnings(step["output"], curve)
                steps.append({"output": step["output"], "inputs": {k: step[k] for k in spec.sources},
                              "samples": int(curve.t.size), **curve.meta})
        except Exception as failure:  # every failure is reported in the job result, as in _post_job
            error = {"type": type(failure).__name__, "message": str(failure) or type(failure).__name__}
        finally:
            try:
                after = [fingerprint(path) for path in sources]
            except OSError as failure:
                error = error or {"type": type(failure).__name__, "message": f"An input disappeared: {failure}"}
        unchanged = before is not None and after == before
        artifacts, rewritten = _recheck(artifacts)
        checks = [CheckResult(name="inputs_unchanged", status="passed" if unchanged else "failed"),
                  CheckResult(name="artifacts_match_records", status="failed" if rewritten else "passed")]
        if error is None and not unchanged:
            error = {"type": "RuntimeError", "message": "An input changed while the job ran"}
        if error is None and rewritten:
            error = {"type": "RuntimeError", "message": "Outputs changed after they were recorded: "
                     + ", ".join(rewritten)}
        result = JobResult(operation="curve_ops", status="failed" if error else "succeeded", backend=BACKEND,
                           job_id=manifest["job_id"], data={"steps": steps, "curves": sorted(curves)},
                           artifacts=tuple(artifacts), checks=tuple(checks), warnings=tuple(warnings), error=error,
                           scope="Python curve arithmetic on the given samples; inputs unchanged")
        payload = result.model_dump(mode="json")
        atomic_json(directory / "job.json", {**manifest, "status": payload["status"], "result": payload})
        return payload


def _step(spec: _Op, step: dict, curves: dict):
    from .domain.results.curves import CurveError

    given = [curves[step[key]] for key in spec.sources]
    for key, curve in zip(spec.sources, given):
        for axis, wanted in (("abscissa", spec.abscissa), ("ordinate", spec.ordinate)):
            if wanted and curve.meta[axis] != wanted:
                raise CurveError(f"{key} must have the {axis} {wanted!r}; {step[key]!r} has {curve.meta[axis]!r}")
    return spec.run(*given, {k: step[k] for k in (*spec.required, *spec.optional) if k in step})


def _input_curve(item: dict, path, read_curve):
    from .domain.results.curves import history

    columns = {"time_column": item.get("time_column", "time"), "value_column": item.get("value_column", "value")}
    t, y = read_curve(path, columns["time_column"], columns["value_column"])
    return history(t, y, t_unit=item["time_unit"], y_unit=item["value_unit"], **columns)


def _write(directory, name: str, curve) -> Artifact:
    from .domain.results.curves import CurveError
    from .post_backend import write_csv

    meta = curve.meta
    header = [meta["abscissa"], meta["ordinate"]]
    try:
        saved = write_csv(directory / f"{name}.csv", header, zip(curve.t.tolist(), curve.y.tolist()))
    except ValueError as failure:
        raise CurveError(f"writing {name}.csv: {failure}") from None
    return Artifact(path=saved["path"], kind="csv", sha256=saved["sha256"], size_bytes=saved["size"],
                    verification="verified" if saved["sha256"] else "unverified",
                    metadata={"curve": name, "columns": header, "units": meta["units"], "rows": saved["row_count"]})


def _recheck(artifacts: list[Artifact]) -> tuple[list[Artifact], list[str]]:
    """Fingerprint every output again at the end; one that no longer matches its record loses
    ``verified`` and is reported, instead of describing a file that was overwritten."""
    kept, rewritten = [], []
    for artifact in artifacts:
        path = Path(artifact.path)
        try:
            current = fingerprint(path)
            same = current["sha256"] == artifact.sha256 and current["size"] == artifact.size_bytes
        except OSError:
            same = False
        if same:
            kept.append(artifact)
            continue
        rewritten.append(path.name)
        kept.append(Artifact(path=artifact.path, kind=artifact.kind, verification="unverified",
                             metadata={**artifact.metadata, "changed_after_writing": True}))
    return kept, rewritten


def _warnings(name: str, curve) -> list[str]:
    parameters = curve.meta["parameters"]
    found = []
    if parameters.get("padding_complete") is False:
        found.append(f"{name}: the record is shorter than the filter transient; its ends are not fully settled")
    if parameters.get("coarser_than_input"):
        found.append(f"{name}: resampled to a coarser step without low-pass filtering; content above the new "
                     "Nyquist frequency aliases (filter first)")
    peak = parameters.get("maximum_engineering_stress")
    if peak and peak["samples_after"]:
        found.append(f"{name}: {peak['samples_after']} samples lie after the maximum engineering stress, where "
                     "necking makes the uniform-deformation conversion invalid")
    return found


__all__ = ["CurveTargetTools"]
