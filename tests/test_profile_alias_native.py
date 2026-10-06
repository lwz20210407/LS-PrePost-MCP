"""I03: named installation profiles dispatch a real, isolated batch operation."""

from dataclasses import replace

import pytest

from ls_prepost_mcp.service import Service
from tests.test_engine_native import native_case as native_case

pytestmark = pytest.mark.native


def test_named_installation_profile_runs_native_inspection(native_case):
    original, source = native_case
    executable = original.settings.native_executable()
    service = Service(replace(original.settings, profiles={"local-install": executable}))
    result = service.run_on_version("local-install", "inspect_model", {"model": str((source / "input.k").resolve())})
    assert result["status"] == "succeeded", result
    assert result["installation_profile"] == "local-install"
    assert result["data"]["counts"]["nodes"] == 8
    assert result["executable"]["path"] == str(executable)
    assert "-nographics" in result["process"]["argv"]
    assert service.settings.native_executable() == executable
