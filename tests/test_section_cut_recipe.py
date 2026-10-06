"""Tests for Q10 section cut recipe and SECFORC force history verification."""

import os
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.automation.recipes import ROOT, load_recipe, validate_parameters
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.results.section import (
    SectionForceError,
    check_secforc_consistency,
    compare_section_forces,
    read_ascii_secforc,
    read_binout_secforc,
)
from ls_prepost_mcp.service import Service


def corpus_root() -> Path | None:
    env_dir = os.environ.get("LSPP_CORPUS_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir)
    default_dir = Path(r"F:\PythonWoking\temp\20260930-lsprepost-mcp-development\corpus")
    if default_dir.is_dir():
        return default_dir
    return None


def test_section_cut_recipe_loading_and_parameter_validation(tmp_path):
    recipe, code, path, identities = load_recipe(ROOT / "section_cut_fringe/recipe.yaml")
    assert recipe.id == "section_cut_fringe"
    assert recipe.task_id == "Q10"
    assert recipe.channel == "cfile"
    assert recipe.input_kind == "d3plot"
    assert "splane create" in code

    # Unverified status check: find_recipe must not return it as T2 before native verification (P0-3)
    assert recipe.versions_verified == []
    assert recipe.execution_modes["c_nographics"]["status"] == "unverified"
    service = Service(Settings(tmp_path))
    t2_hits = service.find_recipe(query="section_cut_fringe", task_id="Q10")
    assert len(t2_hits) == 0  # not returned as verified T2

    candidate_hits = service.find_recipe(query="section_cut_fringe", task_id="Q10", include_candidates=True)
    assert any(h["id"] == "section_cut_fringe" and h["tier"] == "candidate" for h in candidate_hits)

    # Default parameters
    defaults = validate_parameters(recipe.parameters, {})
    assert defaults["px"] == 0.0
    assert defaults["nx"] == 1.0
    assert defaults["state"] == 1

    # Custom valid parameters
    custom = validate_parameters(
        recipe.parameters,
        {
            "px": 15.5,
            "py": 2.0,
            "pz": -3.0,
            "nx": 0.0,
            "ny": 1.0,
            "nz": 0.0,
            "state": 5,
            "fringe_code": 2,
        },
    )
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
        parameters={
            "px": 10.0,
            "py": 20.0,
            "pz": 30.0,
            "nx": 0.0,
            "ny": 0.0,
            "nz": 1.0,
            "state": 3,
            "fringe_code": 1,
        },
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


def test_real_3line_ascii_secforc_parsing(tmp_path):
    """P0-4: Test real LS-DYNA 3-line ASCII layout parsing with moment and centroid."""
    content = """
 LSTC Standard Dummy SECFORC
                    ls-dyna smp s R16 date 03/18/2025

{BEGIN LEGEND}
 Entity #        Title
        1     Neck_Cross_Section
{END LEGEND}

 line#1  section#     time        x-force     y-force     z-force    magnitude
 line#2  resultant  moments       x-moment    y-moment    z-moment   magnitude
 line#3  centroids                x           y           z            area  
           1    0.00000E+00     0.0000E+00  0.0000E+00  0.0000E+00  0.0000E+00
ac ID =   33377                 0.0000E+00  0.0000E+00  0.0000E+00  0.0000E+00
                               -3.7437E-01  1.0501E+01 -4.6940E+01  0.0000E+00

           1    1.00000E-01     3.0000E+02  4.0000E+02  0.0000E+00  5.0000E+02
ac ID =   33377                 1.0000E+01  2.0000E+01  2.0000E+01  3.0000E+01
                               -3.7400E-01  1.0500E+01 -4.6900E+01  1.5000E+02
"""
    sec_file = tmp_path / "secforc"
    sec_file.write_text(content, encoding="utf-8")

    data = read_ascii_secforc(sec_file)
    assert 1 in data
    s1 = data[1]
    assert s1["title"] == "Neck_Cross_Section"
    assert np.allclose(s1["time"], [0.0, 0.1])
    assert np.allclose(s1["total_force"], [0.0, 500.0])
    assert np.allclose(s1["resultant_force"], [0.0, 500.0])
    assert np.allclose(s1["total_moment"], [0.0, 30.0])
    assert np.allclose(s1["resultant_moment"], [0.0, 30.0])
    assert np.allclose(s1["area"], [0.0, 150.0])


def test_ascii_secforc_legend_with_section_7_title(tmp_path):
    """P0-4 (b): Legend title containing 'Section 7' must not corrupt section ID or time alignment."""
    content = """
{BEGIN LEGEND}
 Entity #        Title
        1     Section 7 Joint Load
{END LEGEND}

 line#1  section#     time        x-force     y-force     z-force    magnitude
 line#2  resultant  moments       x-moment    y-moment    z-moment   magnitude
 line#3  centroids                x           y           z            area  
           1    0.00000E+00     0.0000E+00  0.0000E+00  0.0000E+00  0.0000E+00
ac ID =   33377                 0.0000E+00  0.0000E+00  0.0000E+00  0.0000E+00
                               -3.7437E-01  1.0501E+01 -4.6940E+01  0.0000E+00

           1    1.00000E-03     1.0000E+02  0.0000E+00  0.0000E+00  1.0000E+02
ac ID =   33377                 0.0000E+00  0.0000E+00  0.0000E+00  0.0000E+00
                               -3.7437E-01  1.0501E+01 -4.6940E+01  1.0000E+02
"""
    f = tmp_path / "secforc"
    f.write_text(content, encoding="utf-8")

    data = read_ascii_secforc(f)
    assert list(data.keys()) == [1]  # Section ID is 1, not 7!
    s1 = data[1]
    assert s1["section_id"] == 1
    assert s1["title"] == "Section 7 Joint Load"
    assert np.allclose(s1["time"], [0.0, 1e-3])
    assert np.allclose(s1["total_force"], [0.0, 100.0])


def test_compare_section_forces_four_synthetic_counterexamples(tmp_path):
    """P1-5: 4 synthetic counterexamples (no overlap, 1-point overlap, inverted component, non-monotonic time)."""
    target = {
        "time": np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0]),
        "x_force": np.array([0.0, 10.0, 20.0, 30.0, 40.0, 50.0]),
        "y_force": np.zeros(6),
        "z_force": np.zeros(6),
        "resultant_force": np.array([0.0, 10.0, 20.0, 30.0, 40.0, 50.0]),
    }

    # 1. No overlap
    cmp_no_overlap = {
        "time": np.array([10.0, 11.0, 12.0]),
        "resultant_force": np.array([100.0, 110.0, 120.0]),
        "x_force": np.array([100.0, 110.0, 120.0]),
        "y_force": np.zeros(3),
        "z_force": np.zeros(3),
    }
    with pytest.raises(SectionForceError, match="No overlapping time interval"):
        compare_section_forces(cmp_no_overlap, target)

    # 2. Single-point overlap (samples below minimum)
    cmp_single_point = {
        "time": np.array([5.0, 6.0, 7.0]),
        "resultant_force": np.array([50.0, 60.0, 70.0]),
        "x_force": np.array([50.0, 60.0, 70.0]),
        "y_force": np.zeros(3),
        "z_force": np.zeros(3),
    }
    with pytest.raises(SectionForceError, match="Overlapping sample count .* below minimum"):
        compare_section_forces(cmp_single_point, target)

    # 3. Inverted component (Fx inverted): matched must be False!
    cmp_inverted_component = {
        "time": np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0]),
        "resultant_force": np.array([0.0, 10.0, 20.0, 30.0, 40.0, 50.0]),
        "x_force": np.array([0.0, -10.0, -20.0, -30.0, -40.0, -50.0]),  # sign inverted
        "y_force": np.zeros(6),
        "z_force": np.zeros(6),
    }
    res_inv = compare_section_forces(cmp_inverted_component, target)
    assert res_inv["matched"] is False
    assert res_inv["consistent_with_secforc"] is False
    assert res_inv["components"]["x_force"]["matched"] is False

    # 4. Non-monotonic time: rejected
    cmp_non_monotonic = {
        "time": np.array([0.0, 1.0, 0.5, 3.0]),
        "resultant_force": np.array([0.0, 10.0, 5.0, 30.0]),
    }
    with pytest.raises(SectionForceError, match="must be strictly increasing"):
        compare_section_forces(cmp_non_monotonic, target)


