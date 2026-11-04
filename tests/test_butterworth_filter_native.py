"""Q07 serial, opt-in full-record BW comparison on fixed engineering-shaped inputs."""
import hashlib
import json

import numpy as np
import pytest

from ls_prepost_mcp.domain.results.curves import butterworth_filter
from ls_prepost_mcp.gui_curves import native_plot_values, verify_curve_readback, xy_text
from ls_prepost_mcp.native import commands as nc
from ls_prepost_mcp.runner import run_batch
from tests.test_save_model_native import installation as installation

pytestmark = pytest.mark.native


def waveform(case):
    """Freeze inputs independently of the native outputs and selected numerical profile."""
    if case == "short_impulse":
        t = np.arange(41) * .00005
        y = np.zeros(t.size)
        y[1], y[16], y[-2] = 1., -.5, .75
    elif case == "offset_step":
        t = np.arange(3001) * .0001
        y = 300 + 120 * (t >= .08) - 45 * (t >= .2) + 2 * np.sin(2 * np.pi * 2300 * t)
    elif case == "impact_ringdown":
        t = np.arange(6001) * .00005
        pulse = (t > .04) & (t < .08)
        y = np.zeros(t.size)
        y[pulse] = 2000 * np.sin(np.pi * (t[pulse] - .04) / .04) ** 2
        after = t >= .08
        y[after] = 500 * np.exp(-(t[after] - .08) / .035) * np.sin(2 * np.pi * 120.7 * (t[after] - .08))
        y += 5 * np.cos(2 * np.pi * 3500.5 * t + .7)
    else:
        assert case == "sine_mix"
        t = np.arange(4001) * .00005
        y = 20 * np.sin(2 * np.pi * 5 * t) + .5 * np.sin(2 * np.pi * 3000 * t)
    return t, y


@pytest.mark.parametrize("case", ["short_impulse", "sine_mix", "offset_step", "impact_ringdown"])
@pytest.mark.parametrize("frequency", [60, 600])
@pytest.mark.parametrize("unit,scale,native_unit", [("s", 1., "sec"), ("ms", 1000., "msec")])
def test_native_butterworth_full_record(installation, pytestconfig, case, frequency, unit, scale, native_unit):
    executable, binary, config_sha = installation
    root = pytestconfig._native_root / f"bw-{case}-{frequency}-{unit}"
    root.mkdir()
    seconds, values = waveform(case)
    times = seconds * scale
    xy = np.column_stack((times, values))
    source = root / "input.xy"
    source.write_text(xy_text([dict(values=xy)]), encoding="ascii")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    command = f"xyplot 1 filter bw {frequency} {native_unit} 0"
    nc.write_cfile(root / "commands.cfile", [nc.open_xydata("input.xy"), "newplot", 'show "input.xy~1" 0',
        nc.save_xypair("control.xy", 1), command, nc.save_xypair("filtered.xy", 1), "exit"])
    result = run_batch(executable, root / "commands.cfile", root, timeout=60, graphics=False,
                       operation="q07_butterworth_native_reference")
    (root / "engine-result.json").write_text(result.model_dump_json(), encoding="utf8")
    assert result.status == "unverified" and result.error is None, result.error
    assert result.data["graphics"] is False and not result.data["timed_out"]
    control = verify_curve_readback(root / "control.xy", [xy])[0]
    actual = np.loadtxt(root / "filtered.xy", skiprows=1)
    imported = np.loadtxt(root / "control.xy", skiprows=1)
    assert actual.shape == xy.shape and np.isfinite(actual).all()
    np.testing.assert_array_equal(actual[:, 0], imported[:, 0])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha
    expected = butterworth_filter(times, native_plot_values(xy)[:, 1], 2, frequency,
                                  t_unit=unit, convention="lsprepost")
    error = np.abs(actual[:, 1] - expected.y)
    atol = 1e-6 * float(np.max(np.abs(expected.y)))
    agrees = bool(np.allclose(actual[:, 1], expected.y, rtol=2e-5, atol=atol))
    identity = pytestconfig._native_identity
    report = dict(actual_git_revision=identity["actual_git_head"],
        working_tree_dirty=identity["working_tree_dirty"], git_diff_sha256=identity["git_diff_sha256"],
        executable=binary, source_config_sha256=config_sha, case=case, samples=len(times),
        nominal_frequency_hz=frequency, time_unit=unit, native_command=command, trailing_option=0,
        trailing_option_semantics="not independently read back", control=control,
        profile=expected.meta["parameters"], rtol=2e-5, atol=atol,
        max_absolute_error=float(error.max()), endpoint_errors=[float(error[0]), float(error[-1])],
        source_sha256=source_sha, filtered_sha256=hashlib.sha256((root / "filtered.xy").read_bytes()).hexdigest(),
        verdict="agrees" if agrees else "mismatch",
        scope="Fixed synthetic engineering-shaped waveforms; full stored record, including both endpoints")
    (root / "comparison.json").write_text(json.dumps(report, separators=(",", ":")) + "\n", encoding="utf8")
    assert agrees, report
