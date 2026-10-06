"""Q07 curve operations against analytical solutions and hand calculations (L1)."""
import math

import numpy as np
import pytest

from ls_prepost_mcp.domain.results import curves as c

FS = 100_000.0  # Hz
T = np.arange(0, 0.2, 1 / FS)
MIDDLE = slice(T.size // 4, 3 * T.size // 4)  # 0.1 s: a whole number of periods for every test frequency


def _gain(filtered: np.ndarray) -> float:
    """Amplitude ratio of a unit sine after filtering, measured away from the ends."""
    return float(np.sqrt(2 * np.mean(filtered[MIDDLE] ** 2)))


def _sae_response(f: float, cfc: float) -> float:
    """Exact digital response of J211 App. C forward + backward: w_a = tan(pi f_d T), f_d = 2.0775 CFC."""
    return 1 / (1 + (math.tan(math.pi * f / FS) / math.tan(math.pi * 2.0775 * cfc / FS)) ** 4)


def test_calculus_carries_units() -> None:
    t = np.linspace(0, 2 * math.pi, 4001)
    slope = c.differentiate(t, np.sin(t), t_unit="ms", y_unit="mm")
    assert np.allclose(slope.y, np.cos(t), atol=2e-6) and slope.meta["units"] == {"t": "ms", "y": "mm/ms"}
    area = c.integrate(t, np.cos(t), 1.5, t_unit="ms", y_unit="kN")
    assert np.allclose(area.y, 1.5 + np.sin(t), atol=1e-6) and area.meta["units"] == {"t": "ms", "y": "kN*ms"}
    assert area.meta["parameters"] == {"initial": 1.5}
    assert c.differentiate([0, 1], [0, 2]).meta["units"] == {"t": None, "y": None}  # undeclared stays undeclared
    assert c.differentiate([0, 1], [0, 2], t_unit="mm/ms", y_unit="kN").meta["units"]["y"] == "kN/mm*ms"


def test_resample_onto_a_uniform_grid() -> None:
    curve = c.resample([0.0, 1.0, 3.0], [0.0, 2.0, 6.0], 0.5, t_unit="s", y_unit="N")
    assert curve.t.tolist() == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0] and np.allclose(curve.y, 2 * curve.t)
    assert curve.meta["operation"] == "resample" and curve.meta["units"] == {"t": "s", "y": "N"}
    assert curve.meta["parameters"] == {"dt": 0.5, "start": 0.0, "samples": 7, "dropped_tail": 0.0,
                                        "coarser_than_input": False}
    short = c.resample([1.0, 2.0, 3.2], [1.0, 1.0, 2.2], 0.5)  # 3.2 is not on the grid: dropped, reported
    assert short.t.tolist() == [1.0, 1.5, 2.0, 2.5, 3.0] and short.y[-1] == pytest.approx(2.0)
    assert short.meta["parameters"]["dropped_tail"] == pytest.approx(0.2)
    coarse = c.resample(T, np.sin(2 * math.pi * 50 * T), 1e-4)  # the grid never leaves the record
    assert coarse.t[-1] <= T[-1] and np.allclose(np.diff(coarse.t), 1e-4)
    assert coarse.meta["parameters"]["coarser_than_input"]  # no low-pass: may alias, reported
    assert c.resample([0.0, 999_999.0], [0.0, 1.0], 1.0).t.size == c.MAX_SAMPLES  # the limit itself is allowed


@pytest.mark.parametrize(("t", "message"), [([0.0, 1.0, 1.0, 2.0], "sample 2 repeats 1"),
                                            ([0.0, 2.0, 1.0], "sample 2 goes back to 1"),
                                            ([0.0, float("nan"), 1.0], "finite")])
def test_resample_refuses_disordered_time(t: list, message: str) -> None:
    with pytest.raises(c.CurveError, match=message):
        c.resample(t, np.zeros(len(t)), 0.1)


def test_resample_refuses_bad_steps() -> None:
    for dt, message in ((0.0, "positive"), (-1.0, "positive"), (5.0, "longer than the record"),
                        (1e-9, "more than"), (True, "finite number"), (10 ** 400, "finite number")):
        with pytest.raises(c.CurveError, match=message):
            c.resample([0.0, 1.0, 2.0], [0.0, 1.0, 2.0], dt)


