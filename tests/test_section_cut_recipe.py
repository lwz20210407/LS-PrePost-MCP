"""Tests for Q10 section cut recipe and SECFORC force history verification."""

import numpy as np
import pytest

from ls_prepost_mcp.automation.recipes import ROOT, load_recipe, validate_parameters
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.section import (
    check_secforc_consistency,
    compare_section_forces,
    read_ascii_secforc,
    read_secforc,
)
from ls_prepost_mcp.service import Service


def test_section_cut_recipe_loading_and_parameter_validation():
    recipe, code, path, identities = load_recipe(ROOT / "section_cut_fringe/recipe.yaml")
    assert recipe.id == "section_cut_fringe"
    assert recipe.task_id == "Q10"
    assert recipe.channel == "cfile"
    assert recipe.input_kind == "d3plot"
    assert "splane create" in code

    # Default parameters
    defaults = validate_parameters(recipe.parameters, {})
    assert defaults["px"] == 0.0
    assert defaults["nx"] == 1.0
    assert defaults["state"] == 1

    # Custom valid parameters
    custom = validate_parameters(recipe.parameters, {
        "px": 15.5, "py": 2.0, "pz": -3.0,
        "nx": 0.0, "ny": 1.0, "nz": 0.0,
        "state": 5, "fringe_code": 2,
    })
    assert custom["px"] == 15.5
    assert custom["ny"] == 1.0
    assert custom["state"] == 5

    # Rejection of invalid parameters
    with pytest.raises(ValueError):
        validate_parameters(recipe.parameters, {"unknown_param": 123})
    with pytest.raises(ValueError):
        validate_parameters(recipe.parameters, {"state": 0})  # minimum is 1
    with pytest.raises(ValueError):
        validate_parameters(recipe.parameters, {"px": "not_a_number"})


def test_section_cut_fringe_recipe_execution(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))
    model_path = tmp_path / "d3plot"
    model_path.write_bytes(b"dummy d3plot binary")

    executed_code = []

    def mock_run_script(channel, rendered, **kwargs):
        executed_code.append(rendered)
        out_png = tmp_path / "section_fringe.png"
        out_png.write_bytes(b"\x89PNG\r\n\x1a\nfake image bytes")
        import hashlib
        sha = hashlib.sha256(b"fake image bytes").hexdigest()
        return {
            "status": "succeeded",
            "operation": "run_script",
            "data": {"rendered_source": rendered},
            "artifacts": [{"path": str(out_png), "kind": "png", "sha256": sha}],
            "evidence": [],
            "warnings": [],
        }

    monkeypatch.setattr(service, "run_script", mock_run_script)

    result = service.run_recipe(
        "section_cut_fringe",
        parameters={"px": 10.0, "py": 20.0, "pz": 30.0, "nx": 0.0, "ny": 0.0, "nz": 1.0, "state": 3, "fringe_code": 1},
        model=str(model_path),
        file_type="d3plot",
    )

    assert result["status"] == "succeeded"
    assert len(executed_code) == 1
    cfile = executed_code[0]
    assert "state 3" in cfile
    assert "fringe 1" in cfile
    assert "splane create 10.0 20.0 30.0 0.0 0.0 1.0" in cfile
    assert 'print png "section_fringe.png" opaque enlisted "OGL1x1"' in cfile


