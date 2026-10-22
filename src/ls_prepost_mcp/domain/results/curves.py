"""Curve operations (tasks.yaml Q07): units, calculus, resampling, filters, spectrum, cross plots and
stress-strain conversions.

Pure numpy, no LS-PrePost and no SciPy. Every operation returns a :class:`Curve` whose ``meta``
records ``operation``, ``formula``, ``parameters`` and the axes (Q07 acceptance):

* ``meta["units"] = {"t": label, "y": label}`` for the abscissa ``t`` and the ordinate ``y``. Labels
  are declared by the caller and carried through; derived labels are composed as text read left to
  right (``y/t`` for a derivative, ``y*t`` for an integral; ``kN/mm*ms`` for kN per mm/ms), as
  :class:`ls_prepost_mcp.units.Unit` reads them. ``None`` means "not declared" and is never guessed.
* ``meta["abscissa"]`` / ``meta["ordinate"]`` name the axes (``time``/``value``, ``frequency``/
  ``amplitude``, ``x``/``y`` for a cross plot, ``engineering_strain``/``engineering_stress``, ...).

Abscissae must be finite and strictly increasing; a repeated or decreasing sample is refused with
its index (nothing is sorted, merged or dropped). Filters and the spectrum need uniform sampling
(``resample`` first) and the time unit (``t_unit`` = s, ms, us or ns), because frequencies are in Hz.

Filters (both zero phase: run forward, then backward over the reversed result):

* ``sae_filter``: SAE J211/1 Appendix C (ISO 6487 uses the same filter). A 2-pole Butterworth
  low-pass with design frequency f_d = 2.0775 * CFC (CFC 60/180/600/1000 are the standard classes),
  coefficients exactly as J211:  w_d = 2 pi f_d,  w_a = tan(w_d T / 2),  D = 1 + sqrt(2) w_a + w_a^2,
  a0 = w_a^2 / D, a1 = 2 a0, a2 = a0, b1 = -2 (w_a^2 - 1) / D, b2 = (-1 + sqrt(2) w_a - w_a^2) / D,
  Y[i] = a0 X[i] + a1 X[i-1] + a2 X[i-2] + b1 Y[i-1] + b2 Y[i-2]. Applied forward and backward the
  result is phaseless and 4-pole: |H(f)|^2 = 1 / (1 + (tan(pi f T) / tan(pi f_d T))^4), 0.949 (-0.45 dB)
  at f = CFC.
* ``butterworth_filter``: order n (1..16), analog Butterworth poles, bilinear transform pre-warped at
  ``cutoff_hz``, unit DC gain, second-order sections. Forward + backward gives |H|^2 =
  1 / (1 + (tan(pi f T) / tan(pi f_c T))^(2n)): 1/2 (-6 dB) at the cutoff, i.e. ``cutoff_hz`` is the
  -3 dB frequency of one pass (the scipy ``filtfilt`` convention).

Record ends (``padding``; J211 fixes the recursion and the two passes, the end treatment is this
module's convention and is recorded in ``meta``):

* ``"odd"`` (default): the record is extended at each end by its point reflection about the end
  sample (2 y[0] - y[k], 2 y[-1] - y[-1-k]), long enough for the slowest pole of the digital filter
  to decay by 1e-6 (``ceil(ln(1e6) / -ln r)`` samples, r the largest pole radius, at most len - 1;
  near Nyquist r approaches 1 and the padding grows). Constant and linear signals then pass
  unchanged; ``padding_complete`` is false (and curve_ops warns) when the record is shorter.
* ``"constant"``: the end values are held (every filter state starts at the end value), which is
  exact for a record that starts and ends at rest but bends a sloped end (``padding_complete`` None).

Spectrum: X_k = sum_n y_n exp(-2 pi i k n / N) (numpy rfft, rectangular window, no detrending);
amplitude A_0 = |X_0| / N (the mean), A_k = 2 |X_k| / N, A_{N/2} = |X_{N/2}| / N for even N, at
f_k = k / (N T) Hz. A sine of amplitude a at a bin frequency gives A = a; off-bin energy leaks.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ...units import Unit

MAX_SAMPLES = 1_000_000
SAE_CLASSES = (60, 180, 600, 1000)
SAE_DESIGN_RATIO = 2.0775
PADDINGS = ("odd", "constant")
_DECAY = math.log(1e6)  # odd padding lasts until the slowest digital pole has decayed by this factor


class CurveError(ValueError):
    """An operation that cannot be applied to the given samples."""


@dataclass(frozen=True)
class Curve:
    t: np.ndarray
    y: np.ndarray
    meta: dict = field(default_factory=dict)


def _pair(t: object, y: object, what: str = "A curve") -> tuple[np.ndarray, np.ndarray]:
    try:
        t, y = np.asarray(t, dtype=float), np.asarray(y, dtype=float)
    except (TypeError, ValueError):
        raise CurveError(f"{what} needs numeric samples") from None
    if t.ndim != 1 or t.shape != y.shape or t.size < 2:
        raise CurveError(f"{what} needs two 1-D arrays of equal length >= 2")
    if t.size > MAX_SAMPLES:
        raise CurveError(f"{what} exceeds {MAX_SAMPLES} samples")
    if not (np.isfinite(t).all() and np.isfinite(y).all()):
        raise CurveError(f"{what} samples must be finite")
    return t, y


def _xy(t: object, y: object) -> tuple[np.ndarray, np.ndarray]:
    t, y = _pair(t, y)
    steps = np.diff(t)
    bad = np.flatnonzero(steps <= 0)
    if bad.size:
        i = int(bad[0])
        kind = "repeats" if steps[i] == 0 else "goes back to"
        raise CurveError(f"Abscissae must increase strictly: sample {i + 1} {kind} {t[i + 1]:.17g} "
                         "(nothing is sorted, merged or dropped; clean the curve first)")
    return t, y


def _step(t: np.ndarray, rel: float = 1e-6) -> float:
    steps = np.diff(t)
    dt = float(steps.mean())
    if np.abs(steps - dt).max() > rel * dt:
        raise CurveError("Sampling is not uniform; resample the curve first")
    return dt


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CurveError(f"{name} must be a finite number")
    try:
        number = float(value)
    except OverflowError:
        raise CurveError(f"{name} must be a finite number") from None
    if not math.isfinite(number):
        raise CurveError(f"{name} must be a finite number")
    return number


def _positive(value: object, name: str) -> float:
    number = _number(value, name)
    if not number > 0:
        raise CurveError(f"{name} must be positive")
    return number


def _label(unit: object, name: str) -> str | None:
    if unit is None:
        return None
    if not isinstance(unit, str) or not 1 <= len(unit.strip()) <= 100:
        raise CurveError(f"{name} must be a unit label of 1..100 characters or None")
    return unit.strip()


def _unit(label: str, name: str) -> Unit:
    try:
        return Unit.parse(label)
    except ValueError as error:
        raise CurveError(f"{name} {label!r}: {error}") from None


def _seconds(t_unit: object) -> float:
    """Seconds per abscissa unit; frequencies in Hz need it."""
    if t_unit is None:
        raise CurveError("Frequencies are in Hz: declare the time unit (t_unit = s, ms, us or ns)")
    unit = _unit(_label(t_unit, "t_unit"), "time unit")
    if unit.dimensions != (0, 0, 1):
        raise CurveError(f"{t_unit!r} is not a time unit")
    return float(unit.scale)


def _compose(a: str | None, operator: str, b: str | None) -> str | None:
    """``a*b`` or ``a/b`` read left to right; dividing by a compound ``b`` flips its own operators."""
    if a is None or b is None:
        return None
    return f"{a}{operator}{b.translate(str.maketrans('*/', '/*')) if operator == '/' else b}"


def _meta(operation: str, formula: str, units: tuple[str | None, str | None], axes: tuple[str, str],
          **parameters: object) -> dict:
    return {"operation": operation, "formula": formula, "parameters": parameters,
            "units": {"t": units[0], "y": units[1]}, "abscissa": axes[0], "ordinate": axes[1]}


def history(t: object, y: object, *, t_unit: str, y_unit: str, **source: object) -> Curve:
    """A declared time history, the start of a pipeline: finite, strictly increasing times in a time
    unit (s, ms, us, ns) and a declared value unit. ``source`` (e.g. file and columns) is recorded."""
    t, y = _xy(t, y)
    _seconds(t_unit)
    value_unit = _label(y_unit, "y_unit")
    if value_unit is None:
        raise CurveError("Declare the value unit (y_unit)")
    return Curve(t, y, _meta("history", "declared samples, unchanged", (_label(t_unit, "t_unit"), value_unit),
                             ("time", "value"), **source))


def convert_units(t: object, y: object, *, t_unit: str | None, y_unit: str | None, to_t_unit: str | None = None,
                  to_y_unit: str | None = None, axes: tuple[str, str] = ("time", "value")) -> Curve:
    """Multiply the abscissa and/or the ordinate by the exact factor between two declared units
    (``units.Unit``: same dimensions, no offsets). Strictly increasing abscissae must stay so, and a
    nonzero sample must not underflow to zero; otherwise the conversion is refused."""
    t, y = _pair(t, y)
    if to_t_unit is None and to_y_unit is None:
        raise CurveError("Give to_t_unit and/or to_y_unit")
    declared = [_label(t_unit, "t_unit"), _label(y_unit, "y_unit")]
    factors, labels = [1.0, 1.0], list(declared)
    for axis, (source, target) in enumerate(((t_unit, to_t_unit), (y_unit, to_y_unit))):
        if target is None:
            continue
        if source is None:
            raise CurveError("Converting an axis needs its declared unit")
        old, new = _unit(source, "unit"), _unit(target, "unit")
        if old.dimensions != new.dimensions:
            raise CurveError(f"Incompatible unit dimensions: {source} -> {target}")
        factors[axis] = old.factor_to(new)
        labels[axis] = _label(target, "target unit")
    ordered = bool((np.diff(t) > 0).all())
    with np.errstate(over="ignore", under="ignore"):
        new_t, new_y = t * factors[0], y * factors[1]
    if not (np.isfinite(new_t).all() and np.isfinite(new_y).all()):
        raise CurveError("Unit conversion overflows")
    if ((t != 0) & (new_t == 0)).any() or ((y != 0) & (new_y == 0)).any():
        raise CurveError("Unit conversion would underflow nonzero samples to zero")
    if ordered and (np.diff(new_t) <= 0).any():
        raise CurveError("Unit conversion collapses the abscissa resolution")
    return Curve(new_t, new_y, _meta("convert_units", "t' = t * k_t, y' = y * k_y (exact unit factors)",
                                     (labels[0], labels[1]), axes, t_factor=factors[0],
                                     y_factor=factors[1], from_units=declared))


def resample(t: object, y: object, dt: float, *, t_unit: str | None = None, y_unit: str | None = None) -> Curve:
    """Linear interpolation onto the uniform grid t0, t0 + dt, ... <= t_end; nothing is extrapolated.

    The grid starts at the first sample and stops at the last multiple of ``dt`` inside the record
    (a remainder shorter than ``dt`` is dropped and reported). Repeated or decreasing times are
    refused (``_xy``), never averaged or sorted; ``dt`` (in the curve's time unit) must give at least
    two grid points. Interpolation does not low-pass: a step coarser than the input's
    (``coarser_than_input``) can alias content above the new Nyquist frequency, so filter first."""
    t, y = _xy(t, y)
    dt = _positive(dt, "dt")
    span = float(t[-1] - t[0])
    ratio = span / dt
    if not ratio < MAX_SAMPLES:
        raise CurveError(f"dt = {dt:g} gives more than {MAX_SAMPLES} samples")
    count = int(math.floor(ratio + 1e-9)) + 1
    if count < 2:
        raise CurveError(f"dt = {dt:g} is longer than the record ({span:g})")
    grid = np.minimum(t[0] + dt * np.arange(count), t[-1])
    return Curve(grid, np.interp(grid, t, y), _meta(
        "resample", "y(t0 + k dt) by linear interpolation between neighbouring samples", (t_unit, y_unit),
        ("time", "value"), dt=dt, start=float(t[0]), samples=count, dropped_tail=float(t[-1] - grid[-1]),
        coarser_than_input=bool(dt > float(np.diff(t).max()) * (1 + 1e-9))))


def differentiate(t: object, y: object, *, t_unit: str | None = None, y_unit: str | None = None,
                  abscissa: str = "time") -> Curve:
    """dy/dt by second-order differences (numpy.gradient; non-uniform spacing allowed)."""
    t, y = _xy(t, y)
    return Curve(t, np.gradient(y, t, edge_order=2 if t.size > 2 else 1), _meta(
        "differentiate", "central differences, 2nd order (one-sided at the ends)",
        (t_unit, _compose(y_unit, "/", t_unit)), (abscissa, "value")))


def integrate(t: object, y: object, initial: float = 0.0, *, t_unit: str | None = None,
              y_unit: str | None = None, abscissa: str = "time") -> Curve:
    """Cumulative trapezoidal integral starting at ``initial`` (in y*t units)."""
    t, y = _xy(t, y)
    initial = _number(initial, "initial")
    area = np.concatenate([[0.0], np.cumsum(np.diff(t) * (y[1:] + y[:-1]) / 2)])
    return Curve(t, initial + area, _meta("integrate", "I(t_k) = initial + sum (t_i - t_i-1)(y_i + y_i-1)/2",
                                          (t_unit, _compose(y_unit, "*", t_unit)), (abscissa, "value"),
                                          initial=initial))


def _recursive(x: np.ndarray, b: tuple[float, float, float], a: tuple[float, float], start: float) -> np.ndarray:
    """y[i] = b0 x[i] + b1 x[i-1] + b2 x[i-2] + a1 y[i-1] + a2 y[i-2], history = ``start``."""
    (b0, b1, b2), (a1, a2) = b, a
    out = []
    append = out.append
    x1 = x2 = y1 = y2 = float(start)
    for xi in x.tolist():
        yi = b0 * xi + b1 * x1 + b2 * x2 + a1 * y1 + a2 * y2
        append(yi)
        x2, x1, y2, y1 = x1, xi, y1, yi
    return np.asarray(out)


def _settling(sections: list) -> int:
    """Samples for the slowest digital pole to decay by 1e-6: ceil(ln(1e6) / -ln r), r = max |pole|
    over the sections (poles of z^2 - a1 z - a2), at least the two samples of input history."""
    radius = max(float(np.abs(np.roots([1.0, -a[0], -a[1]])).max()) for _, a in sections)
    if not radius < 1:
        raise CurveError("The digital filter is not stable at this sampling rate")
    return 2 if radius == 0 else max(2, math.ceil(_DECAY / -math.log(radius)))


def _zero_phase(y: np.ndarray, sections: list, padding: object) -> tuple[np.ndarray, dict]:
    """Forward then backward pass with the given end treatment (module docstring)."""
    if padding not in PADDINGS:
        raise CurveError(f"padding must be one of {PADDINGS}")
    needed = _settling(sections)
    pad = min(y.size - 1, needed) if padding == "odd" else 0
    data = np.concatenate([2 * y[0] - y[pad:0:-1], y, 2 * y[-1] - y[-2:-pad - 2:-1]]) if pad else y.copy()
    for direction in (1, -1):
        data = data[::direction]
        for b, a in sections:
            data = _recursive(data, b, a, data[0])
        data = data[::direction]
    return data[pad:pad + y.size], {"padding": padding, "padding_samples": pad,
                                    "padding_complete": None if padding == "constant" else pad >= needed}


def sae_filter(t: object, y: object, cfc: float, *, t_unit: str, y_unit: str | None = None,
               padding: str = "odd") -> Curve:
    """SAE J211/1 CFC filter (module docstring); ``cfc`` as in the SAEFilter contract, in Hz."""
    t, y = _xy(t, y)
    cfc = _positive(cfc, "CFC")
    dt = _step(t)
    dt_s = dt * _seconds(t_unit)
    design = SAE_DESIGN_RATIO * cfc
    if design >= 0.5 / dt_s:
        raise CurveError(f"CFC {cfc:g}: design frequency {design:g} Hz must be below the Nyquist frequency "
                         f"{0.5 / dt_s:g} Hz; sample faster")
    wa = math.tan(2 * math.pi * design * dt_s / 2)
    norm = 1 + math.sqrt(2) * wa + wa * wa
    a0 = wa * wa / norm
    b = (a0, 2 * a0, a0)
    a = (-2 * (wa * wa - 1) / norm, (-1 + math.sqrt(2) * wa - wa * wa) / norm)
    filtered, ends = _zero_phase(y, [(b, a)], padding)
    return Curve(t, filtered, _meta(
        "sae_filter", "SAE J211/1 App. C: 2-pole Butterworth, f_d = 2.0775*CFC, w_a = tan(pi f_d T), "
        "forward + backward (phaseless 4-pole)", (t_unit, y_unit), ("time", "value"), cfc=cfc,
        standard_class=cfc in SAE_CLASSES, design_frequency_hz=design, sampling_rate_hz=1 / dt_s, dt=dt,
        coefficients={"a0": a0, "a1": 2 * a0, "a2": a0, "b1": a[0], "b2": a[1]}, **ends))


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


def butterworth_filter(t: object, y: object, order: int, cutoff_hz: float, *, t_unit: str,
                       y_unit: str | None = None, padding: str = "odd") -> Curve:
    """Zero-phase Butterworth low-pass (ButterworthFilter contract: order 1..16, cutoff_hz)."""
    t, y = _xy(t, y)
    if isinstance(order, bool) or not isinstance(order, int) or not 1 <= order <= 16:
        raise CurveError("order must be an integer in 1..16")
    cutoff_hz = _positive(cutoff_hz, "cutoff_hz")
    dt = _step(t)
    dt_s = dt * _seconds(t_unit)
    if cutoff_hz >= 0.5 / dt_s:
        raise CurveError(f"cutoff {cutoff_hz:g} Hz must be below the Nyquist frequency {0.5 / dt_s:g} Hz")
    filtered, ends = _zero_phase(y, _sections(order, cutoff_hz, 1 / dt_s), padding)
    return Curve(t, filtered, _meta(
        "butterworth_filter", "Butterworth low-pass, bilinear transform pre-warped at the cutoff, forward + "
        "backward (zero phase, |H|^2 = 1/(1 + (tan(pi f T)/tan(pi f_c T))^(2n)))", (t_unit, y_unit),
        ("time", "value"), order=order, cutoff_hz=cutoff_hz, sampling_rate_hz=1 / dt_s, dt=dt, **ends))


def spectrum(t: object, y: object, *, t_unit: str, y_unit: str | None = None) -> Curve:
    """One-sided amplitude spectrum (module docstring); abscissa in Hz, ordinate in y units."""
    t, y = _xy(t, y)
    dt = _step(t)
    dt_s = dt * _seconds(t_unit)
    amplitude = np.abs(np.fft.rfft(y)) * 2 / y.size
    amplitude[0] /= 2
    if y.size % 2 == 0:
        amplitude[-1] /= 2
    return Curve(np.fft.rfftfreq(y.size, dt_s), amplitude, _meta(
        "spectrum", "A_k = 2|X_k|/N (A_0 = |X_0|/N, A_N/2 = |X_N/2|/N), f_k = k/(N T), rectangular window",
        ("Hz", y_unit), ("frequency", "amplitude"), dt=dt, sampling_rate_hz=1 / dt_s,
        resolution_hz=1 / (y.size * dt_s), samples=int(y.size), window="rectangular"))


def cross_plot(tx: object, x: object, ty: object, y: object, *, t_unit: str | None = None,
               x_unit: str | None = None, y_unit: str | None = None) -> Curve:
    """y(t) against x(t) on the common time interval. Both curves share one time unit (``t_unit``,
    the caller converts first); the abscissa is x and need not be monotonic.

    Times are the union of both curves' samples inside [max(start), min(end)] plus its ends, both
    values interpolated linearly there; nothing is extrapolated and disjoint ranges are refused."""
    tx, x = _xy(tx, x)
    ty, y = _xy(ty, y)
    lo, hi = max(tx[0], ty[0]), min(tx[-1], ty[-1])
    if not lo < hi:
        raise CurveError(f"The time ranges [{tx[0]:g}, {tx[-1]:g}] and [{ty[0]:g}, {ty[-1]:g}] do not overlap")
    times = np.unique(np.concatenate([tx[(tx >= lo) & (tx <= hi)], ty[(ty >= lo) & (ty <= hi)], [lo, hi]]))
    if times.size > MAX_SAMPLES:
        raise CurveError(f"The aligned curve exceeds {MAX_SAMPLES} samples")
    return Curve(np.interp(times, tx, x), np.interp(times, ty, y), _meta(
        "cross_plot", "(x(t), y(t)) at the union of both sample times in the common interval, linear "
        "interpolation, no extrapolation", (x_unit, y_unit), ("x", "y"), interval=[float(lo), float(hi)],
        t_unit=t_unit, samples=int(times.size)))


def engineering_stress_strain(displacement: object, force: object, area: float, gauge_length: float, *,
                              displacement_unit: str | None = None, force_unit: str | None = None,
                              length_unit: str | None = None) -> Curve:
    """sigma_e = F / A0, eps_e = delta / L0 from a force-displacement curve.

    ``area`` is in length_unit^2 and ``gauge_length`` in ``length_unit`` (one length term, e.g. mm
    or m). Declare the displacement, force and length units together (dimensions are checked with
    ``units.Unit``) or none of them: the displacement is converted to ``length_unit`` by the exact
    factor, the stress label is ``force_unit/length_unit^2`` and the strain is a ratio ("1").
    Without units the three lengths are taken to share one unit, and the result says so."""
    d, f = _pair(displacement, force, "A force-displacement curve")
    area, gauge_length = _positive(area, "area"), _positive(gauge_length, "gauge_length")
    declared = (displacement_unit, force_unit, length_unit)
    if None in declared and any(unit is not None for unit in declared):
        raise CurveError("Declare displacement_unit, force_unit and length_unit together, or none of them")
    stress_unit, factor = None, 1.0
    if length_unit is not None:
        length, moved = _unit(length_unit, "length unit"), _unit(displacement_unit, "displacement unit")
        if length.dimensions != (1, 0, 0) or any(sign in length_unit for sign in "*/^"):
            raise CurveError(f"length_unit {length_unit!r} must be one length unit such as mm or m")
        if moved.dimensions != (1, 0, 0):
            raise CurveError(f"{displacement_unit!r} is not a length unit")
        if _unit(force_unit, "force unit").dimensions != (1, 1, -2):
            raise CurveError(f"{force_unit!r} is not a force unit")
        factor = moved.factor_to(length)
        stress_unit = f"{force_unit.strip()}/{length_unit.strip()}^2"
    return Curve(d * factor / gauge_length, f / area, _meta(
        "engineering_stress_strain", "sigma_e = F / A0, eps_e = delta * k / L0 (k: displacement to length unit)",
        ("1", stress_unit), ("engineering_strain", "engineering_stress"), area=area, gauge_length=gauge_length,
        displacement_unit=displacement_unit, force_unit=force_unit, length_unit=length_unit,
        displacement_factor=factor,
        assumption=None if length_unit else "displacement, gauge length and area share one undeclared length unit"))


def true_stress_strain(strain: object, stress: object, *, strain_unit: str = "1",
                       stress_unit: str | None = None) -> Curve:
    """sigma_t = sigma_e (1 + eps_e), eps_t = ln(1 + eps_e) from an engineering stress-strain curve.

    ``strain_unit`` is a dimensionless unit ("1" for a ratio, "%", "microstrain"); the strain is
    converted to a ratio first. Valid only while the deformation is uniform and the volume
    constant: in tension up to the maximum engineering stress (onset of necking, Considere); after
    it the local true stress needs the measured neck area or a Bridgman correction. That point is
    reported, not cut off. eps_e <= -1 is refused (ln(1 + eps_e) undefined)."""
    e, s = _pair(strain, stress, "An engineering stress-strain curve")
    if strain_unit is None:
        raise CurveError("Declare the strain unit ('1' for a ratio, '%' or 'microstrain')")
    ratio = _unit(strain_unit, "strain unit")
    if ratio.dimensions != (0, 0, 0):
        raise CurveError(f"{strain_unit!r} is not a strain unit ('1', '%' or 'microstrain')")
    e = e * float(ratio.scale)
    bad = np.flatnonzero(e <= -1)
    if bad.size:
        raise CurveError(f"Engineering strain must exceed -1 (sample {int(bad[0])}: {e[bad[0]]:g} as a ratio)")
    tension = s[int(np.argmax(np.abs(s)))] > 0  # the largest stress in magnitude decides
    peak = int(np.argmax(s)) if tension else None
    uniform = None if peak is None else {"index": peak, "engineering_strain": float(e[peak]),
                                         "engineering_stress": float(s[peak]), "samples_after": int(e.size - 1 - peak)}
    return Curve(np.log1p(e), s * (1 + e), _meta(
        "true_stress_strain", "sigma_t = sigma_e (1 + eps_e), eps_t = ln(1 + eps_e); uniform deformation, "
        "constant volume", ("1", _label(stress_unit, "stress_unit")), ("true_strain", "true_stress"),
        strain_unit=strain_unit, strain_factor=float(ratio.scale),
        validity="uniform deformation only (in tension: up to the maximum engineering stress)",
        maximum_engineering_stress=uniform))


__all__ = ["Curve", "CurveError", "MAX_SAMPLES", "PADDINGS", "SAE_CLASSES", "butterworth_filter",
           "convert_units", "cross_plot", "differentiate", "engineering_stress_strain", "history", "integrate",
           "resample", "sae_filter", "spectrum", "true_stress_strain"]
