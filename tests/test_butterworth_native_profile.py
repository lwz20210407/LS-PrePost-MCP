"""Q07: native BW is an explicit numerical profile, independently observed at the tool boundary."""
import json
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.domain.results.curves import CurveError, butterworth_filter


def test_native_butterworth_matches_independent_native_short_record():
    reference = json.loads((Path(__file__).parent / "data/butterworth_native_reference.json").read_text())
    times = np.arange(len(reference["input_values"])) * reference["dt_seconds"]
    expected = np.asarray(reference["native_values"])
    got = butterworth_filter(times, reference["input_values"], 2, reference["cutoff_hz"],
                             t_unit="s", convention="lsprepost")
    np.testing.assert_allclose(got.y, expected, rtol=reference["rtol"],
                               atol=reference["atol_scale"] * np.max(np.abs(expected)))
    parameters = got.meta["parameters"]
    assert parameters["convention"] == "lsprepost"
    assert parameters["design_frequency_hz"] == 750
    assert parameters["reflection_samples"] == 3


@pytest.mark.parametrize("time_unit,scale", [("s", 1), ("ms", 1000)])
def test_native_butterworth_preserves_dc_and_declared_units(time_unit, scale):
    times = np.arange(1001) * .00005 * scale
    values = np.full(times.size, 17.25)
    got = butterworth_filter(times, values, 2, 600, t_unit=time_unit, y_unit="kN",
                             convention="lsprepost")
    np.testing.assert_array_equal(got.y, values)
    np.testing.assert_array_equal(got.t, times)
    assert got.meta["units"] == {"t": time_unit, "y": "kN"}


def test_native_profile_does_not_change_standard_butterworth_default():
    t = np.arange(1001) * .0001
    y = 3 * t + np.sin(2 * np.pi * 12 * t)
    np.testing.assert_array_equal(butterworth_filter(t, y, 4, 600, t_unit="s").y,
                                  butterworth_filter(t, y, 4, 600, t_unit="s", convention="standard").y)


@pytest.mark.parametrize("parameters,reason", [
    ({"order": 4}, "order 2"),
    ({"padding": "odd"}, "initialization"),
    ({"padding": "constant"}, "initialization"),
    ({"cutoff_hz": 8000}, "Nyquist"),
])
def test_native_butterworth_refuses_unsupported_numerical_contract(parameters, reason):
    settings = dict(order=2, cutoff_hz=600, t_unit="s", convention="lsprepost")
    settings.update(parameters)
    with pytest.raises(CurveError, match=reason):
        butterworth_filter(np.arange(1001) * .00005, np.ones(1001), **settings)


def test_native_butterworth_refuses_an_unsafe_short_reflection_record():
    with pytest.raises(CurveError, match="reflection"):
        butterworth_filter(np.arange(10) * .00005, np.ones(10), 2, 60,
                          t_unit="s", convention="lsprepost")


@pytest.mark.parametrize("kind", ["clock_collapse", "underflow", "endpoint_overflow"])
def test_native_butterworth_refuses_lossy_native_storage(kind):
    t = np.arange(1001) * .00005
    y = np.ones(t.size)
    if kind == "clock_collapse":
        t = 2**20 + np.arange(1001) / 1024
    elif kind == "underflow":
        y[:] = 1e-100
    else:
        y[:] = 2e38
    with pytest.raises(CurveError, match="float32|underflow|overflow"):
        butterworth_filter(t, y, 2, 60, t_unit="s", convention="lsprepost")


def test_native_butterworth_is_exposed_through_curve_ops(tmp_path):
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.service import Service

    source = tmp_path / "constant.csv"
    source.write_text("time,value\n" + "".join(f"{i*.0001},17.25\n" for i in range(101)))
    result = Service(Settings(tmp_path / "jobs", allowed_roots=(tmp_path,))).curve_ops(
        [dict(name="a", path=str(source), time_unit="s", value_unit="kN")],
        [dict(op="butterworth_filter", input="a", output="filtered", order=2,
              cutoff_hz=600, convention="lsprepost")])
    assert result["status"] == "succeeded", result.get("error")
    assert result["data"]["steps"][-1]["parameters"]["convention"] == "lsprepost"
