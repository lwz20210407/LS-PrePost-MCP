"""Every existing tools/run_* acceptance entrypoint is collected here."""

import json

import pytest

from tools.native_regression import cases, run_case


@pytest.mark.native
@pytest.mark.parametrize("acceptance_case", [
    pytest.param(case, id=case.id, marks=[pytest.mark.gui] if case.gui else []) for case in cases()
], indirect=True)
def test_legacy_acceptance(acceptance_case, pytestconfig, request):
    case, argv, directory = acceptance_case
    result = run_case(case, argv, directory, pytestconfig.getoption("--native-timeout"))
    (directory / "verified.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    request.node.user_properties.append(("native_evidence", str(directory / "verified.json")))