@pytest.mark.parametrize("cfc", [60.0, 180.0, 600.0, 1000.0])
def test_sae_filter_attenuation_and_phase(cfc: float) -> None:
    flat = c.sae_filter(T, np.full(T.size, 3.0), cfc, t_unit="s", y_unit="m/s^2")
    assert np.allclose(flat.y, 3.0) and flat.meta["units"] == {"t": "s", "y": "m/s^2"}  # DC passes, ends included
    for f in (cfc, 10 * cfc):
        sine = np.sin(2 * math.pi * f * T)
        filtered = c.sae_filter(T, sine, cfc, t_unit="s").y
        assert _gain(filtered) == pytest.approx(_sae_response(f, cfc), rel=1e-6, abs=1e-9)
        if f == cfc:  # phaseless: the passed sine is the input scaled, not shifted
            assert np.allclose(filtered[MIDDLE], sine[MIDDLE] * _gain(filtered), rtol=0, atol=1e-9)
            assert -1.0 < 20 * math.log10(_gain(filtered)) < 0.5  # J211 corridor at the CFC: +0.5 / -1 dB
    parameters = c.sae_filter(T, np.zeros(T.size), cfc, t_unit="s").meta["parameters"]
    assert parameters["standard_class"] and parameters["design_frequency_hz"] == pytest.approx(2.0775 * cfc)


def test_sae_coefficients_and_result_match_an_independent_reference() -> None:
    signal = pytest.importorskip("scipy.signal")
    noisy = np.sin(2 * math.pi * 300 * T) + 0.5 * np.sin(2 * math.pi * 7000 * T) + 40 * T
    for cfc in (60.0, 600.0):
        ours = c.sae_filter(T, noisy, cfc, t_unit="s")
        b, a = signal.butter(2, 2.0775 * cfc, fs=FS)  # 2-pole Butterworth, bilinear, pre-warped at f_d
        k = ours.meta["parameters"]["coefficients"]
        assert np.allclose([k["a0"], k["a1"], k["a2"]], b, rtol=1e-12)
        assert np.allclose([k["b1"], k["b2"]], -a[1:], rtol=1e-12)  # J211 writes the feedback with + signs
        pad = ours.meta["parameters"]["padding_samples"]
        assert np.allclose(ours.y, signal.filtfilt(b, a, noisy, padtype="odd", padlen=pad), rtol=0, atol=1e-10)
    for order in (1, 4, 7):
        ours = c.butterworth_filter(T, noisy, order, 800.0, t_unit="s")
        sos = signal.butter(order, 800.0, fs=FS, output="sos")
        pad = ours.meta["parameters"]["padding_samples"]
        assert np.allclose(ours.y, signal.sosfiltfilt(sos, noisy, padtype="odd", padlen=pad), rtol=0, atol=1e-9)


def test_sae_filter_needs_the_time_unit_and_scales_with_it() -> None:
    signal = np.sin(2 * math.pi * 1000 * T) + 0.3 * np.sin(2 * math.pi * 9000 * T)
    in_seconds = c.sae_filter(T, signal, 600, t_unit="s")
    in_ms = c.sae_filter(T * 1000, signal, 600, t_unit="ms")
    assert np.allclose(in_seconds.y, in_ms.y, rtol=0, atol=1e-12)
    assert in_ms.meta["parameters"]["sampling_rate_hz"] == pytest.approx(FS)
    with pytest.raises(c.CurveError, match="declare the time unit"):
        c.sae_filter(T, signal, 600, t_unit=None)
    with pytest.raises(c.CurveError, match="not a time unit"):
        c.sae_filter(T, signal, 600, t_unit="mm")
    with pytest.raises(c.CurveError, match="Nyquist"):  # 100 Hz sampling cannot carry a 125 Hz design frequency
        c.sae_filter(T * 1000, signal, 60, t_unit="s")


