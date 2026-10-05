"""I04 UU evidence checks; native lane failures are retained, not relabeled."""

import json
from pathlib import Path

import pytest

from tools.remote_regression import capture, identity, read_json, targets, verify_cell

pytestmark = [pytest.mark.native, pytest.mark.gui, pytest.mark.remote]


@pytest.fixture(scope="module")
def remote_evidence(pytestconfig):
    if not pytestconfig.getoption("--run-native"):
        pytest.skip("Remote native probes are opt-in")
    unavailable = pytest.fail if pytestconfig.getoption("--native-strict") else pytest.skip
    supplied = pytestconfig.getoption("--remote-evidence")
    confirmation_path = pytestconfig.getoption("--remote-confirmation")
    if not confirmation_path:
        unavailable("Provide the operator's external UU window confirmation file")
    confirmation = read_json(confirmation_path)
    if pytestconfig.getoption("--remote-capture"):
        if supplied:
            pytest.fail("Choose a new capture or existing evidence, not both")
        if not pytestconfig.getoption("--native-gui"):
            unavailable("Remote capture requires the approved GUI/UU window")
        exe = pytestconfig.getoption("--native-executable")
        old = pytestconfig.getoption("--native-executable-410")
        fixture = pytestconfig.getoption("--native-fixture")
        if not all((exe, old, fixture)):
            unavailable("Capture requires both installations and the original synthetic fixture")
        supplied = pytestconfig._native_root / "remote-capture"
        capture(supplied, exe, old, fixture, confirmation, pytestconfig.getoption("--remote-timeout"))
        confirmation = read_json(confirmation_path)
    if not supplied:
        unavailable("Provide --remote-evidence or explicitly request --remote-capture")
    if confirmation.get("phase") != "confirmed":
        unavailable("Native capture is saved; operator must confirm the completed UU interval before verification")
    return Path(supplied), confirmation


@pytest.mark.parametrize("target", targets(), ids=identity)
def test_remote_probe_evidence_and_window(remote_evidence, target, pytestconfig, request):
    root, confirmation = remote_evidence
    result = verify_cell(root, target, confirmation)
    output = pytestconfig._native_root / (identity(target) + ".json")
    output.write_text(json.dumps(result, indent=2), encoding="utf8")
    request.node.user_properties.append(("native_evidence", str(output)))
