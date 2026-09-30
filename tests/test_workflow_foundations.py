import csv
import math

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.engineering import align
from ls_prepost_mcp.installation_assets import declarations, evaluate_parameters, render_template
from ls_prepost_mcp.mesh_quality import element_metrics
from ls_prepost_mcp.service import Service


def curve(path, rows):
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "value"])
        w.writerows(rows)


def test_hex_quality_identifies_inversion_and_warp():
    x = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float
    )
    r = element_metrics("solid", x)
    assert r["signed_volume"] == pytest.approx(1)
    assert r["scaled_jacobian"] == pytest.approx(1)
    assert element_metrics("solid", x * np.array([-1, 1, 1]))["minimum_jacobian"] < 0
    quad = x[:4].copy()
    quad[3, 2] = 1
    assert element_metrics("shell", quad)["warpage_degrees"] > 15
    assert not element_metrics("solid", x[:6])["supported"]


def test_parameter_dependency_override_cycles_and_no_eval():
    text = "*KEYWORD\n*PARAMETER_EXPRESSION\n$Text: velocity\nRVEL, 10\n*PARAMETER_EXPRESSION\nRANG, 90\n*PARAMETER_EXPRESSION\nRVX, SIN(ANG/180*3.141592653589793)*VEL\n*END\n"
    output, items, values = render_template(text, {"vel": 20})
    assert values["VX"] == pytest.approx(20)
    assert "RVX       20" in output
    with pytest.raises(ValueError):
        evaluate_parameters(items, {"UNKNOWN": 1})
    with pytest.raises(ValueError, match="Cyclic"):
        evaluate_parameters(declarations("*PARAMETER_EXPRESSION\nRA, B\nRB, A\n"), {})
    with pytest.raises(ValueError):
        evaluate_parameters(declarations('*PARAMETER_EXPRESSION\nRA, __import__("os")\n'), {})


def test_installed_asset_filter_and_render(tmp_path, monkeypatch):
    root = tmp_path / "templates"
    f = root / "kwfilter"
    t = root / "kwtemplate" / "example"
    f.mkdir(parents=True)
    t.mkdir(parents=True)
    (f / "Materials.txt").write_text("*MAT_001\n")
    (t / "template.k").write_text("*KEYWORD\n*PARAMETER_EXPRESSION\nRT, 10\n*CONTROL_TERMINATION\n&T\n*END\n")
    monkeypatch.setenv("LSPP_TEMPLATE_ROOT", str(root))
    s = Service(Settings(tmp_path))
    assets = s.list_installation_assets()
    model = tmp_path / "input.k"
    model.write_text("*KEYWORD\n*MAT_001_TITLE\nSynthetic\n1,1,100,.3\n*END\n")
    assert len(s.apply_keyword_filter(str(model), assets["filters"][0]["id"])["matches"]) == 1
    r = s.instantiate_installed_template(assets["templates"][0]["id"], {"T": 20}, "test", native_check=False)
    assert r["status"] == "succeeded"
    assert r["data"]["parameters"]["T"] == 20


def test_engineering_units_relative_motion_and_true_assumptions(tmp_path):
    f, u, b = tmp_path / "f.csv", tmp_path / "u.csv", tmp_path / "b.csv"
    curve(f, [(0, 0), (1, 1), (2, 2)])
    curve(u, [(0, 0), (2, 0.003)])
    curve(b, [(0, 0), (2, 0.001)])
    s = Service(Settings(tmp_path))
    r = s.build_tensile_curves(str(f), str(u), 0.0001, 0.02, "kN", "m", "s", str(b), true_conversion=True)
    assert r["status"] == "succeeded", r
    with open(r["artifacts"][0]["path"]) as file:
        rows = list(csv.DictReader(file))
    last = rows[-1]
    assert float(last["force_N"]) == 2000
    assert float(last["displacement_mm"]) == pytest.approx(2)
    assert float(last["engineering_stress_MPa"]) == pytest.approx(20)
    assert float(last["engineering_strain"]) == pytest.approx(0.1)
    assert float(last["true_strain_uniform"]) == pytest.approx(math.log(1.1))
    assert r["data"]["assumptions"]


def test_no_extrapolation_and_zero_energy_undefined(tmp_path):
    with pytest.raises(ValueError):
        align([(np.array([0, 1]), np.array([0, 1])), (np.array([2, 3]), np.array([0, 1]))])
    a, b = tmp_path / "ke.csv", tmp_path / "ie.csv"
    curve(a, [(0, 0), (1, 1)])
    curve(b, [(0, 0), (1, 100)])
    r = Service(Settings(tmp_path)).assess_energy_balance(str(a), str(b), "J")
    assert r["status"] == "succeeded"
    assert r["data"]["undefined_rows"] == 1 and not r["data"]["quasistatic_certified"]
    assert r["data"]["hourglass_exceedances"] is None
    with open(r["artifacts"][0]["path"]) as file:
        assert all(row["hourglass"] == "" and row["hg_ie_ratio"] == "" for row in csv.DictReader(file))


def test_duplicate_merge_rewrites_connectivity(tmp_path):
    pytest.importorskip("ansys.dyna.core")
    model = tmp_path / "mesh.k"
    model.write_text(
        "*KEYWORD\n*NODE\n1,0,0,0\n2,1,0,0\n3,1,1,0\n4,0,1,0\n5,0,0,0\n"
        "*ELEMENT_SHELL\n10,1,5,2,3,4\n*SET_NODE_LIST\n         7\n         5         2\n*END\n"
    )
    before = model.read_bytes()
    r = Service(Settings(tmp_path)).merge_duplicate_mesh_nodes(str(model), 1e-8, "mm", native_check=False)
    assert r["status"] == "succeeded", r
    assert r["data"]["removed_count"] == 1 and r["data"]["node_count"] == 4
    assert model.read_bytes() == before
