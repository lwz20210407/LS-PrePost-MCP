"""Q07 relative histories: explicit alignment, declared units and analytical values."""
import hashlib
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.domain.results import curves as cv
from ls_prepost_mcp.engineering import read_curve
from ls_prepost_mcp.service import Service


def test_difference_matches_analytic_displacement_and_preserves_inputs():
    t = np.linspace(0., 2., 21)
    a, b = 3 * t + 2, t - 1
    before = (t.copy(), a.copy(), b.copy())
    result = cv.difference(t, a, t, b, t_unit="ms", y_unit="mm")
    np.testing.assert_allclose(result.y, 2 * t + 3)
    np.testing.assert_array_equal(result.t, t)
    assert result.meta["formula"] == "a(t) - b(t)"
    assert result.meta["parameters"]["alignment"] == "exact"
    assert result.meta["units"] == {"t": "ms", "y": "mm"}
    for actual, original in zip((t, a, b), before):
        np.testing.assert_array_equal(actual, original)


def test_difference_interpolates_only_with_explicit_common_interval_policy():
    a_times = np.array([0., 1., 3.])
    b_times = np.array([.5, 2., 4.])
    result = cv.difference(a_times, 3 * a_times + 2, b_times, b_times - 1,
                           alignment="intersection", t_unit="s", y_unit="N")
    np.testing.assert_array_equal(result.t, [.5, 1., 2., 3.])
    np.testing.assert_allclose(result.y, 2 * result.t + 3)
    assert result.meta["parameters"]["interval"] == [.5, 3.]
    assert "no extrapolation" in result.meta["parameters"]["interpolation"]


@pytest.mark.parametrize("times", [[0., 1., 3.], [0., 1., 2. + 1e-14]])
def test_different_clocks_are_not_silently_interpolated(times):
    with pytest.raises(cv.CurveError, match="exact.*convert|exact.*resample|exact.*intersection"):
        cv.difference([0., 1., 2.], [1., 2., 3.], times, [1., 2., 3.])


@pytest.mark.parametrize("alignment", ["automatic", "union", "", None, True])
def test_bad_alignment_is_rejected(alignment):
    with pytest.raises(cv.CurveError, match="alignment"):
        cv.difference([0., 1.], [1., 2.], [0., 1.], [1., 2.], alignment=alignment)


@pytest.mark.parametrize("times,values", [([1., 0.], [1., 2.]), ([0., 0.], [1., 2.]),
    ([0., float("nan")], [1., 2.]), ([0., 1.], [1., float("inf")]), ([0., 1.], [1.])])
def test_invalid_reference_history_is_rejected(times, values):
    with pytest.raises(cv.CurveError):
        cv.difference([0., 1.], [1., 2.], times, values, alignment="intersection")


@pytest.mark.parametrize("times", [[2., 3.], [1., 2.]])
def test_no_extrapolation_or_single_point_intersection(times):
    with pytest.raises(cv.CurveError, match="overlap"):
        cv.difference([0., 1.], [1., 2.], times, [1., 2.], alignment="intersection")


def test_derived_overflow_is_rejected():
    with pytest.raises(cv.CurveError, match="overflow|finite"):
        cv.difference([0., 1.], [1e308, 1e308], [0., 1.], [-1e308, -1e308])


def test_aligned_union_cannot_exceed_shared_sample_bound(monkeypatch):
    monkeypatch.setattr(cv, "MAX_SAMPLES", 3)
    with pytest.raises(cv.CurveError, match="aligned curve exceeds"):
        cv.difference([0., 1., 3.], [0., 1., 3.], [.5, 2., 4.], [.5, 2., 4.], alignment="intersection")


def _input(tmp_path, name, values, time_unit="s", value_unit="mm", times=(0, 1, 2)):
    path = tmp_path / (name + ".csv")
    path.write_text("time,value\n" + "".join(f"{t},{y}\n" for t, y in zip(times, values)), encoding="ascii")
    return dict(name=name, path=str(path), time_unit=time_unit, value_unit=value_unit)