def test_padding_conventions_at_the_ends() -> None:
    ramp = 3.0 + 50.0 * T
    odd = c.sae_filter(T, ramp, 60, t_unit="s")
    assert np.allclose(odd.y, ramp, rtol=0, atol=1e-6)  # point reflection passes a straight line unchanged
    assert odd.meta["parameters"]["padding"] == "odd" and odd.meta["parameters"]["padding_complete"]
    held = c.sae_filter(T, ramp, 60, t_unit="s", padding="constant")
    assert np.allclose(held.y[MIDDLE], ramp[MIDDLE], rtol=0, atol=1e-6) and abs(held.y[0] - ramp[0]) > 0.01
    assert held.meta["parameters"]["padding_samples"] == 0 and held.meta["parameters"]["padding_complete"] is None
    short = c.butterworth_filter(T[:50], ramp[:50], 2, 100.0, t_unit="s")
    assert short.meta["parameters"]["padding_samples"] == 49 and not short.meta["parameters"]["padding_complete"]
    with pytest.raises(c.CurveError, match="padding"):
        c.sae_filter(T, ramp, 60, t_unit="s", padding="zero")


def test_padding_length_follows_the_digital_poles_near_nyquist() -> None:
    fs, cutoff = 1000.0, 490.0
    t = np.arange(1000) / fs
    ramp = 2.0 + 3.0 * t
    warped = math.tan(math.pi * cutoff / fs)  # analog poles over 2 fs, then the bilinear map z = (1 + s) / (1 - s)
    poles = [warped * np.exp(1j * math.pi * (2 * k + 3) / 4) for k in range(2)]
    radius = max(abs((1 + p) / (1 - p)) for p in poles)
    assert radius == pytest.approx(0.95654, abs=1e-5)
    needed = math.ceil(math.log(1e6) / -math.log(radius))  # 311 samples for the transient to fall by 1e-6
    full = c.butterworth_filter(t, ramp, 2, cutoff, t_unit="s")
    assert full.meta["parameters"]["padding_samples"] == needed and full.meta["parameters"]["padding_complete"]
    assert np.allclose(full.y, ramp, rtol=0, atol=1e-5)  # the ends have settled: a straight line passes
    short = c.butterworth_filter(t[:50], ramp[:50], 2, cutoff, t_unit="s")
    assert short.meta["parameters"]["padding_samples"] == 49 and short.meta["parameters"]["padding_complete"] is False
    sae = c.sae_filter(t, ramp, 230.0, t_unit="s")  # design frequency 477.8 Hz, close to the 500 Hz Nyquist
    assert sae.meta["parameters"]["padding_complete"] and np.allclose(sae.y, ramp, rtol=0, atol=1e-5)


@pytest.mark.parametrize("order", [1, 2, 4, 5])
def test_butterworth_zero_phase_gain(order: int) -> None:
    cutoff = 500.0
    for ratio in (0.2, 1.0, 5.0):
        f = ratio * cutoff
        signal = np.sin(2 * math.pi * f * T)
        filtered = c.butterworth_filter(T, signal, order, cutoff, t_unit="s").y
        warped = math.tan(math.pi * f / FS) / math.tan(math.pi * cutoff / FS)  # exact: pre-warped at the cutoff
        assert _gain(filtered) == pytest.approx(1 / (1 + warped ** (2 * order)), rel=1e-6, abs=1e-9)
        if ratio == 0.2:  # zero phase: the passed sine is not shifted
            assert np.allclose(filtered[MIDDLE], signal[MIDDLE] * _gain(filtered), rtol=0, atol=1e-9)
    ramp = c.butterworth_filter(T, 1.0 - 20.0 * T, order, cutoff, t_unit="s", y_unit="kN")
    assert np.allclose(ramp.y, 1.0 - 20.0 * T, rtol=0, atol=1e-6) and ramp.meta["units"]["y"] == "kN"


