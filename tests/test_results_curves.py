"""Q07 curve operations against analytical solutions (L1)."""
import math

import numpy as np
import pytest

from ls_prepost_mcp.domain.results import curves as c

FS = 100_000.0  # Hz
T = np.arange(0, 0.2, 1 / FS)


def _gain(filtered: np.ndarray, frequency: float) -> float:
    """Amplitude ratio of a unit sine after filtering, measured away from the ends."""
    middle = slice(T.size // 4, 3 * T.size // 4)
    return float(np.sqrt(2 * np.mean(filtered[middle] ** 2)))


def test_calculus_and_resampling() -> None:
    t = np.linspace(0, 2 * math.pi, 4001)
    assert np.allclose(c.differentiate(t, np.sin(t)).y, np.cos(t), atol=2e-6)
    assert np.allclose(c.integrate(t, np.cos(t)).y, np.sin(t), atol=1e-6)
    curve = c.resample([0.0, 1.0, 3.0], [0.0, 2.0, 6.0], 0.5)
    assert curve.t.tolist() == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0] and np.allclose(curve.y, 2 * curve.t)
    assert curve.meta["operation"] == "resample" and curve.meta["parameters"] == {"dt": 0.5}


@pytest.mark.parametrize("cfc", [60.0, 180.0, 600.0, 1000.0])
def test_sae_filter_matches_its_design_response(cfc: float) -> None:
    def expected(f: float) -> float:
        """Exact digital response: forward + backward 2-pole Butterworth, bilinear transform with the
        design frequency fd = 2.0775*CFC mapped exactly (J211 App. C: wa = tan(wd*T/2))."""
        warped = math.tan(math.pi * f / FS) / math.tan(math.pi * 2.0775 * cfc / FS)
        return 1 / (1 + warped ** 4)

    assert np.allclose(c.sae_filter(T, np.full(T.size, 3.0), cfc).y, 3.0)  # DC passes, ends included
    for f in (cfc, 10 * cfc):
        got = _gain(c.sae_filter(T, np.sin(2 * math.pi * f * T), cfc).y, f)
        assert got == pytest.approx(expected(f), rel=0.03, abs=2e-5)
    assert 1 / (1 + (1 / 2.0775) ** 4) == pytest.approx(0.949, abs=1e-3)  # J211: within +-0.5 dB at CFC


@pytest.mark.parametrize("order", [2, 4, 5])
def test_butterworth_zero_phase_gain(order: int) -> None:
    cutoff = 500.0
    for ratio in (0.2, 1.0, 5.0):
        f = ratio * cutoff
        signal = np.sin(2 * math.pi * f * T)
        filtered = c.butterworth_filter(T, signal, order, cutoff).y
        warped = math.tan(math.pi * f / FS) / math.tan(math.pi * cutoff / FS)  # exact: pre-warped at the cutoff
        assert _gain(filtered, f) == pytest.approx(1 / (1 + warped ** (2 * order)), rel=0.03, abs=1e-5)
        if ratio == 0.2:  # zero phase: the passed sine is not shifted
            middle = slice(T.size // 4, 3 * T.size // 4)
            assert np.allclose(filtered[middle], signal[middle] * _gain(filtered, f), atol=2e-3)


def test_spectrum_and_cross_plot() -> None:
    t = np.arange(0, 1, 1 / 1000.0)
    spec = c.spectrum(t, 0.5 + 2.0 * np.sin(2 * math.pi * 50 * t))
    assert spec.y[0] == pytest.approx(0.5) and spec.t[np.argmax(spec.y[1:]) + 1] == 50.0
    assert spec.y[np.argmax(spec.y[1:]) + 1] == pytest.approx(2.0, rel=1e-6)
    force = c.cross_plot([0, 1, 2, 3], [0, 10, 20, 30], [0.5, 1.5, 2.5], [1, 3, 5])
    assert force.t.tolist() == [10, 20] and force.y.tolist() == [2.0, 4.0]


def test_refusals() -> None:
    uneven = [0.0, 0.1, 0.3, 0.4]
    with pytest.raises(c.CurveError, match="resample"):
        c.sae_filter(uneven, [0, 1, 2, 3], 60)
    with pytest.raises(c.CurveError, match="Nyquist"):
        c.butterworth_filter(T, np.sin(T), 2, FS)
    with pytest.raises(c.CurveError, match="increase"):
        c.integrate([0, 0, 1], [1, 2, 3])
    with pytest.raises(c.CurveError, match="1..16"):
        c.butterworth_filter(T, np.sin(T), 17, 100)
