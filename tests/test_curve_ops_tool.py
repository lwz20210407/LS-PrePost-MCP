"""Q07 target tool curve_ops: JobResult/v1, one CSV per named result, formulas and units in the data."""
import asyncio
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

import ls_prepost_mcp.curve_target_tools as tool
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.server import build_server
from ls_prepost_mcp.service import Service

FS = 10_000.0  # Hz; times are written in ms


def _history(path: Path, t: np.ndarray, values: np.ndarray) -> Path:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["time", "value"])
        writer.writerows(zip(t.tolist(), values.tolist()))
    return path


def _read(path: str) -> tuple[list[str], np.ndarray]:
    with open(path, newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    return rows[0], np.asarray(rows[1:], dtype=float)


@pytest.fixture()
def service(tmp_path: Path) -> Service:
    t = np.arange(0, 0.1, 1 / FS)  # s
    force = 20.0 * np.sin(math.pi * t / 0.1) + 0.5 * np.sin(2 * math.pi * 3000 * t)  # kN: 5 Hz hump + 3 kHz ripple
    _history(tmp_path / "force.csv", t * 1000, force)
    _history(tmp_path / "displacement.csv", t * 1000, 10.0 * t / 0.1)  # mm
    return Service(Settings(tmp_path))


def _run(service: Service, operations: list[dict], force_time: str = "ms") -> dict:
    inputs = [{"name": "force", "path": "force.csv", "time_unit": force_time, "value_unit": "kN"},
              {"name": "disp", "path": "displacement.csv", "time_unit": "ms", "value_unit": "mm"}]
    result = service.curve_ops(inputs, operations)
    JobResult.model_validate(json.loads(json.dumps(result)), strict=False)
    job = json.loads((service.settings.workspace / "jobs" / result["job_id"] / "job.json").read_text("utf-8"))
    assert job["status"] == result["status"] and job["result"] == result  # the job record is final
    return result


def _files(result: dict) -> dict:
    return {a["metadata"]["curve"]: a["path"] for a in result["artifacts"]}


TENSILE = [{"op": "sae_filter", "input": "force", "cfc": 600, "output": "force_f"},
           {"op": "cross_plot", "x": "disp", "y": "force_f", "output": "fd"},
           {"op": "engineering_stress_strain", "input": "fd", "area": 20.0, "gauge_length": 50.0,
            "length_unit": "mm", "output": "eng"},
           {"op": "true_stress_strain", "input": "eng", "output": "true"}]


def test_force_displacement_to_true_stress_strain_with_sae_600(service: Service) -> None:
    result = _run(service, [*TENSILE, {"op": "convert_units", "input": "true", "value_unit": "MPa",
                                       "output": "true_mpa"}])
    assert result["status"] == "succeeded" and result["contract"] == "JobResult/v1"
    assert [(check["name"], check["status"]) for check in result["checks"]] == [
        ("inputs_unchanged", "passed"), ("artifacts_match_records", "passed")]
    steps = {s["output"]: s for s in result["data"]["steps"]}
    assert steps["force"]["operation"] == "history" and steps["force"]["input_file"]["sha256"]
    assert steps["force_f"]["parameters"]["cfc"] == 600 and steps["force_f"]["parameters"]["padding"] == "odd"
    assert "2.0775" in steps["force_f"]["formula"] and steps["force_f"]["units"] == {"t": "ms", "y": "kN"}
    assert steps["eng"]["units"] == {"t": "1", "y": "kN/mm^2"} and steps["true"]["formula"].startswith("sigma_t")
    assert steps["true_mpa"]["units"] == {"t": "1", "y": "MPa"} and steps["true_mpa"]["parameters"]["y_factor"] == 1000.0
    files = {a["metadata"]["curve"]: a for a in result["artifacts"]}
    assert sorted(files) == ["eng", "fd", "force_f", "true", "true_mpa"]
    for artifact in files.values():
        assert hashlib.sha256(Path(artifact["path"]).read_bytes()).hexdigest() == artifact["sha256"]
    header, eng = _read(files["eng"]["path"])
    _, true = _read(files["true_mpa"]["path"])
    assert header == ["engineering_strain", "engineering_stress"]
    assert np.allclose(true[:, 0], np.log1p(eng[:, 0])) and np.allclose(true[:, 1], 1000 * eng[:, 1] * (1 + eng[:, 0]))
    _, filtered = _read(files["force_f"]["path"])
    t = filtered[:, 0] / 1000
    smooth = 20.0 * np.sin(math.pi * t / 0.1)
    gain = 1 / (1 + (math.tan(math.pi * 3000 / FS) / math.tan(math.pi * 2.0775 * 600 / FS)) ** 4)
    middle = slice(200, 800)
    assert np.allclose(filtered[middle, 1], smooth[middle] + gain * 0.5 * np.sin(2 * math.pi * 3000 * t[middle]),
                       rtol=0, atol=1e-6)  # the 3 kHz ripple is attenuated as J211 predicts, in phase; hump kept
    assert len(result["warnings"]) == 1 and "after the maximum engineering stress" in result["warnings"][0]


def test_units_reach_the_stress_strain_formulas(service: Service) -> None:
    reference = _files(_run(service, TENSILE))
    metres = _run(service, [
        TENSILE[0], {"op": "convert_units", "input": "disp", "value_unit": "m", "output": "disp_m"},
        {"op": "cross_plot", "x": "disp_m", "y": "force_f", "output": "fd"},
        {"op": "engineering_stress_strain", "input": "fd", "area": 20e-6, "gauge_length": 0.05, "length_unit": "m",
         "output": "eng"},
        {"op": "convert_units", "input": "eng", "abscissa_unit": "%", "value_unit": "kN/mm^2", "output": "eng_pct"},
        {"op": "true_stress_strain", "input": "eng_pct", "output": "true"}])
    assert metres["status"] == "succeeded"
    _, expected = _read(reference["true"])
    _, got = _read(_files(metres)["true"])
    assert np.allclose(got, expected, rtol=1e-12, atol=1e-15)  # m and % change nothing in the true curve
    eng_pct = next(s for s in metres["data"]["steps"] if s["output"] == "eng_pct")
    assert eng_pct["units"] == {"t": "%", "y": "kN/mm^2"} and eng_pct["abscissa"] == "engineering_strain"


def test_spectrum_resample_and_calculus_steps(service: Service) -> None:
    result = _run(service, [
        {"op": "spectrum", "input": "force", "output": "spec"},
        {"op": "resample", "input": "disp", "dt": 0.5, "output": "coarse"},
        {"op": "differentiate", "input": "coarse", "output": "velocity"},
        {"op": "cross_plot", "x": "disp", "y": "force", "output": "fd"},
        {"op": "integrate", "input": "fd", "output": "work"},
        {"op": "butterworth_filter", "input": "force", "order": 4, "cutoff_hz": 1000.0, "output": "smooth"}])
    assert result["status"] == "succeeded"
    files = _files(result)
    header, spec = _read(files["spec"])
    high = spec[spec[:, 0] > 100]  # above the hump's own harmonics
    assert header == ["frequency", "amplitude"] and high[np.argmax(high[:, 1]), 0] == pytest.approx(3000.0)
    assert spec[300, 1] == pytest.approx(0.5, rel=1e-3)  # 3 kHz bin at 10 Hz resolution; the hump leaks 7e-5
    _, velocity = _read(files["velocity"])
    assert np.allclose(velocity[:, 1], 0.1)  # 10 mm in 100 ms
    steps = {s["output"]: s for s in result["data"]["steps"]}
    assert steps["velocity"]["units"] == {"t": "ms", "y": "mm/ms"} and steps["work"]["units"] == {"t": "mm", "y": "kN*mm"}
    assert steps["spec"]["units"] == {"t": "Hz", "y": "kN"} and steps["coarse"]["parameters"]["dt"] == 0.5
    assert result["warnings"] == ["coarse: resampled to a coarser step without low-pass filtering; content above "
                                  "the new Nyquist frequency aliases (filter first)"]


CROSS = {"op": "cross_plot", "x": "disp", "y": "force", "output": "fd"}
ENGINEERING = {"op": "engineering_stress_strain", "input": "fd", "area": 20.0, "gauge_length": 50.0,
               "length_unit": "mm", "output": "eng"}


@pytest.mark.parametrize(("operations", "message", "force_time"), [
    ([{"op": "sae_filter", "input": "force", "cfc": 600, "output": "s"},
      {"op": "spectrum", "input": "s", "output": "f"}, {"op": "sae_filter", "input": "f", "cfc": 60, "output": "g"}],
     "input must have the abscissa 'time'; 'f' has 'frequency'", "ms"),
    ([{"op": "true_stress_strain", "input": "force", "output": "t"}], "abscissa 'engineering_strain'", "ms"),
    ([CROSS, ENGINEERING, {"op": "differentiate", "input": "eng", "output": "slope"},
      {"op": "true_stress_strain", "input": "slope", "output": "t"}], "ordinate 'engineering_stress'", "ms"),
    ([{"op": "butterworth_filter", "input": "force", "order": 2, "cutoff_hz": 6000.0, "output": "b"}], "Nyquist",
     "ms"),
    ([CROSS, {**ENGINEERING, "area": -1.0}], "area must be positive", "ms"),
    ([CROSS], "convert one time axis", "s"),
])
def test_refused_steps_fail_the_job_with_the_step(service: Service, operations: list, message: str,
                                                  force_time: str) -> None:
    result = _run(service, operations, force_time)
    assert result["status"] == "failed" and message in result["error"]["message"]
    assert result["error"]["message"].startswith("operation ") and result["error"]["type"] == "CurveError"


def test_converted_time_axes_can_be_cross_plotted(service: Service) -> None:
    fixed = _run(service, [{"op": "convert_units", "input": "force", "abscissa_unit": "ms", "output": "f_ms"},
                           {"op": "cross_plot", "x": "disp", "y": "f_ms", "output": "fd"}], force_time="s")
    assert fixed["status"] == "succeeded"  # 0..99.9 "s" became 0..99900 ms; the common interval is disp's
    fd = next(s for s in fixed["data"]["steps"] if s["output"] == "fd")
    assert fd["parameters"]["interval"] == [0.0, pytest.approx(99.9)] and fd["parameters"]["t_unit"] == "ms"


def test_read_failures_and_changed_inputs_fail_the_job(service: Service, tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "short.csv").write_text("time,value\n0,1\n1\n", encoding="utf-8")  # a short row
    result = service.curve_ops([{"name": "s", "path": "short.csv", "time_unit": "s", "value_unit": "N"}],
                               [{"op": "differentiate", "input": "s", "output": "d"}])
    assert result["status"] == "failed" and result["error"]["type"] == "TypeError"
    job = json.loads((tmp_path / "jobs" / result["job_id"] / "job.json").read_text("utf-8"))
    assert job["status"] == "failed"
    write = tool._write

    def tamper(directory, name, curve):
        (tmp_path / "force.csv").write_text("time,value\n0,1\n1,2\n", encoding="utf-8")
        return write(directory, name, curve)

    monkeypatch.setattr(tool, "_write", tamper)
    changed = _run(service, [{"op": "differentiate", "input": "force", "output": "d"}])
    assert changed["status"] == "failed" and "changed" in changed["error"]["message"]
    assert [(check["name"], check["status"]) for check in changed["checks"]] == [
        ("inputs_unchanged", "failed"), ("artifacts_match_records", "passed")]


def test_malformed_requests_are_refused_before_a_job(service: Service, tmp_path: Path) -> None:
    good = {"name": "force", "path": "force.csv", "time_unit": "ms", "value_unit": "kN"}
    for inputs, operations, message in (
        ([good], [{"op": "fft", "input": "force", "output": "f"}], "'op' must be one of"),
        ([good], [{"op": ["resample"], "input": "force", "output": "f"}], "'op' must be one of"),
        ([good], [{"op": "resample", "input": "force", "output": "force", "dt": 1.0}], "new identifier"),
        ([good], [{"op": "resample", "input": "force", "output": "nul", "dt": 1.0}], "device name"),
        ([good], [{"op": "resample", "input": "other", "output": "r", "dt": 1.0}], "not defined"),
        ([good], [{"op": "resample", "input": ["force"], "output": "r", "dt": 1.0}], "not defined"),
        ([good], [{"op": "resample", "input": "force", "output": "r"}], "missing ['dt']"),
        ([good], [{"op": "resample", "input": "force", "output": "r", "dt": 1.0, "kind": "x"}], "unknown ['kind']"),
        ([{**good, "unit": "kN"}], [{"op": "spectrum", "input": "force", "output": "s"}], "Unknown input keys"),
        ([{**good, "path": "//server/share/force.csv"}], [{"op": "spectrum", "input": "force", "output": "s"}],
         "Network path"),
        ([], [{"op": "spectrum", "input": "force", "output": "s"}], "1..20"),
    ):
        with pytest.raises(ValueError, match=message.replace("[", r"\[").replace("]", r"\]")):
            service.curve_ops(inputs, operations)
    assert not (tmp_path / "jobs").exists()


def test_names_differing_only_in_case_are_refused_before_a_job(service: Service, tmp_path: Path) -> None:
    inputs = [{"name": "force", "path": "force.csv", "time_unit": "ms", "value_unit": "kN"}]
    for operations in ([{"op": "differentiate", "input": "force", "output": "Result"},  # Result.csv, then result.csv
                        {"op": "integrate", "input": "force", "output": "result"}],
                       [{"op": "differentiate", "input": "force", "output": "FORCE"}]):
        with pytest.raises(ValueError, match="differs only in case"):
            service.curve_ops(inputs, operations)
    assert not (tmp_path / "jobs").exists()
    result = _run(service, [{"op": "differentiate", "input": "force", "output": "Result"},
                            {"op": "integrate", "input": "force", "output": "result_2"}])
    assert result["status"] == "succeeded"
    for artifact in result["artifacts"]:  # every registered fingerprint still describes the file on disk
        assert hashlib.sha256(Path(artifact["path"]).read_bytes()).hexdigest() == artifact["sha256"]
    assert ("artifacts_match_records", "passed") in [(check["name"], check["status"]) for check in result["checks"]]


def test_an_overwritten_artifact_fails_the_job(service: Service, monkeypatch) -> None:
    write, written = tool._write, []

    def overwrite(directory, name, curve):
        artifact = write(directory, name, curve)
        written.append(artifact.path)
        Path(written[0]).write_text("time,value\n0,0\n1,1\n", encoding="utf-8")  # a later step clobbers the first
        return artifact

    monkeypatch.setattr(tool, "_write", overwrite)
    result = _run(service, [{"op": "differentiate", "input": "force", "output": "a"},
                            {"op": "integrate", "input": "force", "output": "b"}])
    assert result["status"] == "failed" and "a.csv" in result["error"]["message"]
    assert ("artifacts_match_records", "failed") in [(check["name"], check["status"]) for check in result["checks"]]


def test_curve_ops_is_a_registered_mcp_tool(service: Service) -> None:
    names = {t.name for t in asyncio.run(build_server(service.settings, "full").list_tools())}
    assert "curve_ops" in names