def test_public_pipeline_relative_displacement_force_and_stress_strain(tmp_path):
    inputs = [_input(tmp_path, "moving", [0, 1, 2]), _input(tmp_path, "base", [0, .2, .4]),
              _input(tmp_path, "force", [0, 8, 16], value_unit="N")]
    identities = {item["path"]: hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() for item in inputs}
    service = Service(Settings(tmp_path / "jobs", allowed_roots=(tmp_path,)))
    result = JobResult.model_validate(service.curve_ops(inputs, [
        dict(op="difference", a="moving", b="base", output="relative"),
        dict(op="cross_plot", x="relative", y="force", output="force_displacement"),
        dict(op="engineering_stress_strain", input="force_displacement", output="stress_strain",
             area=2., gauge_length=10., length_unit="mm"),
    ]))
    assert result.status == "succeeded", result.error
    assert len(result.artifacts) == 3
    artifact = next(a for a in result.artifacts if a.metadata["curve"] == "stress_strain")
    strain, stress = read_curve(Path(artifact.path), "engineering_strain", "engineering_stress")
    np.testing.assert_allclose(strain, [0., .08, .16])
    np.testing.assert_allclose(stress, [0., 4., 8.])
    step = next(s for s in result.data["steps"] if s["output"] == "relative")
    assert step["inputs"] == {"a": "moving", "b": "base"}
    assert step["formula"] == "a(t) - b(t)"
    assert step["parameters"]["alignment"] == "exact"
    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha for path, sha in identities.items())


@pytest.mark.parametrize("time_unit,value_unit", [("ms", "mm"), ("s", "m"), ("s", "N")])
def test_public_difference_requires_explicit_unit_conversion(tmp_path, time_unit, value_unit):
    inputs = [_input(tmp_path, "a", [0, 1, 2]),
              _input(tmp_path, "b", [0, 1, 2], time_unit=time_unit, value_unit=value_unit)]
    result = Service(Settings(tmp_path / "jobs", allowed_roots=(tmp_path,))).curve_ops(
        inputs, [dict(op="difference", a="a", b="b", output="relative")])
    assert result["status"] == "failed"
    assert "convert_units" in result["error"]["message"]
    assert not result["artifacts"]


def test_public_difference_after_explicit_unit_conversion(tmp_path):
    inputs = [_input(tmp_path, "a", [0, 2, 4]),
              _input(tmp_path, "b", [0, .001, .002], time_unit="ms", value_unit="m", times=(0, 1000, 2000))]
    result = JobResult.model_validate(Service(Settings(tmp_path / "jobs", allowed_roots=(tmp_path,))).curve_ops(
        inputs, [dict(op="convert_units", input="b", output="b_converted", abscissa_unit="s", value_unit="mm"),
                 dict(op="difference", a="a", b="b_converted", output="relative")]))
    assert result.status == "succeeded", result.error
    artifact = next(a for a in result.artifacts if a.metadata["curve"] == "relative")
    times, values = read_curve(Path(artifact.path))
    np.testing.assert_array_equal(times, [0., 1., 2.])
    np.testing.assert_allclose(values, [0., 1., 2.])


def test_public_intersection_records_actual_interpolation_policy(tmp_path):
    inputs = [_input(tmp_path, "a", [2, 5, 11], times=(0, 1, 3)),
              _input(tmp_path, "b", [-.5, 1, 3], times=(.5, 2, 4))]
    result = JobResult.model_validate(Service(Settings(tmp_path / "jobs", allowed_roots=(tmp_path,))).curve_ops(
        inputs, [dict(op="difference", a="a", b="b", output="relative", alignment="intersection")]))
    assert result.status == "succeeded", result.error
    times, values = read_curve(Path(result.artifacts[0].path))
    np.testing.assert_array_equal(times, [.5, 1., 2., 3.])
    np.testing.assert_allclose(values, 2 * times + 3)
    parameters = result.data["steps"][-1]["parameters"]
    assert parameters["alignment"] == "intersection"
    assert parameters["interval"] == [.5, 3.]
    assert "no extrapolation" in parameters["interpolation"]
