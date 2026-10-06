"""Tests for Q12 energy balance, ratio screening, and MATSUM part dissipation."""

import json
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.energy import calculate_energy_balance, read_ascii_glstat
from ls_prepost_mcp.service import Service


def test_calculate_energy_balance_conserved_and_screening():
    times = np.linspace(0.0, 1.0, 11)
    # Physical system: work input converts into KE, IE and a small amount of HG
    ew = 1000.0 * times
    ke = 400.0 * times
    ie = 550.0 * times
    hg = 25.0 * times  # HG / IE = 25 / 550 ≈ 0.0454 (< 0.05)
    se = 10.0 * times
    de = 10.0 * times
    ee = 5.0 * times
    te = ke + ie + hg + se + de + ee  # exact sum: 1000.0 * times

    energies = {
        "time": times,
        "kinetic_energy": ke,
        "internal_energy": ie,
        "hourglass_energy": hg,
        "sliding_energy": se,
        "external_work": ew,
        "damping_energy": de,
        "eroded_energy": ee,
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


def test_part_level_matsum_decomposition():
    times = np.array([0.0, 0.5, 1.0])
    energies = {
        "time": times,
        "kinetic_energy": np.array([0.0, 50.0, 100.0]),
        "internal_energy": np.array([0.0, 500.0, 1000.0]),
        "hourglass_energy": np.array([0.0, 20.0, 40.0]),
        "sliding_energy": np.array([0.0, 0.0, 0.0]),
        "external_work": np.array([0.0, 570.0, 1140.0]),
        "damping_energy": np.array([0.0, 0.0, 0.0]),
        "eroded_energy": np.array([0.0, 0.0, 0.0]),
        "total_energy": np.array([0.0, 570.0, 1140.0]),
    }

    # Two parts in MATSUM
    parts = {
        1: {
            "time": times,
            "internal_energy": np.array([0.0, 400.0, 800.0]),  # 80% of total IE
            "kinetic_energy": np.array([0.0, 40.0, 80.0]),
            "hourglass_energy": np.array([0.0, 10.0, 20.0]),
        },
        2: {
            "time": times,
            "internal_energy": np.array([0.0, 100.0, 200.0]),  # 20% of total IE
            "kinetic_energy": np.array([0.0, 10.0, 20.0]),
            "hourglass_energy": np.array([0.0, 10.0, 20.0]),  # 20/200 = 10% HG in part 2
        },
    }

    res = calculate_energy_balance(energies, parts=parts, units="J")
    summary = res["summary"]
    assert summary["parts_analyzed"] == 2
    part1 = summary["parts"][1]
    part2 = summary["parts"][2]
    assert part1["fraction_of_total_internal_energy"] == pytest.approx(0.8)
    assert part2["fraction_of_total_internal_energy"] == pytest.approx(0.2)
    assert part2["max_part_hourglass_ratio"] == pytest.approx(0.1)


def test_read_ascii_glstat_and_consistency(tmp_path):
    glstat_file = tmp_path / "glstat"
    content = """
$ LS-DYNA GLSTAT energy file
 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00
 1.000000E-03 1.000000E+02 5.000000E+02 0.000000E+00 2.000000E+01 5.000000E+00 2.000000E+00 6.270000E+02 0.000000E+00 0.000000E+00 0.000000E+00 6.270000E+02
 2.000000E-03 2.000000E+02 1.000000E+03 0.000000E+00 4.000000E+01 1.000000E+01 4.000000E+00 1.254000E+03 0.000000E+00 0.000000E+00 0.000000E+00 1.254000E+03
"""
    glstat_file.write_text(content, encoding="utf-8")

    data = read_ascii_glstat(glstat_file)
    assert len(data["time"]) == 3
    assert np.allclose(data["kinetic_energy"], [0.0, 100.0, 200.0])
    assert np.allclose(data["internal_energy"], [0.0, 500.0, 1000.0])
    assert np.allclose(data["hourglass_energy"], [0.0, 20.0, 40.0])
    assert np.allclose(data["total_energy"], [0.0, 627.0, 1254.0])

    res = calculate_energy_balance(data, units="J")
    assert res["summary"]["sample_count"] == 3


def test_service_check_energy_end_to_end(tmp_path):
    service = Service(Settings(tmp_path))
    glstat_file = tmp_path / "glstat"
    content = """
 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00
 1.000000E-03 1.000000E+02 5.000000E+02 0.000000E+00 2.000000E+01 0.000000E+00 0.000000E+00 6.200000E+02 0.000000E+00 0.000000E+00 0.000000E+00 6.200000E+02
"""
    glstat_file.write_text(content, encoding="utf-8")

    result = service.check_energy(
        str(glstat_file),
        units="J",
        kinetic_ratio_limit=0.3,
        hourglass_ratio_limit=0.05,
    )

    assert result["status"] == "succeeded"
    data = result["data"]
    assert data["units"] == "J"
    assert data["verdict"] == "passed"
    assert data["checks"]["hourglass_energy"]["passed"] is True

    # Artifacts check
    artifacts = result["artifacts"]
    artifact_kinds = {a["kind"] for a in artifacts}
    assert "csv" in artifact_kinds and "json" in artifact_kinds

    csv_path = next(Path(a["path"]) for a in artifacts if a["kind"] == "csv")
    assert csv_path.is_file()
    assert "time" in csv_path.read_text(encoding="utf-8")

    json_path = next(Path(a["path"]) for a in artifacts if a["kind"] == "json")
    summary = json.loads(json_path.read_text(encoding="utf-8"))
    assert summary["energy_budget"]["final_internal_energy"] == 500.0


def test_binout_glstat_and_matsum_with_lasso(tmp_path):
    pytest.importorskip("lasso.dyna")
    from lasso.dyna.lsda_py3 import Lsda

    binout_path = tmp_path / "binout0000"
    f = Lsda(str(binout_path), "w")

    # glstat
    times = [0.0, 0.001, 0.002]
    for k, t in enumerate(times, start=1):
        f.cd(f"/glstat/d{k:06d}", 1)
        f.write("time", Lsda.R8, [t])
        f.write("kinetic_energy", Lsda.R8, [100.0 * (k - 1)])
        f.write("internal_energy", Lsda.R8, [500.0 * (k - 1)])
        f.write("hourglass_energy", Lsda.R8, [20.0 * (k - 1)])
        f.write("external_work", Lsda.R8, [620.0 * (k - 1)])

    # matsum
    f.cd("/matsum/metadata", 1)
    f.write("ids", Lsda.I4, [1, 2])
    for k, t in enumerate(times, start=1):
        f.cd(f"/matsum/d{k:06d}", 1)
        f.write("time", Lsda.R8, [t])
        f.write("internal_energy", Lsda.R8, [400.0 * (k - 1), 100.0 * (k - 1)])
        f.write("kinetic_energy", Lsda.R8, [80.0 * (k - 1), 20.0 * (k - 1)])
        f.write("hourglass_energy", Lsda.R8, [10.0 * (k - 1), 10.0 * (k - 1)])
    f.close()

    service = Service(Settings(tmp_path))
    res = service.check_energy(str(binout_path), units="J")

    assert res["status"] == "succeeded"
    data = res["data"]
    assert data["sample_count"] == 3
    assert data["parts_analyzed"] == 2
    assert data["parts"][1]["fraction_of_total_internal_energy"] == pytest.approx(0.8)
    assert data["parts"][2]["fraction_of_total_internal_energy"] == pytest.approx(0.2)

