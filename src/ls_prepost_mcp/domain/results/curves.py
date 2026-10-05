"""Curve operations (tasks.yaml Q07): filters, calculus, resampling, spectrum and cross plots.

Pure numpy, no LS-PrePost. Every operation returns a :class:`Curve` whose ``meta`` records the
operation, its formula and its parameters (Q07 acceptance). Filters and spectra need uniform
sampling and refuse anything else (resample first) instead of silently resampling.

Filter definitions:

* SAE J211/1 Appendix C (CFC filter): a 2-pole Butterworth low-pass with design frequency
  2.0775 x CFC, applied forward and then backward, so the result is phaseless and 4-pole
  (gain |H|^2 = 1 / (1 + (f / (2.0775 CFC))^4) before frequency warping). Start-up uses the
  first and last samples as constant extensions.
* Butterworth of order n (``ButterworthFilter`` contract: order 1..16, cutoff_hz): analog
  prototype poles, bilinear transform with frequency pre-warping, unit DC gain, run forward and
  backward (zero phase, gain |H|^2, i.e. 1/2 at the cutoff); ends padded by odd reflection.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


class CurveError(ValueError):
    """An operation that cannot be applied to the given samples."""


@dataclass(frozen=True)
class Curve:
    t: np.ndarray
    y: np.ndarray
    meta: dict = field(default_factory=dict)


def _xy(t: object, y: object) -> tuple[np.ndarray, np.ndarray]:
    t, y = np.asarray(t, dtype=float), np.asarray(y, dtype=float)
    if t.ndim != 1 or t.shape != y.shape or t.size < 2:
        raise CurveError("A curve needs two 1-D arrays of equal length >= 2")
    if not (np.isfinite(t).all() and np.isfinite(y).all()):
        raise CurveError("Curve samples must be finite")
    if (np.diff(t) <= 0).any():
        raise CurveError("Abscissae must increase strictly")
    return t, y


def _step(t: np.ndarray, rel: float = 1e-6) -> float:
    steps = np.diff(t)
    dt = float(steps.mean())
    if np.abs(steps - dt).max() > rel * dt:
        raise CurveError("Sampling is not uniform; resample the curve first")
    return dt


def _meta(operation: str, formula: str, **parameters: object) -> dict:
    return {"operation": operation, "formula": formula, "parameters": parameters}


def resample(t: object, y: object, dt: float) -> Curve:
    """Linear interpolation onto t0, t0 + dt, ... <= t_end."""
    t, y = _xy(t, y)
    if not dt > 0:
        raise CurveError("dt must be positive")
    grid = t[0] + dt * np.arange(int(math.floor((t[-1] - t[0]) / dt + 1e-9)) + 1)
    return Curve(grid, np.interp(grid, t, y), _meta("resample", "linear interpolation", dt=dt))


def differentiate(t: object, y: object) -> Curve:
    """dy/dt by second-order differences (numpy.gradient; non-uniform spacing allowed)."""
    t, y = _xy(t, y)
    return Curve(t, np.gradient(y, t, edge_order=2), _meta("differentiate", "central differences, 2nd order"))


def integrate(t: object, y: object, initial: float = 0.0) -> Curve:
    """Cumulative trapezoidal integral starting at ``initial``."""
    t, y = _xy(t, y)
    area = np.concatenate([[0.0], np.cumsum(np.diff(t) * (y[1:] + y[:-1]) / 2)])
    return Curve(t, initial + area, _meta("integrate", "cumulative trapezoid", initial=initial))


def _recursive(x: np.ndarray, b: tuple[float, float, float], a: tuple[float, float], start: float) -> np.ndarray:
    """y[i] = b0 x[i] + b1 x[i-1] + b2 x[i-2] + a1 y[i-1] + a2 y[i-2], history = ``start``."""
    out = np.empty_like(x)
    x1 = x2 = y1 = y2 = start
    for i, xi in enumerate(x):
        yi = b[0] * xi + b[1] * x1 + b[2] * x2 + a[0] * y1 + a[1] * y2
        out[i] = yi
        x2, x1, y2, y1 = x1, xi, y1, yi
    return out


def sae_filter(t: object, y: object, cfc: float) -> Curve:
    """SAE J211/1 CFC filter (phaseless, forward and backward); ``cfc`` as in the SAEFilter contract."""
    t, y = _xy(t, y)
    if not cfc > 0:
        raise CurveError("CFC must be positive")
    dt = _step(t)
    wd = 2 * math.pi * cfc * 2.0775
    wa = math.sin(wd * dt / 2) / math.cos(wd * dt / 2)
    norm = 1 + math.sqrt(2) * wa + wa * wa
    a0 = wa * wa / norm
    b = (a0, 2 * a0, a0)
    a = (-2 * (wa * wa - 1) / norm, (-1 + math.sqrt(2) * wa - wa * wa) / norm)
    forward = _recursive(y, b, a, y[0])
    backward = _recursive(forward[::-1], b, a, forward[-1])[::-1]
    return Curve(t, backward, _meta("sae_filter", "SAE J211/1 App. C, 2-pole Butterworth forward+backward, "
                                    "design frequency 2.0775*CFC", cfc=cfc, dt=dt))


def _sections(order: int, cutoff: float, fs: float) -> list[tuple[tuple[float, float, float], tuple[float, float]]]:
    """Second-order sections (b, a) of a digital Butterworth low-pass with unit DC gain."""
    warped = 2 * fs * math.tan(math.pi * cutoff / fs)
    poles = [warped * np.exp(1j * math.pi * (2 * k + order + 1) / (2 * order)) for k in range(order)]
    digital = [(1 + p / (2 * fs)) / (1 - p / (2 * fs)) for p in poles]
    upper = sorted((z for z in digital if z.imag > 1e-12), key=lambda z: z.real)
    real = [z.real for z in digital if abs(z.imag) <= 1e-12]
    sections = []
    for z in upper:  # conjugate pair -> (1 + z^-1)^2 / (1 - 2 Re z z^-1 + |z|^2 z^-2)
        a1, a2 = -2 * z.real, abs(z) ** 2
        gain = (1 + a1 + a2) / 4
        sections.append(((gain, 2 * gain, gain), (-a1, -a2)))
    for z in real:  # first-order section padded to second order
        gain = (1 - z) / 2
        sections.append(((gain, gain, 0.0), (z, 0.0)))
    return sections


def butterworth_filter(t: object, y: object, order: int, cutoff_hz: float) -> Curve:
    """Zero-phase Butterworth low-pass (ButterworthFilter contract: order 1..16, cutoff_hz)."""
    t, y = _xy(t, y)
    if not (isinstance(order, int) and 1 <= order <= 16) or not cutoff_hz > 0:
        raise CurveError("order must be an integer in 1..16 and cutoff_hz positive")
    dt = _step(t)
    fs = 1 / dt
    if cutoff_hz >= fs / 2:
        raise CurveError(f"cutoff {cutoff_hz:g} Hz must be below the Nyquist frequency {fs / 2:g} Hz")
    pad = min(y.size - 1, 3 * (order + 1))
    extended = np.concatenate([2 * y[0] - y[pad:0:-1], y, 2 * y[-1] - y[-2:-pad - 2:-1]])
    sections = _sections(order, cutoff_hz, fs)
    for direction in (1, -1):
        extended = extended[::direction]
        for b, a in sections:
            extended = _recursive(extended, b, a, extended[0])
        extended = extended[::direction]
    return Curve(t, extended[pad:pad + y.size], _meta(
        "butterworth_filter", "Butterworth low-pass, bilinear transform with pre-warping, forward+backward "
        "(zero phase, gain |H|^2), odd-reflection padding", order=order, cutoff_hz=cutoff_hz, dt=dt))


def spectrum(t: object, y: object) -> Curve:
    """One-sided amplitude spectrum (rfft; amplitude of a sine = its amplitude); abscissa in Hz."""
    t, y = _xy(t, y)
    dt = _step(t)
    values = np.fft.rfft(y)
    amplitude = np.abs(values) * 2 / y.size
    amplitude[0] /= 2
    if y.size % 2 == 0:
        amplitude[-1] /= 2
    return Curve(np.fft.rfftfreq(y.size, dt), amplitude, _meta("spectrum", "one-sided |rfft| * 2/N", dt=dt,
                                                                samples=int(y.size)))


def cross_plot(tx: object, x: object, ty: object, y: object) -> Curve:
    """y against x on the common time interval (x's samples inside it; y interpolated linearly)."""
    tx, x = _xy(tx, x)
    ty, y = _xy(ty, y)
    lo, hi = max(tx[0], ty[0]), min(tx[-1], ty[-1])
    inside = (tx >= lo) & (tx <= hi)
    if inside.sum() < 2:
        raise CurveError("The two curves share fewer than two time samples")
    return Curve(x[inside], np.interp(tx[inside], ty, y), _meta(
        "cross_plot", "y(t) against x(t) on the common interval, y interpolated linearly", interval=[lo, hi]))


__all__ = ["Curve", "CurveError", "butterworth_filter", "cross_plot", "differentiate", "integrate", "resample",
           "sae_filter", "spectrum"]
