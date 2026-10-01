import csv
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.units import Unit, curve_conversion


@pytest.mark.parametrize(
    "source,target,factor",
    [
        ("N/mm^2", "MPa", 1),
        ("N*mm", "J", 0.001),
        ("mm/ms^2", "m/s^2", 1000),
        ("g/cm^3", "kg/m^3", 1000),
        ("tonne*mm/ms^2", "MN", 1),
        ("microstrain", "%", 0.0001),
        ("µm", "mm", 0.001),
    ],
)
def test_explicit_mechanical_unit_algebra(source, target, factor):
    assert Unit.parse(source).factor_to(Unit.parse(target)) == factor


@pytest.mark.parametrize(
    "unit",
    [
        "m m",
        "N/(mm^2)",
        "__import__('os')",
        "C",
        "MPa^7",
        "N//m",
        "model_stress",
        "m^6*m^6*m^6*m^6*m^6*m^6*m^6*m^6*m^6",
    ],
)
def test_unsupported_or_ambiguous_units_are_never_guessed(unit):
    with pytest.raises(ValueError):
        Unit.parse(unit)


def write_curve(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["time", "value"])
        writer.writerows(rows)
    return str(path)


def output_rows(result):
    with Path(result["artifacts"][0]["path"]).open(newline="") as stream:
        return np.asarray([[float(v) for v in row] for row in list(csv.reader(stream))[1:]])


def test_scalar_conversion_preserves_source_and_reports_exact_scale(tmp_path):
    path = tmp_path / "mm.csv"
    write_curve(path, [(0, 0), (1000, 1000), (2000, 2000)])
    original = path.read_bytes()
    service = Service(Settings(tmp_path))
    result = service.convert_history_units(str(path), "mm", "m", "ms", "s")
    assert result["status"] == "succeeded"
    assert np.array_equal(output_rows(result), [[0, 0], [1, 1], [2, 2]])
    assert path.read_bytes() == original
    assert result["data"]["unit_contract"]["exact_value_factor"] == dict(numerator="1", denominator="1000")
    assert not result["data"]["unit_contract"]["source_unit_labels_verified"]


def test_declared_units_are_converted_before_alignment_and_difference(tmp_path):
    paths = [
        write_curve(tmp_path / "a.csv", [(0, 0), (1, 1), (2, 2)]),
        write_curve(tmp_path / "b.csv", [(0, 0), (0.001, 0.05), (0.002, 0.1)]),
    ]
    service = Service(Settings(tmp_path))
    result = service.combine_history_curves(
        paths, "difference", "mm", [dict(time="ms", value="mm"), dict(time="s", value="cm")], "ms"
    )
    assert result["status"] == "succeeded", result
    assert np.allclose(output_rows(result), [[0, 0], [1, 0.5], [2, 1]])
    assert result["data"]["unit_contract"]["dimensional_compatibility_checked"]


def test_legacy_shared_units_are_an_explicit_assumption(tmp_path):
    paths = [
        write_curve(tmp_path / "a.csv", [(0, 1), (1, 2)]),
        write_curve(tmp_path / "b.csv", [(0, 2), (1, 4)]),
    ]
    result = Service(Settings(tmp_path)).combine_history_curves(paths, "sum", "unknown_model_unit")
    assert result["status"] == "succeeded"
    assert result["data"]["unit_contract"]["mode"] == "assumed_shared"
    assert not result["data"]["unit_contract"]["dimensional_compatibility_checked"]


def test_incompatible_value_or_non_time_axis_rejected_before_file_access(tmp_path):
    service = Service(Settings(tmp_path))
    with pytest.raises(ValueError, match="dimensions"):
        service.convert_history_units("missing", "N", "MPa", "s", "s")
    with pytest.raises(ValueError, match="time dimensions"):
        curve_conversion("mm", "N", "m", "kN")
    assert not (tmp_path / "jobs").exists()


@pytest.mark.parametrize("value,source,target", [(1e-320, "Pa", "GPa"), (1e308, "m", "um")])
def test_nonfinite_and_underflow_conversions_fail_without_fabricating_zero(tmp_path, value, source, target):
    path = write_curve(tmp_path / "curve.csv", [(0, value), (1, value)])
    result = Service(Settings(tmp_path)).convert_history_units(path, source, target, "s", "s")
    assert result["status"] == "failed" and not result["artifacts"]
    assert not Path(result["job_directory"], "curve.csv").exists()
