"""Q07 curve operations: SAE J211/Butterworth filtering, resampling, FFT, cross plot, and stress-strain.

Features:
- SAE J211 / ISO 6487 four-pole zero-phase digital filtering (CFC 60, 180, 600, 1000);
- General Butterworth zero-phase filtering;
- Strictly non-extrapolated uniform resampling;
- Fast Fourier Transform (FFT) spectrum and dominant frequency extraction;
- Cross plotting (combining X(t) and Y(t) onto common time base, e.g., Force-Displacement);
- Engineering stress-strain to true stress-strain conversion (incompressible pre-necking model);
- Numerical differentiation (2nd order interior) and integration (trapezoidal quadrature);
- Curve summary statistics (min, max, peak, duration, time-weighted average, RMS, integral).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from .domain.results.curves import _recursive


class CurveOperationError(ValueError):
    """Raised when curve data or parameters are invalid or calculations fail."""


def read_curve_table(
    path: str | Path,
    time_column: str | int = 1,
    value_column: str | int = 2,
    delimiter: str = "comma",
    skip_rows: int = 1,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Read two numeric columns (time, value) from CSV or delimited text.

    Supports 1-based integer column index or named string columns (when header exists).
    Returns (times, values, header_names).
    """
    p = Path(path)
    if not p.is_file():
        raise CurveOperationError(f"Curve file not found: {p}")

    text = p.read_text(encoding="utf-8-sig")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise CurveOperationError(f"Curve file is empty: {p}")

    sep = "," if delimiter in ("comma", ",") else "\t" if delimiter in ("tab", "\\t") else None

    # Parse header if available
    first_tokens = lines[0].split(sep) if sep else lines[0].split()
    header_present = False
    headers: list[str] = []

    # Check if first row contains non-numeric strings
    try:
        float(first_tokens[0])
    except ValueError:
        header_present = True
        headers = [h.strip().strip('"').strip("'") for h in first_tokens]

    data_lines = lines[(skip_rows if header_present else 0) :]
    if not data_lines:
        raise CurveOperationError(f"No numeric data lines found in {p}")

    rows: list[list[float]] = []
    for line_idx, line in enumerate(data_lines, start=1):
        if line.startswith(("$", "#", "%")):
            continue
        tokens = line.split(sep) if sep else line.split()
        if not tokens:
            continue
        try:
            row_vals = [float(tok.strip().strip('"')) for tok in tokens]
            rows.append(row_vals)
        except ValueError as err:
            raise CurveOperationError(f"Non-numeric value in line {line_idx} of {p}: {line}") from err

    if len(rows) < 2:
        raise CurveOperationError(f"Curve requires at least 2 data points, found {len(rows)}")

    data = np.asarray(rows, dtype=float)

    # Resolve time and value columns
    if isinstance(time_column, str):
        if time_column not in headers:
            raise CurveOperationError(f"Column '{time_column}' not found in headers {headers}")
        t_col_idx = headers.index(time_column)
    else:
        t_col_idx = int(time_column) - 1

    if isinstance(value_column, str):
        if value_column not in headers:
            raise CurveOperationError(f"Column '{value_column}' not found in headers {headers}")
        v_col_idx = headers.index(value_column)
    else:
        v_col_idx = int(value_column) - 1

    if t_col_idx < 0 or t_col_idx >= data.shape[1]:
        raise CurveOperationError(f"Time column index {time_column} out of range [1, {data.shape[1]}]")
    if v_col_idx < 0 or v_col_idx >= data.shape[1]:
        raise CurveOperationError(f"Value column index {value_column} out of range [1, {data.shape[1]}]")

    times = data[:, t_col_idx]
    values = data[:, v_col_idx]

    if not (np.all(np.isfinite(times)) and np.all(np.isfinite(values))):
        raise CurveOperationError("Curve contains NaN or infinite values")

    return times, values, headers


