"""Tests for Q12 energy balance, ratio screening, and MATSUM part dissipation."""

import os
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.domain.results.energy import (
    calculate_energy_balance,
    read_ascii_glstat,
    read_ascii_matsum,
    read_binout_glstat,
)
from ls_prepost_mcp.outcomes import normalize_outcome
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.workflow_checks import evaluate_gate


def corpus_root() -> Path | None:
    env_dir = os.environ.get("LSPP_CORPUS_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir)
    default_dir = Path(r"F:\PythonWoking\temp\20260930-lsprepost-mcp-development\corpus")
    if default_dir.is_dir():
        return default_dir
    return None


def test_calculate_energy_balance_conserved_and_screening():
    times = np.linspace(0.0, 1.0, 11)
    ew = 1000.0 * times
    ke = 400.0 * times
    ie = 550.0 * times
    hg = 25.0 * times  # HG / IE = 25 / 550 ≈ 0.0454 (< 0.05)
    se = 10.0 * times
    de = 10.0 * times
    stonewall = 5.0 * times
    te = ke + ie + hg + se + de + stonewall

    energies = {
        "time": times,
        "kinetic_energy": ke,
        "internal_energy": ie,
        "hourglass_energy": hg,
        "sliding_energy": se,
        "external_work": ew,
        "damping_energy": de,
        "stonewall_energy": stonewall,
        "total_energy": te,
    }

    # Case 1: Caller supplies strict thresholds that pass
    res = calculate_energy_balance(
        energies,
        units="J",
        kinetic_ratio_limit=0.8,
        hourglass_ratio_limit=0.05,
        residual_ratio_limit=0.01,
        sliding_ratio_limit=0.05,
    )
    summary = res["summary"]
    assert summary["units"] == "J"
    assert summary["sample_count"] == 11
    assert summary["verdict"] == "passed"
    assert summary["passed"] is True
    assert summary["checks"]["hourglass_energy"]["passed"] is True
    assert summary["checks"]["energy_balance"]["passed"] is True
    assert summary["balance_residual"]["max_relative_residual"] < 1e-10

    # CSV series rows shape
    assert len(res["series_rows"]) == 11
    assert len(res["series_rows"][0]) == 13

    # Case 2: Unspecified thresholds - acceptance rule: "未给定时只报告比例不下结论"
    res_none = calculate_energy_balance(energies, units="J")
    sum_none = res_none["summary"]
    assert sum_none["verdict"] == "metrics_only_no_thresholds"
    assert sum_none["passed"] is None
    assert sum_none["checks"]["kinetic_energy"]["passed"] is None
    assert sum_none["checks"]["hourglass_energy"]["passed"] is None
    assert sum_none["checks"]["energy_balance"]["passed"] is None
    assert sum_none["screening_ratios"]["max_hourglass_ratio"] == pytest.approx(25.0 / 550.0, rel=1e-4)

    # Case 3: Threshold exceedance
    res_exceeded = calculate_energy_balance(
        energies,
        units="J",
        hourglass_ratio_limit=0.02,  # actual ratio is ~0.045
    )
    assert res_exceeded["summary"]["verdict"] == "exceeded"
    assert res_exceeded["summary"]["passed"] is False
    assert res_exceeded["summary"]["checks"]["hourglass_energy"]["passed"] is False
    assert res_exceeded["summary"]["checks"]["hourglass_energy"]["exceedances"] > 0


def test_real_block_glstat_parsing_multi_stonewall_missing_hg(tmp_path):
    """P0-1: Parse real LS-DYNA block layout (>=3 blocks, stonewall with wall# suffix, missing hourglass, 5-sigfig)."""
    glstat_text = """
 Bolted Connection Test
                         ls-dyna mpp.190 s              date 10/29/2021


 dt of cycle       1 is controlled by solid         100778 of part        10

 time...........................   0.00000E+00
 time step......................   2.11870E-04
 kinetic energy.................   0.00000E+00
 internal energy................   1.60000E-02
 spring and damper energy.......   8.00000E-04
 stonewall energy...............   1.25000E+01 wall#    1
 stonewall energy...............   2.50000E+01 wall#    2
 system damping energy..........   0.00000E+00
 sliding interface energy.......   0.00000E+00
 external work..................   0.00000E+00
 total energy...................   5.35000E+01
 added mass.....................   1.00000E-03
 percent increase...............   2.50000E-02


 dt of cycle      24 is controlled by solid         100778 of part        10

 time...........................   4.87301E-03
 time step......................   2.11870E-04
 kinetic energy.................   9.93441E-02
 internal energy................   1.36945E-01
 spring and damper energy.......   8.00000E-04
 stonewall energy...............   1.50000E+01 wall#    1
 stonewall energy...............   3.00000E+01 wall#    2
 system damping energy..........   1.00000E-04
 sliding interface energy.......   2.00000E-04
 external work..................   4.50000E-01
 total energy...................   4.52338E+01
 added mass.....................   1.00000E-03
 percent increase...............   2.50000E-02


 dt of cycle      48 is controlled by solid         100778 of part        10

 time...........................   9.95789E-03
 time step......................   2.11870E-04
 kinetic energy.................   1.07716E-01
 internal energy................   1.92573E-01
 spring and damper energy.......   8.00000E-04
 stonewall energy...............   2.00000E+01 wall#    1
 stonewall energy...............   4.00000E+01 wall#    2
 system damping energy..........   2.00000E-04
 sliding interface energy.......   4.00000E-04
 external work..................   9.00000E-01
 total energy...................   6.03009E+01
 added mass.....................   1.00000E-03
 percent increase...............   2.50000E-02
"""
    f = tmp_path / "glstat"
    f.write_text(glstat_text, encoding="utf-8")

    data = read_ascii_glstat(f)
    assert len(data["time"]) == 3
    assert np.allclose(data["time"], [0.0, 4.87301e-3, 9.95789e-3])
    # Multi-stonewall sum: (12.5+25)=37.5, (15+30)=45.0, (20+40)=60.0
    assert np.allclose(data["stonewall_energy"], [37.5, 45.0, 60.0])
    # Hourglass missing
    assert data["hourglass_energy"] is None
    # 5-sigfig kinetic energy check
    assert np.allclose(data["kinetic_energy"], [0.0, 9.93441e-2, 1.07716e-1])
    assert data["added_mass"] is not None and data["percent_increase"] is not None


def test_missing_quantities_not_filled_with_zero_and_fail_threshold():
    """P0-2: Missing binout/ASCII keys are None; thresholds on missing quantities cannot pass."""
    times = np.array([0.0, 1.0])
    energies = {
        "time": times,
        "kinetic_energy": None,  # missing
        "internal_energy": np.array([100.0, 200.0]),
        "hourglass_energy": None,  # missing
        "sliding_energy": np.array([0.0, 0.0]),
        "external_work": np.array([100.0, 200.0]),
        "damping_energy": np.array([0.0, 0.0]),
        "total_energy": np.array([100.0, 200.0]),
    }

    res = calculate_energy_balance(
        energies,
        units="J",
        kinetic_ratio_limit=0.5,
        hourglass_ratio_limit=0.05,
    )
    summary = res["summary"]
    assert summary["passed"] is False  # Must NOT pass when thresholded quantities are missing
    assert summary["checks"]["kinetic_energy"]["passed"] is False
    assert summary["checks"]["kinetic_energy"]["status"] == "not_applicable"
    assert summary["checks"]["hourglass_energy"]["passed"] is False
    assert summary["checks"]["hourglass_energy"]["status"] == "not_applicable"

    # Warnings must contain explicit notices
    warnings = " ".join(summary["warnings"])
    assert "沙漏能未输出（需 *CONTROL_ENERGY HGEN=2）" in warnings
    assert "动能未输出" in warnings


def test_energy_balance_negative_sliding_detection():
    times = np.array([0.0, 1.0])
    energies = {
        "time": times,
        "kinetic_energy": np.array([0.0, 100.0]),
        "internal_energy": np.array([0.0, 500.0]),
        "hourglass_energy": np.array([0.0, 10.0]),
        "sliding_energy": np.array([0.0, -50.0]),  # Negative contact sliding energy
        "external_work": np.array([0.0, 560.0]),
        "damping_energy": np.array([0.0, 0.0]),
        "eroded_energy": np.array([0.0, 0.0]),
        "total_energy": np.array([0.0, 560.0]),
    }
    res = calculate_energy_balance(energies, units="mJ")
    assert res["summary"]["energy_budget"]["negative_sliding_detected"] is True
    assert res["summary"]["energy_budget"]["min_sliding_energy"] == -50.0
    assert any("负滑移" in w for w in res["summary"]["warnings"])


def test_part_level_matsum_decomposition_and_glstat_discrepancy(tmp_path):
    """P1-3: MATSUM part dissipation and Σ部件 IE vs GLSTAT IE discrepancy."""
    matsum_text = """
 LS-DYNA SIMULATION
 {BEGIN LEGEND}
  Entity #        Title
         1     Part 1
         2     Part 2
 {END LEGEND}

  time =   0.0000E+00
  mat.#=    1             inten=   0.0000E+00     kinen=   0.0000E+00     eroded_ie=   0.0000E+00     eroded_ke=   0.0000E+00
  x-mom=   0.0000E+00     y-mom=   0.0000E+00     z-mom=   0.0000E+00
  x-rbv=   0.0000E+00     y-rbv=   0.0000E+00     z-rbv=   0.0000E+00
                          hgeng=   0.0000E+00     +mass=   0.0000E+00     eroded_he=   0.0000E+00

  mat.#=    2             inten=   0.0000E+00     kinen=   0.0000E+00     eroded_ie=   0.0000E+00     eroded_ke=   0.0000E+00
  x-mom=   0.0000E+00     y-mom=   0.0000E+00     z-mom=   0.0000E+00
  x-rbv=   0.0000E+00     y-rbv=   0.0000E+00     z-rbv=   0.0000E+00
                          hgeng=   0.0000E+00     +mass=   0.0000E+00     eroded_he=   0.0000E+00

  time =   1.0000E-03
  mat.#=    1             inten=   8.0000E+02     kinen=   8.0000E+01     eroded_ie=   0.0000E+00     eroded_ke=   0.0000E+00
  x-mom=   0.0000E+00     y-mom=   0.0000E+00     z-mom=   0.0000E+00
  x-rbv=   0.0000E+00     y-rbv=   0.0000E+00     z-rbv=   0.0000E+00
                          hgeng=   2.0000E+01     +mass=   0.0000E+00     eroded_he=   0.0000E+00

  mat.#=    2             inten=   1.8000E+02     kinen=   2.0000E+01     eroded_ie=   0.0000E+00     eroded_ke=   0.0000E+00
  x-mom=   0.0000E+00     y-mom=   0.0000E+00     z-mom=   0.0000E+00
  x-rbv=   0.0000E+00     y-rbv=   0.0000E+00     z-rbv=   0.0000E+00
                          hgeng=   1.0000E+01     +mass=   0.0000E+00     eroded_he=   0.0000E+00
"""
    m_path = tmp_path / "matsum"
    m_path.write_text(matsum_text, encoding="utf-8")
    parts = read_ascii_matsum(m_path)
    assert len(parts) == 2

    # Global GLSTAT IE is 1000.0, while sum of parts is 800+180 = 980 (diff = 20 from spring/damper)
    times = np.array([0.0, 1.0e-3])
    energies = {
        "time": times,
        "kinetic_energy": np.array([0.0, 100.0]),
        "internal_energy": np.array([0.0, 1000.0]),
        "hourglass_energy": np.array([0.0, 30.0]),
        "spring_and_damper_energy": np.array([0.0, 20.0]),
        "total_energy": np.array([0.0, 1150.0]),
    }

    res = calculate_energy_balance(energies, parts=parts, units="J")
    summary = res["summary"]
    assert summary["parts_analyzed"] == 2
    # Fraction: 800 / 1000 = 0.8
    assert summary["parts"][1]["fraction_of_total_internal_energy"] == pytest.approx(0.8)
    assert summary["parts"][2]["fraction_of_total_internal_energy"] == pytest.approx(0.18)

    # Discrepancy separately reported
    mvs = summary["matsum_vs_glstat"]
    assert mvs["max_internal_discrepancy"] == pytest.approx(20.0)
    assert mvs["spring_and_damper_energy"] == pytest.approx(20.0)
    assert mvs["unaccounted_discrepancy"] == pytest.approx(0.0)


def test_non_monotonic_time_rejected():
    """P1-6: Non-monotonic time triggers warning and rejects passed verdict."""
    times = np.array([0.0, 0.5, 0.4])  # Time rollback
    energies = {
        "time": times,
        "kinetic_energy": np.array([0.0, 10.0, 10.0]),
        "internal_energy": np.array([0.0, 100.0, 100.0]),
        "hourglass_energy": np.array([0.0, 1.0, 1.0]),
        "total_energy": np.array([0.0, 111.0, 111.0]),
    }
    res = calculate_energy_balance(energies, units="J", hourglass_ratio_limit=0.05)
    assert res["summary"]["passed"] is False
    assert res["summary"]["verdict"] == "exceeded"
    assert any("时间序列非严格单调递增" in w for w in res["summary"]["warnings"])


def test_no_from_lasso_import_in_energy():
    """P1-1: Verify domain/results/energy.py does not contain 'from lasso'."""
    src = Path(__file__).resolve().parents[1] / "src/ls_prepost_mcp/domain/results/energy.py"
    code = src.read_text(encoding="utf-8")
    assert "from lasso" not in code


def test_service_check_energy_jobresult_v1(tmp_path):
    """P1-2: check_energy returns JobResult/v1 accepted by normalize_outcome and evaluate_gate."""
    service = Service(Settings(tmp_path))
    glstat_text = """
 dt of cycle       1 is controlled by solid 1
 time...........................   0.00000E+00
 kinetic energy.................   0.00000E+00
 internal energy................   1.00000E+02
 hourglass energy ..............   2.00000E+00
 total energy...................   1.02000E+02
 external work..................   1.02000E+02

 dt of cycle       2 is controlled by solid 1
 time...........................   1.00000E-03
 kinetic energy.................   1.00000E+01
 internal energy................   1.00000E+02
 hourglass energy ..............   2.00000E+00
 total energy...................   1.12000E+02
 external work..................   1.12000E+02
"""
    f = tmp_path / "glstat"
    f.write_text(glstat_text, encoding="utf-8")

    result = service.check_energy(
        str(f),
        units="J",
        kinetic_ratio_limit=0.2,
        hourglass_ratio_limit=0.05,
    )

    # 1. Contract check
    assert result["contract"] == "JobResult/v1"
    assert result["operation"] == "check_energy"
    assert result["status"] == "succeeded"

    # 2. Strict Pydantic JobResult validation
    job = JobResult.model_validate(result)
    assert job.execution_accepted is True
    assert job.check_status == "passed"

    # 3. normalize_outcome and evaluate_gate
    normalized = normalize_outcome("check_energy", result)
    assert normalized.operation == "check_energy"
    gate = evaluate_gate(normalized, [])
    assert gate["passed"] is True


# ==================== Real Corpus Acceptance Tests ====================


def test_bolt_b_explicit_glstat_vs_binout_corpus():
    """P0-1 (b): Compare hu-shuhan Bolt_B_Explicit glstat vs binout over 1000 states (rel diff <= 1e-5)."""
    pytest.importorskip("lasso")
    root = corpus_root()
    if root is None:
        pytest.skip("Corpus directory not found")
    bolt_dir = root / "public-results/hu-shuhan__editOpeniGame/test/Format Validation Test/lsdyna/Bolt_B_Explicit"
    if not (bolt_dir / "glstat").is_file():
        pytest.skip("Bolt_B_Explicit glstat not found")

    ascii_data = read_ascii_glstat(bolt_dir / "glstat")
    binout_data = read_binout_glstat(bolt_dir)

    assert len(ascii_data["time"]) == 1000
    assert len(binout_data["time"]) == 1000

    for comp in ("kinetic_energy", "internal_energy", "total_energy"):
        a_val = ascii_data[comp]
        b_val = binout_data[comp]
        diff = np.abs(a_val - b_val)
        denom = np.maximum(np.abs(b_val), 1e-12)
        rel_diff = diff / denom
        max_rel = float(np.max(rel_diff))
        assert max_rel <= 1e-5, f"{comp} max rel diff {max_rel} exceeded 1e-5"


def test_eight_public_ascii_glstat_corpus():
    """P0-1 (c): Read all 8 public ASCII glstat files and verify non-zero samples."""
    root = corpus_root()
    if root is None:
        pytest.skip("Corpus directory not found")

    paths = [
        root / "public-results/hu-shuhan__editOpeniGame/test/Format Validation Test/lsdyna/Bolt_B_Explicit/glstat",
        root / "public-results/jascott4427__PILLARS-LSDyna/Bolt_B_Explicit/glstat",
        root / "public-results/kitware__vtk-testdata/Testing/Data/LSDyna/hemi.draw/hemi_draw.glstat",
        root / "public-results/lsdyna-ansys-com__lsopt-genex/genex_example_and_tutorial/sample_glstat",
        root / "public-results/NaudeConradie__Masters-Project/Models/Old/Other/LSDyna_Unit_Cell_Corner/Steel_Explicit/glstat",
        root / "public-results/NaudeConradie__Masters-Project/Models/Old/Other/LSDyna_Unit_Cell_Corner/Steel_Implicit/glstat",
        root / "public-results/node997__dyna_pladebuk/Plade_300_150_4/BB/glstat",
        root / "public-results/praveenvenky110395__LS-DYNA-Crimping-Simulation/results/glstat",
    ]

    for p in paths:
        if not p.is_file():
            pytest.skip(f"Missing corpus file {p}")
        data = read_ascii_glstat(p)
        assert len(data["time"]) >= 1, f"{p} parsed 0 samples"


def test_pyansys_heart_corpus_missing_hourglass():
    """P0-2 (b): pyansys-heart binout (set 5) missing hourglass_energy triggers warning and None."""
    pytest.importorskip("lasso")
    root = corpus_root()
    if root is None:
        pytest.skip("Corpus directory not found")
    heart_binout = root / "public-results/ansys__pyansys-heart/tests/heart/assets/post/main/binout"
    if not heart_binout.is_file():
        pytest.skip("pyansys-heart binout not found")

    data = read_binout_glstat(heart_binout)
    assert data["hourglass_energy"] is None
    res = calculate_energy_balance(data, units="J", hourglass_ratio_limit=0.05)
    assert res["summary"]["checks"]["hourglass_energy"]["status"] == "not_applicable"
    assert any("沙漏能未输出（需 *CONTROL_ENERGY HGEN=2）" in w for w in res["summary"]["warnings"])


def test_hemi_draw_and_genex_closure_corpus():
    """P1-4: kitware hemi_draw and lsopt genex relative closure error <= 1e-5."""
    root = corpus_root()
    if root is None:
        pytest.skip("Corpus directory not found")

    p1 = root / "public-results/kitware__vtk-testdata/Testing/Data/LSDyna/hemi.draw/hemi_draw.glstat"
    p2 = root / "public-results/lsdyna-ansys-com__lsopt-genex/genex_example_and_tutorial/sample_glstat"
    if not p1.is_file() or not p2.is_file():
        pytest.skip("Corpus files not found")

    res1 = calculate_energy_balance(read_ascii_glstat(p1))
    assert res1["summary"]["energy_closure"]["max_relative_closure_error"] <= 1e-5

    res2 = calculate_energy_balance(read_ascii_glstat(p2))
    assert res2["summary"]["energy_closure"]["max_relative_closure_error"] <= 1e-5


def test_node997_plade_matsum_binout_consistency_corpus():
    """P1-3: node997 Plade BB ASCII matsum and binout part results match."""
    pytest.importorskip("lasso")
    root = corpus_root()
    if root is None:
        pytest.skip("Corpus directory not found")
    bb_dir = root / "public-results/node997__dyna_pladebuk/Plade_300_150_4/BB"
    if not (bb_dir / "matsum").is_file() or not (bb_dir / "binout").is_file():
        pytest.skip("node997 BB files not found")

    from ls_prepost_mcp.domain.results.energy import read_binout_matsum

    ascii_parts = read_ascii_matsum(bb_dir / "matsum")
    binout_parts = read_binout_matsum(bb_dir)

    assert set(ascii_parts.keys()) == set(binout_parts.keys())
    for pid in ascii_parts:
        a_ie = ascii_parts[pid]["internal_energy"]
        b_ie = binout_parts[pid]["internal_energy"]
        assert np.allclose(a_ie, b_ie, atol=1e-5)
