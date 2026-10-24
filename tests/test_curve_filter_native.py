"""Q07 native compatibility; old J211 differences retained, explicit profile must agree."""
import hashlib
import json

import numpy as np
import pytest

from ls_prepost_mcp.domain.results.curves import sae_filter
from ls_prepost_mcp.gui_curves import native_plot_values, verify_curve_readback, xy_text
from ls_prepost_mcp.native import commands as nc
from ls_prepost_mcp.runner import run_batch
from tests.test_save_model_native import installation as installation

pytestmark = pytest.mark.native


@pytest.mark.parametrize("cfc", [60, 600])
@pytest.mark.parametrize("unit,scale,native_unit", [("s", 1., "sec"), ("ms", 1000., "msec")])
def test_sae_native_full_record_and_interior(installation, pytestconfig, cfc, unit, scale, native_unit):
    if not pytestconfig.getoption("--run-native"):
        pytest.skip("Explicit --run-native opt-in required")
    executable, binary, config_sha = installation
    root = pytestconfig._native_root / f"sae-{cfc}-{unit}"
    root.mkdir()
    seconds = np.arange(4001) * .00005
    times = seconds * scale
    # A smooth low-frequency component plus a deliberately suppressed harmonic.
    # Fix these inputs before looking at the native output; do not tune questions
    # or tolerances to make a mismatch pass.
    values = 20 * np.sin(2 * np.pi * 5 * seconds) + .5 * np.sin(2 * np.pi * 3000 * seconds)
    xy = np.column_stack((times, values))
    source = root / "input.xy"
    source.write_text(xy_text([dict(values=xy)]), encoding="ascii")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    command = f"xyplot 1 filter sae {cfc} {native_unit} 0"
    nc.write_cfile(root / "commands.cfile", [nc.open_xydata("input.xy"), "newplot", 'show "input.xy~1" 0',
        nc.save_xypair("control.xy", 1), command, nc.save_xypair("filtered.xy", 1), "exit"])
    execution = run_batch(executable, root / "commands.cfile", root, timeout=60,
                          graphics=False, operation="q07_sae_native_reference")
    (root / "engine-result.json").write_text(execution.model_dump_json(), encoding="utf8")
    assert execution.error is None and execution.status == "unverified", execution.error
    assert execution.data["graphics"] is False and not execution.data["timed_out"]
    control = verify_curve_readback(root / "control.xy", [xy])[0]
    actual_control = np.loadtxt(root / "control.xy", skiprows=1)
    actual = np.loadtxt(root / "filtered.xy", skiprows=1)
    assert actual.shape == xy.shape and np.isfinite(actual).all()
    np.testing.assert_array_equal(actual[:, 0], actual_control[:, 0])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha
    # Use the actual imported float32 ordinate with the declared uniform input
    # time grid. Native stored float32 times themselves have quantization jitter;
    # do not silently reinterpret that jitter as nonuniform input sampling.
    input_values = native_plot_values(xy)[:, 1]
    comparisons = {}
    for padding in ["odd", "constant", "lsprepost"]:
        reference = sae_filter(times, input_values, cfc, t_unit=unit,
            **({"convention":"lsprepost"} if padding == "lsprepost" else {"padding":padding})).y
        errors = np.abs(actual[:, 1] - reference)
        atol = 1e-6 * float(np.max(np.abs(reference)))
        comparisons[padding] = dict(agrees=bool(np.allclose(actual[:, 1], reference, rtol=2e-5, atol=atol)),
            max_absolute_error=float(errors.max()), interior_max_absolute_error=float(errors[1000:-1000].max()),
            endpoint_errors=[float(errors[0]), float(errors[-1])], rtol=2e-5, atol=atol,
            formula="explicit " + padding + " profile; see product source identity")
    context = pytestconfig._native_identity
    result = dict(actual_git_revision=context["actual_git_head"], working_tree_dirty=context["working_tree_dirty"],
        git_diff_sha256=context["git_diff_sha256"], executable=binary, source_config_sha256=config_sha,
        cfc=cfc, time_unit=unit, native_command=command, trailing_option=0,
        trailing_option_semantics="not independently read back", force_zero_start=None, samples=len(times),
        control=control, comparisons=comparisons, source_sha256=source_sha,
        filtered_sha256=hashlib.sha256((root / "filtered.xy").read_bytes()).hexdigest(),
        verdict="agrees" if comparisons["lsprepost"]["agrees"] else "mismatch",
        scope="Frozen synthetic waveform only; no universal native filter equivalence or Butterworth claim")
    (root / "comparison.json").write_text(json.dumps(result,separators=(",", ":"))+"\n", encoding="utf8")
    assert comparisons["lsprepost"]["agrees"], comparisons