def test_spectrum_frequency_axis_and_amplitudes() -> None:
    t = np.arange(0, 1, 1 / 1000.0)
    spec = c.spectrum(t, 0.5 + 2.0 * np.sin(2 * math.pi * 50 * t) + 0.25 * np.cos(math.pi * 1000 * t),
                      t_unit="s", y_unit="kN")
    assert spec.y[0] == pytest.approx(0.5) and spec.t[np.argmax(spec.y[1:]) + 1] == 50.0
    assert spec.y[50] == pytest.approx(2.0, rel=1e-9) and spec.y[-1] == pytest.approx(0.25, rel=1e-9)  # Nyquist
    assert spec.t[-1] == 500.0 and spec.meta["units"] == {"t": "Hz", "y": "kN"}
    assert spec.meta["parameters"]["resolution_hz"] == pytest.approx(1.0)
    odd = np.arange(999) / 1000.0  # odd N: no Nyquist bin, every bin above 0 doubled
    spec = c.spectrum(odd, 0.5 + 2.0 * np.sin(2 * math.pi * 37 * np.arange(999) / 999), t_unit="s")
    assert spec.t.size == 500 and spec.y[0] == pytest.approx(0.5) and spec.y[37] == pytest.approx(2.0, rel=1e-9)
    assert spec.t[37] == pytest.approx(37 * 1000 / 999)
    in_ms = c.spectrum(t * 1000, np.sin(2 * math.pi * 50 * t), t_unit="ms")
    assert in_ms.t[np.argmax(in_ms.y)] == pytest.approx(50.0)  # Hz, whatever the time unit


def test_frequency_operations_refuse_non_uniform_sampling() -> None:
    uneven = [0.0, 0.1, 0.3, 0.4]
    for operation in (lambda: c.sae_filter(uneven, [0, 1, 2, 3], 60, t_unit="s"),
                      lambda: c.butterworth_filter(uneven, [0, 1, 2, 3], 2, 1.0, t_unit="s"),
                      lambda: c.spectrum(uneven, [0, 1, 2, 3], t_unit="s")):
        with pytest.raises(c.CurveError, match="resample"):
            operation()
    with pytest.raises(c.CurveError, match="Nyquist"):
        c.butterworth_filter(T, np.sin(T), 2, FS, t_unit="s")
    for order in (17, 0, 2.0, True):
        with pytest.raises(c.CurveError, match="1..16"):
            c.butterworth_filter(T, np.sin(T), order, 100, t_unit="s")


def test_cross_plot_aligns_on_the_common_interval() -> None:
    plot = c.cross_plot([0, 1, 2, 3], [0, 10, 20, 30], [0.5, 1.5, 2.5], [1, 3, 5], t_unit="ms",
                        x_unit="mm", y_unit="kN")
    assert plot.t.tolist() == [5.0, 10.0, 15.0, 20.0, 25.0] and plot.y.tolist() == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert plot.meta["units"] == {"t": "mm", "y": "kN"} and plot.meta["parameters"]["interval"] == [0.5, 2.5]
    loop = c.cross_plot([0, 1, 2], [0, 1, 0], [0, 1, 2], [0, 5, 0])  # unloading: x need not be monotonic
    assert loop.t.tolist() == [0.0, 1.0, 0.0] and loop.y.tolist() == [0.0, 5.0, 0.0]
    for ty in ([5, 6], [3, 4]):  # disjoint, or touching in a single instant
        with pytest.raises(c.CurveError, match="do not overlap"):
            c.cross_plot([0, 1, 2, 3], [0, 1, 2, 3], ty, [1, 2])


