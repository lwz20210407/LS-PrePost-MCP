"""Explicitly opted-in installed recipe reopen with entirely original input files."""

import os
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json, fingerprint
from ls_prepost_mcp.service import Service

pytestmark = pytest.mark.native


def test_original_installed_template_reopens_in_batch(tmp_path, monkeypatch, pytestconfig):
    if not pytestconfig.getoption("--run-native"):
        pytest.skip("Native installed recipe requires explicit --run-native and a project lease")
    executable = pytestconfig.getoption("--native-executable") or os.environ.get("LSPP_ENGINE_EXECUTABLE")
    if not executable:
        pytest.fail("Explicit native executable required")
    root = tmp_path / "installation"
    template = root / "kwtemplate" / "Original termination" / "template.k"
    template.parent.mkdir(parents=True)
    template.write_text("*KEYWORD\n*PARAMETER\nRT, 1\n*CONTROL_TERMINATION\n&T\n*END\n", encoding="utf8")
    model = tmp_path / "input.k"
    model.write_text("*KEYWORD\n*NODE\n1,0,0,0\n2,1,0,0\n3,1,1,0\n4,0,1,0\n"
                     "*ELEMENT_SHELL\n1,1,1,2,3,4\n*END\n", encoding="utf8")
    before = [fingerprint(path) for path in (template, model)]
    monkeypatch.setenv("LSPP_TEMPLATE_ROOT", str(root))
    service = Service(Settings(tmp_path, Path(executable), timeout=60))
    row = next(item for item in service.find_recipe("Original termination", include_candidates=True)
               if item.get("adapter_kind") == "installed_template")
    result = service.run_recipe(row["reference"], {"units": "mm-ms", "values": {"T": 2}, "native_check": True},
                                model=str(model))
    atomic_json(tmp_path / "installed-verdict.json", result)
    assert result["status"] == "succeeded", result
    assert result["data"]["native_mesh_verified"] is True
    assert result["data"]["native_counts"]["nodes"] == 4
    assert result["data"]["native_counts"]["elements"] == 1
    assert result["data"]["solver_validated"] is False
    assert result["data"]["parameters"] == {"T": 2}
    assert result["data"]["recipe"]["versions_verified"] == []
    assert before == [fingerprint(path) for path in (template, model)]
    assert all(item["sha256"] == fingerprint(Path(item["path"]))["sha256"] for item in result["artifacts"])
