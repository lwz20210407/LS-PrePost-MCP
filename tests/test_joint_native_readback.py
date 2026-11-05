"""P12 opt-in single-file Joint definition export roundtrip; not motion/typed recognition."""

import pytest

from ls_prepost_mcp.native.versions import require_capability, require_installation
from tests.test_save_model_native import installation as installation
from tools.verify_p12_joint_roundtrip import prepare_case, verify_native

pytestmark = pytest.mark.native


@pytest.mark.parametrize("case", ["pilot", "nine_types", "body_modes"])
def test_native_joint_definition_roundtrip(installation, pytestconfig, record_property, case):
    executable, binary, _ = installation
    if binary["version"] not in ("4.13", "4.10"):
        pytest.fail("P12 definition roundtrip is registered only for explicit 4.13/4.10 runs")
    policy = require_installation(executable, version=binary["version"])
    assert policy["version_source"] == "file_version_resource"
    require_capability(executable, "batch")
    prepared = prepare_case(case, pytestconfig._native_root / case, executable)
    proof = verify_native(prepared, pytestconfig._native_identity)
    record_property("evidence", str(prepared["directory"] / "comparison.json"))
    assert proof["status"] == "passed" and proof["native_executed"] is True
    assert proof["typed_joint_recognition"] == "unverified" and proof["motion_verification"] == "not_run"
    assert proof["original_unchanged"] and proof["edited_unchanged"] and proof["saved_unchanged"]
    assert proof["configuration_unchanged"] and proof["executable_unchanged"] and proof["checkout_unchanged"]
    assert proof["saved_sha256"] == proof["staged_input_sha256"]