def test_engineering_and_true_stress_strain_by_hand() -> None:
    eng = c.engineering_stress_strain([0.0, 0.5, 1.0, 1.5], [0.0, 1000.0, 2000.0, 1500.0], 10.0, 50.0,
                                      displacement_unit="mm", force_unit="N", length_unit="mm")
    assert np.allclose(eng.t, [0.0, 0.01, 0.02, 0.03]) and np.allclose(eng.y, [0.0, 100.0, 200.0, 150.0])
    assert eng.meta["units"] == {"t": "1", "y": "N/mm^2"} and eng.meta["parameters"]["assumption"] is None
    true = c.true_stress_strain(eng.t, eng.y, stress_unit=eng.meta["units"]["y"])
    assert np.allclose(true.t, [0.0, math.log(1.01), math.log(1.02), math.log(1.03)], rtol=1e-12, atol=0)
    assert np.allclose(true.y, [0.0, 101.0, 204.0, 154.5]) and true.meta["units"] == {"t": "1", "y": "N/mm^2"}
    assert true.meta["parameters"]["maximum_engineering_stress"] == {
        "index": 2, "engineering_strain": 0.02, "engineering_stress": 200.0, "samples_after": 1}
    percent = c.true_stress_strain([0.0, 1.0, 2.0, 3.0], eng.y, strain_unit="%")  # the same curve in percent
    assert np.allclose(percent.t, true.t, rtol=1e-12) and np.allclose(percent.y, true.y, rtol=1e-12)
    in_metres = c.engineering_stress_strain([0.0, 0.0005, 0.001, 0.0015], [0.0, 1.0, 2.0, 1.5], 10.0, 50.0,
                                            displacement_unit="m", force_unit="kN", length_unit="mm")
    assert np.allclose(in_metres.t, eng.t, rtol=1e-12) and in_metres.meta["parameters"]["displacement_factor"] == 1000
    assert in_metres.meta["units"]["y"] == "kN/mm^2"
    compression = c.true_stress_strain([0.0, -0.1, -0.5], [0.5, -100.0, -300.0])  # positive noise at the start
    assert compression.t[2] == pytest.approx(math.log(0.5)) and compression.y[2] == pytest.approx(-150.0)
    assert compression.meta["parameters"]["maximum_engineering_stress"] is None


def test_stress_strain_refusals() -> None:
    for strain, message in (([0.0, -1.0], "exceed -1"), ([0.0, -100.0], "exceed -1")):
        with pytest.raises(c.CurveError, match=message):
            c.true_stress_strain(strain, [0.0, 10.0], strain_unit="%" if strain[1] == -100.0 else "1")
    for unit, message in (("mm", "not a strain unit"), (None, "Declare the strain unit")):
        with pytest.raises(c.CurveError, match=message):
            c.true_stress_strain([0.0, 0.1], [0.0, 10.0], strain_unit=unit)
    for units, message in ((("N", "N", "mm"), "not a length unit"), (("mm", "mm", "mm"), "not a force unit"),
                           (("mm", "N", "mm^2"), "one length unit"), (("mm", "N", None), "together")):
        with pytest.raises(c.CurveError, match=message):
            c.engineering_stress_strain([0, 1], [0, 1], 1.0, 1.0, displacement_unit=units[0], force_unit=units[1],
                                        length_unit=units[2])
    with pytest.raises(c.CurveError, match="area must be positive"):
        c.engineering_stress_strain([0, 1], [0, 1], 0.0, 1.0)
    assert "undeclared" in c.engineering_stress_strain([0, 1], [0, 1], 1.0, 1.0).meta["parameters"]["assumption"]


def test_unit_conversion_and_declared_histories() -> None:
    curve = c.convert_units([0.0, 1.0, 2.0], [0.0, 1.5, 3.0], t_unit="ms", y_unit="kN", to_t_unit="s",
                            to_y_unit="N")
    assert np.allclose(curve.t, [0.0, 0.001, 0.002]) and np.allclose(curve.y, [0.0, 1500.0, 3000.0])
    assert curve.meta["units"] == {"t": "s", "y": "N"} and curve.meta["parameters"]["y_factor"] == 1000.0
    assert curve.meta["parameters"]["from_units"] == ["ms", "kN"]
    with pytest.raises(c.CurveError, match="Incompatible"):
        c.convert_units([0, 1], [0, 1], t_unit="ms", y_unit="kN", to_y_unit="mm")
    with pytest.raises(c.CurveError, match="declared unit"):
        c.convert_units([0, 1], [0, 1], t_unit=None, y_unit="kN", to_t_unit="s")
    with pytest.raises(c.CurveError, match="underflow"):
        c.convert_units([0, 1], [0, 1e-320], t_unit="s", y_unit="N", to_y_unit="MN")
    history = c.history([0, 1], [2, 3], t_unit="us", y_unit="mm", path="x.csv")
    assert history.meta["units"] == {"t": "us", "y": "mm"} and history.meta["parameters"] == {"path": "x.csv"}
    with pytest.raises(c.CurveError, match="value unit"):
        c.history([0, 1], [2, 3], t_unit="s", y_unit=None)
    with pytest.raises(c.CurveError, match="numeric"):
        c.history(["a", "b"], [2, 3], t_unit="s", y_unit="N")
