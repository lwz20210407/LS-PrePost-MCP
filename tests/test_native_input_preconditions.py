"""I04 headless input checks before the more expensive GUI acceptance batch."""

from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from tools.native_regression import resolve_value

pytestmark = pytest.mark.native


@pytest.mark.parametrize("case,key,kind,counts", [
    ("stale_model_regression.native", "keyword", "keyword", dict(nodes=2957, elements=3005)),
    ("public_motion_acceptance.native", "keyword", "keyword", dict(nodes=6, elements=2)),
    ("public_nodal_load_acceptance.native", "keyword", "keyword", dict(nodes=41, elements=21)),
    ("gui_post_workflow_acceptance.native", "source", "d3plot", None),
])
def test_native_input_precondition(case, key, kind, counts, pytestconfig, request, tmp_path):
    if not pytestconfig.getoption("--run-native"):
        pytest.skip("Native fixture preflight is opt-in")
    native_inputs = request.getfixturevalue("native_inputs")
    if case not in native_inputs or not pytestconfig.getoption("--native-executable"):
        unavailable = pytest.fail if pytestconfig.getoption("--native-strict") else pytest.skip
        unavailable("Native fixture inputs and executable are required")
    source = Path(resolve_value(native_inputs[case][key])).resolve(strict=True)
    service = Service(Settings(tmp_path, Path(pytestconfig.getoption("--native-executable")), (source.parent,), 90))
    result = service.inspect_model(str(source), kind)
    assert result["status"] == "succeeded", result.get("error")
    observed = result["data"]["counts"]
    if counts:
        assert all(observed[name] == expected for name, expected in counts.items()), observed
    else:
        assert 0 < observed["nodes"] <= 20000 and observed["states"] >= 3, observed