def test_ascii_secforc_parsing_and_consistency(tmp_path):
    secforc_file = tmp_path / "secforc"
    content = """
$ LS-DYNA SECFORC output test file
 cross section id:       1
  time        x-force     y-force     z-force     total-force   x-moment    y-moment    z-moment    total-moment   x-centroid  y-centroid  z-centroid  area
  0.0000E+00  0.0000E+00  0.0000E+00  0.0000E+00  0.0000E+00   0.0000E+00  0.0000E+00  0.0000E+00  0.0000E+00     1.0000E+01  0.0000E+00  5.0000E+00  1.0000E+02
  1.0000E-03  3.0000E+02  4.0000E+02  0.0000E+00  5.0000E+02   1.0000E+01  2.0000E+01  0.0000E+00  2.2360E+01     1.0000E+01  0.0000E+00  5.0000E+00  1.0000E+02
  2.0000E-03  6.0000E+02  8.0000E+02  0.0000E+00  1.0000E+03   2.0000E+01  4.0000E+01  0.0000E+00  4.4721E+01     1.0000E+01  0.0000E+00  5.0000E+00  1.0000E+02

 cross section id:       2
  time        x-force     y-force     z-force     total-force
  0.0000E+00  0.0000E+00  0.0000E+00  0.0000E+00  0.0000E+00
  1.0000E-03  0.0000E+00  0.0000E+00  1.0000E+02  1.0000E+02
  2.0000E-03  0.0000E+00  0.0000E+00  2.0000E+02  2.0000E+02
"""
    secforc_file.write_text(content, encoding="utf-8")

    data = read_ascii_secforc(secforc_file)
    assert 1 in data and 2 in data

    sec1 = data[1]
    assert np.allclose(sec1["time"], [0.0, 1e-3, 2e-3])
    assert np.allclose(sec1["total_force"], [0.0, 500.0, 1000.0])
    assert np.allclose(sec1["resultant_force"], [0.0, 500.0, 1000.0])
    assert np.allclose(sec1["area"], [100.0, 100.0, 100.0])

    # Consistency check
    consistency = check_secforc_consistency(sec1)
    assert consistency["consistent"] is True
    assert consistency["max_absolute_difference"] < 1e-10

    # Auto-detection read_secforc
    auto_data = read_secforc(secforc_file)
    assert 1 in auto_data


def test_compare_section_forces_matches_secforc(tmp_path):
    secforc_file = tmp_path / "secforc"
    content = """
 cross section id:       1
  time        x-force     y-force     z-force     total-force
  0.0000E+00  0.0000E+00  0.0000E+00  0.0000E+00  0.0000E+00
  1.0000E-03  3.0000E+02  4.0000E+02  0.0000E+00  5.0000E+02
  2.0000E-03  6.0000E+02  8.0000E+02  0.0000E+00  1.0000E+03
"""
    secforc_file.write_text(content, encoding="utf-8")

    # Match test
    cut_measured = {
        "time": [0.0, 1e-3, 2e-3],
        "total_force": [0.0, 500.0, 1000.0],
    }
    comparison = compare_section_forces(cut_measured, secforc_file, section_id=1)
    assert comparison["consistent_with_secforc"] is True
    assert comparison["max_absolute_difference"] < 1e-10

    # Mismatch test
    cut_divergent = {
        "time": [0.0, 1e-3, 2e-3],
        "total_force": [0.0, 450.0, 900.0],  # 10% discrepancy
    }
    comparison_bad = compare_section_forces(cut_divergent, secforc_file, section_id=1, rtol=1e-3)
    assert comparison_bad["consistent_with_secforc"] is False
    assert comparison_bad["max_relative_difference"] > 0.05


def test_binout_secforc_with_lasso(tmp_path):
    pytest.importorskip("lasso.dyna")
    from lasso.dyna.lsda_py3 import Lsda

    binout_path = tmp_path / "binout0000"
    f = Lsda(str(binout_path), "w")
    f.cd("/secforc/metadata", 1)
    f.write("ids", Lsda.I4, [10, 20])
    times = [0.0, 0.5, 1.0]
    for k, t in enumerate(times, start=1):
        f.cd(f"/secforc/d{k:06d}", 1)
        f.write("time", Lsda.R8, [t])
        f.write("x_force", Lsda.R8, [100.0 * t, 200.0 * t])
        f.write("y_force", Lsda.R8, [0.0, 0.0])
        f.write("z_force", Lsda.R8, [0.0, 0.0])
        f.write("total_force", Lsda.R8, [100.0 * t, 200.0 * t])
    f.close()

    sec_data = read_secforc(tmp_path)
    assert 10 in sec_data and 20 in sec_data
    assert np.allclose(sec_data[10]["total_force"], [0.0, 50.0, 100.0])
    assert np.allclose(sec_data[20]["total_force"], [0.0, 100.0, 200.0])
    chk = check_secforc_consistency(sec_data[10])
    assert chk["consistent"] is True
