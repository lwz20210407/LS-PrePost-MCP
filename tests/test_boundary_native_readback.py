"""Opt-in serial P05 keyword retention, not typed boundary or physical validation."""
import pytest

from tests.test_save_model_native import installation as installation
from tools.verify_p05_boundary_roundtrip import prepare_case, verify_native

pytestmark = pytest.mark.native


def test_native_boundary_definition_roundtrip(installation, pytestconfig, record_property):
    executable, binary, _ = installation
    if binary["version"] not in ("4.13", "4.10"):
        pytest.fail("P05 fixture is registered only for explicit 4.13/4.10 runs")
    prepared = prepare_case(pytestconfig._native_root / "nine-types", executable)
    proof = verify_native(prepared, pytestconfig._native_identity)
    record_property("evidence", str(prepared["directory"] / "comparison.json"))
    assert proof["status"] == "passed" and proof["native_executed"] is True
    assert proof["typed_boundary_recognition"] == "unverified" and proof["physical_response"] == "not_run"
    assert proof["differences"] == [] and proof["boundary_count"] == 9
    assert proof["original_unchanged"] and proof["edited_unchanged"] and proof["saved_unchanged"]
    assert proof["source_configuration_unchanged"] and proof["executable_unchanged"] and proof["checkout_unchanged"]
    assert proof["saved_sha256"] == proof["staged_input_sha256"]