def test_secforc_missing_y_force_or_ids_rejected(tmp_path):
    """P1-7: Missing y_force or missing IDs throws clear SectionForceError, no fallback to [1]."""
    pytest.importorskip("lasso.dyna")
    from lasso.dyna.lsda_py3 import Lsda

    # Subtest A: Missing IDs
    f_no_ids = tmp_path / "binout_no_ids"
    ls = Lsda(str(f_no_ids), "w")
    ls.cd("/secforc/d000001", 1)
    ls.write("time", Lsda.R8, [0.0])
    ls.write("x_force", Lsda.R8, [10.0])
    ls.write("y_force", Lsda.R8, [0.0])
    ls.write("z_force", Lsda.R8, [0.0])
    ls.close()

    with pytest.raises(SectionForceError, match="No section IDs found in secforc database"):
        read_binout_secforc(f_no_ids)

    # Subtest B: Missing y_force
    f_no_fy = tmp_path / "binout_no_fy"
    ls2 = Lsda(str(f_no_fy), "w")
    ls2.cd("/secforc/metadata", 1)
    ls2.write("ids", Lsda.I4, [1])
    ls2.cd("/secforc/d000001", 1)
    ls2.write("time", Lsda.R8, [0.0])
    ls2.write("x_force", Lsda.R8, [10.0])
    # y_force is missing!
    ls2.write("z_force", Lsda.R8, [0.0])
    ls2.close()

    with pytest.raises(SectionForceError, match="Missing force components in secforc"):
        read_binout_secforc(f_no_fy)