def sae_j211_filter(
    times: np.ndarray,
    values: np.ndarray,
    cfc: int = 60,
    custom_cutoff_hz: float | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Apply SAE J211 / ISO 6487 four-pole zero-phase Butterworth filter.

    CFC standards:
    - CFC 60:   fc = 100.0 Hz (rollover/rolloff -3dB point)
    - CFC 180:  fc = 300.0 Hz
    - CFC 600:  fc = 1000.0 Hz
    - CFC 1000: fc = 1650.0 Hz (or 1667 Hz)

    Returns (filtered_values, filter_metadata).
    """
    times = np.asarray(times, dtype=float)
    values = np.asarray(values, dtype=float)

    if len(times) < 5:
        raise CurveOperationError("SAE J211 filter requires at least 5 data points")

    diffs = np.diff(times)
    if np.any(diffs <= 0):
        raise CurveOperationError("Times must be strictly increasing for digital filtering")

    dt = float(np.mean(diffs))
    sampling_rate = 1.0 / dt

    if custom_cutoff_hz is not None:
        fc = float(custom_cutoff_hz)
    else:
        fc_map = {60: 100.0, 180: 300.0, 600: 1000.0, 1000: 1650.0}
        fc = fc_map.get(cfc, 1.65 * cfc)

    # Nyquist criterion check
    nyquist = 0.5 * sampling_rate
    if fc >= nyquist:
        raise CurveOperationError(
            f"Cutoff frequency {fc:.1f} Hz must be strictly less than Nyquist frequency {nyquist:.1f} Hz (dt={dt:.6e} s)"
        )

    if custom_cutoff_hz is None:
        wd = 2 * math.pi * cfc * 2.0775
        wa = math.tan(wd * dt / 2)
    else:
        wa = math.tan(math.pi * fc * dt)
    norm = 1.0 + math.sqrt(2.0) * wa + wa * wa
    a0 = (wa * wa) / norm
    b = [a0, 2.0 * a0, a0]
    a = [-2.0 * (wa * wa - 1.0) / norm, (-1.0 + math.sqrt(2.0) * wa - wa * wa) / norm]
    forward = _recursive(values, (b[0], b[1], b[2]), (a[0], a[1]), values[0])
    backward = _recursive(forward[::-1], (b[0], b[1], b[2]), (a[0], a[1]), forward[-1])[::-1]
    filtered = backward

    meta = {
        "filter_standard": "SAE J211 / ISO 6487",
        "cfc": cfc if custom_cutoff_hz is None else "custom",
        "cutoff_frequency_hz": fc,
        "sampling_rate_hz": sampling_rate,
        "nyquist_hz": nyquist,
        "filter_poles": 4,
        "phase_shift": "zero (forward-backward bidirectional filtfilt)",
        "coefficients": {"b": b, "a": a},
    }
    return filtered, meta


def resample_curve(
    times: np.ndarray,
    values: np.ndarray,
    dt: float | None = None,
    num_points: int | None = None,
    target_times: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Resample curve onto a uniform time grid using linear interpolation (strictly no extrapolation)."""
    times = np.asarray(times, dtype=float)
    values = np.asarray(values, dtype=float)

    if len(times) < 2 or np.any(np.diff(times) <= 0):
        raise CurveOperationError("Times must have at least 2 strictly increasing points")

    t_start = float(times[0])
    t_end = float(times[-1])

    if target_times is not None:
        new_times = np.asarray(target_times, dtype=float)
        if np.any(new_times < t_start - 1e-12) or np.any(new_times > t_end + 1e-12):
            raise CurveOperationError(
                f"Target times [{new_times.min()}, {new_times.max()}] exceed curve interval [{t_start}, {t_end}]; no extrapolation allowed"
            )
    elif dt is not None:
        if not (math.isfinite(dt) and dt > 0):
            raise CurveOperationError(f"Resampling time step dt must be positive: {dt}")
        new_times = np.arange(t_start, t_end + 1e-14, dt)
    elif num_points is not None:
        if not (isinstance(num_points, int) and num_points >= 2):
            raise CurveOperationError(f"num_points must be an integer >= 2: {num_points}")
        new_times = np.linspace(t_start, t_end, num_points)
    else:
        raise CurveOperationError("Specify either dt, num_points, or target_times for resampling")

    new_values = np.interp(new_times, times, values)

    meta = {
        "resample_method": "linear interpolation; no extrapolation",
        "original_sample_count": len(times),
        "resampled_sample_count": len(new_times),
        "t_start": t_start,
        "t_end": t_end,
        "dt": float(np.mean(np.diff(new_times))) if len(new_times) > 1 else None,
    }
    return new_times, new_values, meta


def compute_fft(
    times: np.ndarray,
    values: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Compute Fast Fourier Transform spectrum and extract dominant frequency.

    If sampling interval is non-uniform, automatically resamples onto uniform grid.
    Returns (frequencies, amplitudes, metadata).
    """
    times = np.asarray(times, dtype=float)
    values = np.asarray(values, dtype=float)

    diffs = np.diff(times)
    is_uniform = np.allclose(diffs, diffs[0], rtol=1e-3, atol=1e-8)
    if not is_uniform:
        # Uniform resample first
        dt_mean = float(np.mean(diffs))
        times, values, _ = resample_curve(times, values, dt=dt_mean)
        dt = dt_mean
    else:
        dt = float(diffs[0])

    n = len(values)
    # Remove DC component for spectral peak identification
    dc_offset = float(np.mean(values))
    detrended = values - dc_offset

    # Real FFT
    freqs = np.fft.rfftfreq(n, d=dt)
    fft_vals = np.fft.rfft(detrended)
    amplitudes = np.abs(fft_vals) * (2.0 / n)
    amplitudes[0] = abs(dc_offset)  # DC term amplitude

    # Find dominant peak (excluding DC)
    if len(freqs) > 1:
        peak_idx = int(np.argmax(amplitudes[1:])) + 1
        dom_freq = float(freqs[peak_idx])
        dom_amp = float(amplitudes[peak_idx])
    else:
        dom_freq = 0.0
        dom_amp = float(amplitudes[0])

    meta = {
        "fft_length": n,
        "sampling_rate_hz": 1.0 / dt,
        "nyquist_frequency_hz": 0.5 / dt,
        "frequency_resolution_hz": float(freqs[1] - freqs[0]) if len(freqs) > 1 else 0.0,
        "dominant_frequency_hz": dom_freq,
        "dominant_amplitude": dom_amp,
        "dc_offset": dc_offset,
    }
    return freqs, amplitudes, meta


def cross_plot(
    times_x: np.ndarray,
    values_x: np.ndarray,
    times_y: np.ndarray,
    values_y: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """Synthesize cross-plot curve Y(X) from two histories X(t) and Y(t) on their common time interval.

    Returns (common_times, aligned_x, aligned_y, metadata).
    """
    times_x = np.asarray(times_x, dtype=float)
    values_x = np.asarray(values_x, dtype=float)
    times_y = np.asarray(times_y, dtype=float)
    values_y = np.asarray(values_y, dtype=float)

    t_start = max(float(times_x[0]), float(times_y[0]))
    t_end = min(float(times_x[-1]), float(times_y[-1]))

    if t_start >= t_end:
        raise CurveOperationError(
            f"No overlapping time interval between X [{times_x[0]}, {times_x[-1]}] and Y [{times_y[0]}, {times_y[-1]}]"
        )

    # Union of sample timestamps in [t_start, t_end]
    mask_x = (times_x >= t_start - 1e-12) & (times_x <= t_end + 1e-12)
    mask_y = (times_y >= t_start - 1e-12) & (times_y <= t_end + 1e-12)

    common_times = np.unique(np.concatenate([times_x[mask_x], times_y[mask_y]]))
    common_times = common_times[(common_times >= t_start) & (common_times <= t_end)]

    aligned_x = np.interp(common_times, times_x, values_x)
    aligned_y = np.interp(common_times, times_y, values_y)

    meta = {
        "common_t_start": t_start,
        "common_t_end": t_end,
        "sample_count": len(common_times),
        "x_range": [float(aligned_x.min()), float(aligned_x.max())],
        "y_range": [float(aligned_y.min()), float(aligned_y.max())],
    }
    return common_times, aligned_x, aligned_y, meta


def engineering_to_true_stress_strain(
    engineering_strain: np.ndarray,
    engineering_stress: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Convert engineering strain and engineering stress to true strain and true stress.

    Formulas:
      true_strain = ln(1 + engineering_strain)
      true_stress = engineering_stress * (1 + engineering_strain)

    Valid up to the onset of localized necking under incompressible plastic volume conservation.
    """
    eng_e = np.asarray(engineering_strain, dtype=float)
    eng_s = np.asarray(engineering_stress, dtype=float)

    if len(eng_e) != len(eng_s):
        raise CurveOperationError("Engineering strain and stress arrays must have identical length")

    if np.any(eng_e <= -1.0):
        raise CurveOperationError("Logarithmic true strain conversion requires engineering strain > -1.0")

    true_strain = np.log1p(eng_e)
    true_stress = eng_s * (1.0 + eng_e)

    meta = {
        "formula_strain": "true_strain = ln(1 + engineering_strain)",
        "formula_stress": "true_stress = engineering_stress * (1 + engineering_strain)",
        "assumption": "Uniform incompressible plastic deformation prior to localized necking",
        "peak_engineering_stress": float(np.max(eng_s)),
        "peak_true_stress": float(np.max(true_stress)),
        "max_engineering_strain": float(np.max(eng_e)),
        "max_true_strain": float(np.max(true_strain)),
    }
    return true_strain, true_stress, meta


def differentiate_curve(
    times: np.ndarray,
    values: np.ndarray,
) -> np.ndarray:
    """Compute 2nd-order interior numerical derivative of curve."""
    times = np.asarray(times, dtype=float)
    values = np.asarray(values, dtype=float)
    if len(times) < 2:
        raise CurveOperationError("Differentiation requires at least 2 points")
    edge_order = 2 if len(times) >= 3 else 1
    return np.gradient(values, times, edge_order=edge_order)


def integrate_curve(
    times: np.ndarray,
    values: np.ndarray,
    initial_value: float = 0.0,
) -> np.ndarray:
    """Compute cumulative trapezoidal integration of curve starting from initial_value."""
    times = np.asarray(times, dtype=float)
    values = np.asarray(values, dtype=float)
    if len(times) < 2:
        raise CurveOperationError("Integration requires at least 2 points")
    dt = np.diff(times)
    trapezoids = dt * (values[:-1] + values[1:]) * 0.5
    integral = np.concatenate(([float(initial_value)], float(initial_value) + np.cumsum(trapezoids)))
    return integral


def curve_summary(
    times: np.ndarray,
    values: np.ndarray,
) -> dict[str, float]:
    """Calculate key scalar summary metrics of a curve."""
    times = np.asarray(times, dtype=float)
    values = np.asarray(values, dtype=float)
    if len(times) < 2:
        raise CurveOperationError("Summary requires at least 2 points")

    duration = float(times[-1] - times[0])
    integral_val = float(integrate_curve(times, values)[-1])
    time_avg = integral_val / duration if duration > 0 else float(values[0])

    # RMS
    energy_sq = integrate_curve(times, values**2)[-1]
    rms = math.sqrt(energy_sq / duration) if duration > 0 else 0.0

    min_idx = int(np.argmin(values))
    max_idx = int(np.argmax(values))

    return {
        "minimum": float(values[min_idx]),
        "maximum": float(values[max_idx]),
        "time_at_minimum": float(times[min_idx]),
        "time_at_maximum": float(times[max_idx]),
        "peak_absolute": float(np.max(np.abs(values))),
        "duration": duration,
        "integral": integral_val,
        "time_average": time_avg,
        "rms_time_weighted": rms,
        "sample_count": float(len(times)),
    }
