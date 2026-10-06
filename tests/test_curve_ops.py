"""Tests for Q07 curve operations: SAE J211 filter, resampling, FFT, cross plot, and stress-strain."""

import json
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.curve_ops import (
    CurveOperationError,
    compute_fft,
    cross_plot,
    curve_summary,
    differentiate_curve,
    engineering_to_true_stress_strain,
    integrate_curve,
    resample_curve,
    sae_j211_filter,
)
from ls_prepost_mcp.service import Service


def test_sae_j211_filter_preserves_low_freq_and_eliminates_noise():
    # 10 kHz sampling for 0.05 s
    dt = 1e-4
    times = np.arange(0.0, 0.05, dt)
    # Fundamental 30 Hz signal + 3000 Hz severe impact noise
    pure_signal = 100.0 * np.sin(2.0 * np.pi * 30.0 * times)
    noise = 40.0 * np.sin(2.0 * np.pi * 3000.0 * times)
    measured = pure_signal + noise

    # Filter with CFC 60 (fc = 100 Hz)
    filtered, meta = sae_j211_filter(times, measured, cfc=60)

    assert meta["filter_standard"] == "SAE J211 / ISO 6487"
    assert meta["cfc"] == 60
    assert meta["cutoff_frequency_hz"] == 100.0
    assert meta["phase_shift"].startswith("zero")

    # High frequency noise is suppressed by > 90%
    noise_residual = np.std(filtered[50:-50] - pure_signal[50:-50])
    orig_noise_std = np.std(noise)
    assert noise_residual < 0.15 * orig_noise_std

    # Peak timing is preserved without lag (zero phase shift)
    peak_pure_idx = np.argmax(pure_signal[:150])
    peak_filtered_idx = np.argmax(filtered[:150])
    assert abs(peak_pure_idx - peak_filtered_idx) <= 2


def test_resample_curve_linear_interpolation_and_no_extrapolation():
    # Non-uniform timestamps
    times = np.array([0.0, 0.05, 0.09, 0.2, 0.35, 0.5])
    # Exact linear function y = 10 * t + 5
    values = 10.0 * times + 5.0

    # Resample with uniform dt = 0.1
    new_t, new_v, meta = resample_curve(times, values, dt=0.1)

    assert len(new_t) == 6  # 0.0, 0.1, 0.2, 0.3, 0.4, 0.5
    assert np.allclose(new_v, 10.0 * new_t + 5.0, atol=1e-12)
    assert meta["original_sample_count"] == 6

    # Extrapolation beyond range must fail
    with pytest.raises(CurveOperationError, match="exceed curve interval"):
        resample_curve(times, values, target_times=np.array([-0.01, 0.2, 0.4]))


def test_fft_identifies_dominant_frequencies():
    dt = 0.001  # 1000 Hz sampling
    times = np.arange(0.0, 1.0, dt)
    # 50 Hz dominant (amp 10.0) + 120 Hz secondary (amp 4.0)
    signal = 10.0 * np.sin(2.0 * np.pi * 50.0 * times) + 4.0 * np.sin(2.0 * np.pi * 120.0 * times)

    freqs, amps, meta = compute_fft(times, signal)

    assert meta["sampling_rate_hz"] == 1000.0
    assert meta["nyquist_frequency_hz"] == 500.0
    assert meta["dominant_frequency_hz"] == pytest.approx(50.0, abs=1.0)
    assert meta["dominant_amplitude"] == pytest.approx(10.0, rel=0.05)


def test_cross_plot_merges_two_time_histories():
    t1 = np.linspace(0.0, 1.0, 101)
    v1 = 20.0 * t1  # Displacement X(t)

    t2 = np.linspace(0.2, 1.2, 101)
    v2 = 500.0 * t2  # Force Y(t)

    t_com, x_aln, y_aln, meta = cross_plot(t1, v1, t2, v2)

    # Common time interval is [0.2, 1.0]
    assert meta["common_t_start"] == pytest.approx(0.2)
    assert meta["common_t_end"] == pytest.approx(1.0)
    assert np.allclose(x_aln, 20.0 * t_com)
    assert np.allclose(y_aln, 500.0 * t_com)


def test_engineering_to_true_stress_strain():
    eng_strain = np.array([0.0, 0.05, 0.10, 0.20])
    eng_stress = np.array([0.0, 200.0, 350.0, 450.0])

    true_strain, true_stress, meta = engineering_to_true_stress_strain(eng_strain, eng_stress)

    # True strain = ln(1 + e)
    assert true_strain[0] == 0.0
    assert true_strain[3] == pytest.approx(np.log(1.20))

    # True stress = s * (1 + e)
    assert true_stress[0] == 0.0
    assert true_stress[3] == pytest.approx(450.0 * 1.20)
    assert "incompressible" in meta["assumption"].lower()

    # Strain <= -1.0 must fail
    with pytest.raises(CurveOperationError, match="engineering strain > -1.0"):
        engineering_to_true_stress_strain(np.array([-1.05]), np.array([100.0]))


def test_calculus_and_summary():
    times = np.linspace(0.0, 2.0, 201)
    # y = 3 * t^2
    values = 3.0 * times**2

    # Derivative dy/dt = 6 * t
    deriv = differentiate_curve(times, values)
    assert np.allclose(deriv[2:-2], 6.0 * times[2:-2], rtol=1e-3)

    # Integral of 6 * t is 3 * t^2
    integ = integrate_curve(times, deriv)
    assert np.allclose(integ, values, atol=0.05)

    stats = curve_summary(times, values)
    assert stats["minimum"] == 0.0
    assert stats["maximum"] == pytest.approx(12.0)
    assert stats["duration"] == pytest.approx(2.0)


def test_service_curve_ops_end_to_end(tmp_path):
    service = Service(Settings(tmp_path))

    # Create dummy curve file
    times = np.linspace(0.0, 0.1, 101)
    values = 50.0 * np.sin(2.0 * np.pi * 20.0 * times) + 10.0 * np.sin(2.0 * np.pi * 1000.0 * times)
    curve_csv = tmp_path / "raw_curve.csv"
    with curve_csv.open("w", encoding="utf-8") as f:
        f.write("time,force\n")
        for t, v in zip(times, values):
            f.write(f"{t:.6e},{v:.6e}\n")

    res = service.curve_ops(str(curve_csv), operation="sae_filter", cfc=60, units="kN")

    assert res["status"] == "succeeded"
    data = res["data"]
    assert data["operation"] == "sae_filter"
    assert data["input_units"] == "kN"

    # Artifacts check
    artifacts = res["artifacts"]
    csv_art = next(a for a in artifacts if a["kind"] == "csv")
    json_art = next(a for a in artifacts if a["kind"] == "json")

    assert Path(csv_art["path"]).is_file()
    assert Path(json_art["path"]).is_file()

    summary_json = json.loads(Path(json_art["path"]).read_text(encoding="utf-8"))
    assert summary_json["filter_metadata"]["cfc"] == 60