def test_no_from_lasso_import_in_section():
    """P1-1: Verify domain/results/section.py does not contain 'from lasso'."""
    src = Path(__file__).resolve().parents[1] / "src/ls_prepost_mcp/domain/results/section.py"
    code = src.read_text(encoding="utf-8")
    assert "from lasso" not in code


# ==================== Real Corpus Acceptance Tests ====================


def test_pendulum_secforc_corpus():
    """P0-4 (a): pranavduraisamy pendulum secforc (250 entries) |F|-mag <= 1e-4, |M|-mag <= 1e-3."""
    root = corpus_root()
    if root is None:
        pytest.skip("Corpus directory not found")
    sec_path = (
        root
        / "public-results/pranavduraisamy__helmet-fit-bayes-opt/bo-runs/run0/pendulum/secforc"
    )
    if not sec_path.is_file():
        pytest.skip("pendulum secforc not found")

    data = read_ascii_secforc(sec_path)
    assert 1 in data
    s1 = data[1]
    assert len(s1["time"]) == 250

    chk = check_secforc_consistency(s1, rtol=1e-3, atol=1e-4)
    assert chk["consistent"] is True
    assert chk["max_absolute_difference"] <= 1e-4

    # Moment difference <= 1e-3
    assert chk["moment_consistency"] is not None
    assert chk["moment_consistency"]["consistent"] is True
    assert chk["moment_consistency"]["max_absolute_difference"] <= 1e-3


def test_binout_forces_secforc_corpus():
    """P0-4 (c): binout_forces (binout_matsum) parses secforc correctly."""
    root = corpus_root()
    if root is None:
        pytest.skip("Corpus directory not found")
    f_path = root / "public-results/ansys__example-data/result_files/binout/binout_matsum"
    if not f_path.is_file():
        pytest.skip("binout_matsum not found")

    data = read_binout_secforc(f_path)
    assert 1 in data
    s1 = data[1]
    assert len(s1["time"]) == 1001
    assert max(s1["resultant_force"]) > 1.0
