"""Tests for tasks.yaml Q04: field metrics and failure masks (extract_field).

Verifies:
1. von Mises, principal stresses, triaxiality, Lode parameter, Lode angle, and effective plastic strain
   on both solid and shell elements match independent calculations from textbook formulas.
2. Formula definitions and Lode conventions written into result metadata.
3. Mask strategies ('alive', 'all', 'deleted') filter correctly, and extrema return entity ID and state.
4. Export to CSV / NPZ and round-trip verification with read_field.
5. Error handling, input validation, and JobResult/v1 contract compliance.
6. Public corpus validation on real LS-DYNA d3plots (solids with deletions and shells).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.results import export as exp
from ls_prepost_mcp.service import Service

pytest.importorskip("lasso")
from lasso.dyna import ArrayType, D3plot  # noqa: E402


def independent_stress_metrics(s: np.ndarray) -> dict[str, float]:
    """Independent ground-truth stress invariants calculated directly from tensor definition.
    Components: xx, yy, zz, xy, yz, zx."""
    tensor = np.array([
        [s[0], s[3], s[5]],
        [s[3], s[1], s[4]],
        [s[5], s[4], s[2]],
    ], dtype=float)
    mean = np.trace(tensor) / 3.0
    pressure = -mean
    dev = tensor - mean * np.eye(3)
    j2 = 0.5 * np.sum(dev * dev)
    j3 = float(np.linalg.det(dev))
    mises = math.sqrt(3.0 * j2)
    principals = sorted(np.linalg.eigvalsh(tensor), reverse=True)
    p1, p2, p3 = principals[0], principals[1], principals[2]
    max_shear = 0.5 * (p1 - p3)

    scale = np.max(np.abs(s))
    if mises <= 1e-12 * (scale if scale > 0 else 1.0):
        triax = np.nan
        lode_param = np.nan
        lode_angle = np.nan
        lode_angle_param = np.nan
    else:
        triax = mean / mises
        spread = p1 - p3
        lode_param = (2.0 * p2 - p1 - p3) / spread
        cos3 = max(-1.0, min(1.0, 1.5 * math.sqrt(3.0) * j3 / (j2 ** 1.5)))
        lode_angle = math.acos(cos3) / 3.0
        lode_angle_param = 1.0 - 6.0 * lode_angle / math.pi

    return {
        "von_mises": mises,
        "mean_stress": mean,
        "pressure": pressure,
        "principal_1": p1,
        "principal_2": p2,
        "principal_3": p3,
        "max_shear": max_shear,
        "triaxiality": triax,
        "lode_parameter": lode_param,
        "lode_angle_rad": lode_angle,
        "lode_angle_parameter": lode_angle_param,
    }


@pytest.fixture()
def synthetic_d3plot(tmp_path: Path) -> Path:
    """Synthetic d3plot with both solid and shell elements across 3 states with deletions."""
    pytest.importorskip("lasso.dyna")
    plot = D3plot()
    a = plot.arrays

    times = np.array([0.0, 0.5, 1.0])
    a[ArrayType.global_timesteps] = times

    # 4 solids: IDs 10, 20, 30, 40
    # 4 shells: IDs 101, 102, 103, 104
    solid_ids = np.array([10, 20, 30, 40])
    shell_ids = np.array([101, 102, 103, 104])

    a[ArrayType.node_ids] = np.arange(1, 25)
    a[ArrayType.node_coordinates] = np.zeros((24, 3))

    a[ArrayType.element_solid_ids] = solid_ids
    a[ArrayType.element_solid_part_indexes] = np.array([0, 0, 1, 1])
    a[ArrayType.element_solid_node_indexes] = np.zeros((4, 8), dtype=int)

    a[ArrayType.element_shell_ids] = shell_ids
    a[ArrayType.element_shell_part_indexes] = np.array([2, 2, 3, 3])
    a[ArrayType.element_shell_node_indexes] = np.zeros((4, 4), dtype=int)

    # Stresses (states=3, elements=4, points=1, components=6)
    solid_stress = np.zeros((3, 4, 1, 6))
    # State 2 (last state):
    # solid 10: uniaxial tension sxx = 200.0
    solid_stress[2, 0, 0, :] = [200.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    # solid 20: pure shear sxy = 60.0
    solid_stress[2, 1, 0, :] = [0.0, 0.0, 0.0, 60.0, 0.0, 0.0]
    # solid 30: equibiaxial tension sxx = syy = 150.0
    solid_stress[2, 2, 0, :] = [150.0, 150.0, 0.0, 0.0, 0.0, 0.0]
    # solid 40: hydrostatic pressure sxx = syy = szz = -100.0
    solid_stress[2, 3, 0, :] = [-100.0, -100.0, -100.0, 0.0, 0.0, 0.0]
    a[ArrayType.element_solid_stress] = solid_stress

    # Shell stresses
    shell_stress = np.zeros((3, 4, 1, 6))
    # shell 101: uniaxial tension sxx = 300.0
    shell_stress[2, 0, 0, :] = [300.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    # shell 102: pure shear sxy = 80.0
    shell_stress[2, 1, 0, :] = [0.0, 0.0, 0.0, 80.0, 0.0, 0.0]
    # shell 103: equibiaxial tension sxx = syy = 180.0
    shell_stress[2, 2, 0, :] = [180.0, 180.0, 0.0, 0.0, 0.0, 0.0]
    # shell 104: zero stress
    shell_stress[2, 3, 0, :] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    a[ArrayType.element_shell_stress] = shell_stress

    # Effective plastic strains (states=3, elements=4, points=1)
    solid_eps = np.zeros((3, 4, 1))
    solid_eps[2, :, 0] = [0.05, 0.12, 0.08, 0.0]
    a[ArrayType.element_solid_effective_plastic_strain] = solid_eps

    shell_eps = np.zeros((3, 4, 1))
    shell_eps[2, :, 0] = [0.03, 0.15, 0.09, 0.0]
    a[ArrayType.element_shell_effective_plastic_strain] = shell_eps

    # Deletions: solid 20 is deleted at last state; shell 102 is deleted at last state
    a[ArrayType.element_solid_is_alive] = np.array([
        [1, 1, 1, 1],
        [1, 1, 1, 1],
        [1, 0, 1, 1],
    ], dtype=float)

    a[ArrayType.element_shell_is_alive] = np.array([
        [1, 1, 1, 1],
        [1, 1, 1, 1],
        [1, 0, 1, 1],
    ], dtype=float)

    plot_path = tmp_path / "d3plot"
    plot.write_d3plot(str(plot_path))
    return plot_path


def test_independent_calculation_match_solids(synthetic_d3plot: Path) -> None:
    """Acceptance 1: Mises, principals, triaxiality, Lode param/angle, plastic strain on solids match independent calculation."""
    service = Service(Settings(synthetic_d3plot.parent))
    stresses = {
        10: np.array([200.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
        20: np.array([0.0, 0.0, 0.0, 60.0, 0.0, 0.0]),
        30: np.array([150.0, 150.0, 0.0, 0.0, 0.0, 0.0]),
        40: np.array([-100.0, -100.0, -100.0, 0.0, 0.0, 0.0]),
    }

    quantities = [
        "von_mises", "principal_1", "principal_2", "principal_3", "triaxiality",
        "lode_parameter", "lode_angle_rad", "lode_angle_parameter", "mean_stress", "pressure"
    ]

    for q in quantities:
        res = service.extract_field(str(synthetic_d3plot), "solid", q, state=2, mask="all")
        assert res["status"] == "succeeded"
        values = res["data"]["values"]
        ids = res["data"]["ids"]

        for eid, val in zip(ids, values):
            expected = independent_stress_metrics(stresses[eid])[q]
            if math.isnan(expected):
                assert val == "nan" or val is None or math.isnan(float(val))
            else:
                assert float(val) == pytest.approx(expected, rel=1e-6, abs=1e-9)

    # Plastic strain
    eps_res = service.extract_field(str(synthetic_d3plot), "solid", "effective_plastic_strain", state=2, mask="all")
    assert eps_res["status"] == "succeeded"
    assert [float(v) for v in eps_res["data"]["values"]] == pytest.approx([0.05, 0.12, 0.08, 0.0], rel=1e-5)


def test_independent_calculation_match_shells(synthetic_d3plot: Path) -> None:
    """Acceptance 1: Mises, principals, triaxiality, Lode param/angle, plastic strain on shells match independent calculation."""
    service = Service(Settings(synthetic_d3plot.parent))
    stresses = {
        101: np.array([300.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
        102: np.array([0.0, 0.0, 0.0, 80.0, 0.0, 0.0]),
        103: np.array([180.0, 180.0, 0.0, 0.0, 0.0, 0.0]),
        104: np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
    }

    quantities = [
        "von_mises", "principal_1", "principal_2", "principal_3", "triaxiality",
        "lode_parameter", "lode_angle_rad", "lode_angle_parameter"
    ]

    for q in quantities:
        res = service.extract_field(str(synthetic_d3plot), "shell", q, state=2, mask="all")
        assert res["status"] == "succeeded"
        values = res["data"]["values"]
        ids = res["data"]["ids"]

        for eid, val in zip(ids, values):
            expected = independent_stress_metrics(stresses[eid])[q]
            if math.isnan(expected):
                assert val == "nan" or val is None or math.isnan(float(val))
            else:
                assert float(val) == pytest.approx(expected, rel=1e-6, abs=1e-9)

    # Plastic strain
    eps_res = service.extract_field(str(synthetic_d3plot), "shell", "effective_plastic_strain", state=2, mask="all")
    assert eps_res["status"] == "succeeded"
    assert [float(v) for v in eps_res["data"]["values"]] == pytest.approx([0.03, 0.15, 0.09, 0.0], rel=1e-5)


def test_metadata_and_lode_conventions(synthetic_d3plot: Path) -> None:
    """Acceptance 2: Formula definition and Lode sign conventions are written into result metadata."""
    service = Service(Settings(synthetic_d3plot.parent))
    res = service.extract_field(str(synthetic_d3plot), "solid", "lode_parameter", state=2, units="MPa")
    assert res["status"] == "succeeded"
    data = res["data"]

    # Conventions dictionary present
    assert "conventions" in data
    conv = data["conventions"]
    assert "lode_parameter" in conv
    assert "(2 s2 - s1 - s3) / (s1 - s3)" in conv["lode_parameter"]
    assert "lode_angle" in conv
    assert "lode_angle_parameter" in conv
    assert "undefined" in conv
    assert "deviatoric quantities are NaN" in conv["undefined"]

    # Specific formula
    assert data["formula"] == conv["lode_parameter"]
    assert data["units"] == "MPa"


def test_mask_modes_and_extrema_with_id_and_state(synthetic_d3plot: Path) -> None:
    """Acceptance 3: Mask strategies ('alive', 'all', 'deleted') selectable; extrema include entity ID and state."""
    service = Service(Settings(synthetic_d3plot.parent))

    # Mask: alive (default) -> solid 20 is excluded
    res_alive = service.extract_field(str(synthetic_d3plot), "solid", "von_mises", state=2, mask="alive")
    assert res_alive["status"] == "succeeded"
    ext_alive = res_alive["data"]["extrema"]
    assert ext_alive["count"] == 3  # elements 10, 30, 40 (20 is deleted)
    assert ext_alive["max"]["id"] == 10
    assert ext_alive["max"]["value"] == pytest.approx(200.0)
    assert ext_alive["max"]["state"] == 2
    assert ext_alive["min"]["id"] == 40
    assert ext_alive["min"]["value"] == pytest.approx(0.0)
    assert ext_alive["min"]["state"] == 2

    # Mask: all -> all 4 elements included
    res_all = service.extract_field(str(synthetic_d3plot), "solid", "von_mises", state=2, mask="all")
    ext_all = res_all["data"]["extrema"]
    assert ext_all["count"] == 4
    assert ext_all["max"]["id"] == 10
    assert ext_all["max"]["state"] == 2

    # Mask: deleted -> only solid 20 included
    res_del = service.extract_field(str(synthetic_d3plot), "solid", "von_mises", state=2, mask="deleted")
    ext_del = res_del["data"]["extrema"]
    assert ext_del["count"] == 1
    assert ext_del["min"]["id"] == 20
    assert ext_del["min"]["value"] == pytest.approx(60.0 * math.sqrt(3.0))
    assert ext_del["min"]["state"] == 2
    assert ext_del["max"]["id"] == 20
    assert ext_del["max"]["state"] == 2

    # Same for shell
    res_shell_alive = service.extract_field(str(synthetic_d3plot), "shell", "von_mises", state=2, mask="alive")
    ext_s_alive = res_shell_alive["data"]["extrema"]
    assert ext_s_alive["count"] == 3  # shell 102 excluded
    assert ext_s_alive["max"]["id"] == 101
    assert ext_s_alive["max"]["state"] == 2

    res_shell_del = service.extract_field(str(synthetic_d3plot), "shell", "von_mises", state=2, mask="deleted")
    ext_s_del = res_shell_del["data"]["extrema"]
    assert ext_s_del["count"] == 1
    assert ext_s_del["min"]["id"] == 102
    assert ext_s_del["min"]["state"] == 2
    assert ext_s_del["min"]["value"] == pytest.approx(80.0 * math.sqrt(3.0))


def test_artifact_export_and_round_trip(synthetic_d3plot: Path) -> None:
    """Verify CSV and NPZ export artifacts, hashes, and round-trip read."""
    service = Service(Settings(synthetic_d3plot.parent))
    res = service.extract_field(str(synthetic_d3plot), "solid", "triaxiality", state=2,
                                output_format="both", units="MPa")
    assert res["status"] == "succeeded"
    artifacts = res["artifacts"]
    assert len(artifacts) == 2

    csv_art = next(a for a in artifacts if a["kind"] == "csv")
    npz_art = next(a for a in artifacts if a["kind"] == "npz")

    # Round trip CSV
    csv_data = exp.read_field(csv_art["path"])
    assert csv_data["ids"].tolist() == [10, 20, 30, 40]
    assert csv_data["meta"]["quantity"] == "triaxiality"
    assert csv_data["meta"]["units"] == "MPa"

    # Round trip NPZ
    npz_data = exp.read_field(npz_art["path"])
    assert npz_data["ids"].tolist() == [10, 20, 30, 40]
    assert npz_data["meta"]["mask"] == "alive"


def test_fastmcp_tool_registration(synthetic_d3plot: Path) -> None:
    """Verify extract_field is registered as a first-class MCP tool."""
    from ls_prepost_mcp.server import build_server

    settings = Settings(synthetic_d3plot.parent)
    server = build_server(settings, tool_profile="full")
    tool_names = {tool.name for tool in server._tool_manager.list_tools()}
    assert "extract_field" in tool_names
    assert "compute_stress_invariants" in tool_names
    assert "inspect_result_validity" in tool_names


def test_input_validation_and_refusals(synthetic_d3plot: Path) -> None:
    """Malformed requests and network paths are refused before creating a job."""
    service = Service(Settings(synthetic_d3plot.parent))

    # Unknown family
    with pytest.raises(ValueError, match="Unknown element family"):
        service.extract_field(str(synthetic_d3plot), "unknown_fam", "von_mises")

    # Unknown mask
    with pytest.raises(ValueError, match="Unknown mask mode"):
        service.extract_field(str(synthetic_d3plot), "solid", "von_mises", mask="invalid_mask")

    # Unknown format
    with pytest.raises(ValueError, match="Unknown output format"):
        service.extract_field(str(synthetic_d3plot), "solid", "von_mises", output_format="docx")

    # Network UNC path
    with pytest.raises(ValueError, match="Network path"):
        service.extract_field(r"\\remote-server\share\d3plot", "solid", "von_mises")

    # Outside root path
    with pytest.raises(ValueError, match="outside the configured allowed roots"):
        service.extract_field("C:/Windows/System32/calc.exe", "solid", "von_mises")


def test_real_corpus_solid_plate_with_deletions() -> None:
    """Validate on real public corpus d3plot_projectile (solids, projectile penetrating plate with deletions)."""
    corpus_file = Path(r"F:\PythonWoking\temp\20260930-lsprepost-mcp-development\corpus\public-results\ansys__example-data\result_files\d3plot_projectile\d3plot")
    if not corpus_file.exists():
        pytest.skip("Corpus file not present")

    service = Service(Settings(corpus_file.parent, allowed_roots=(corpus_file.parent,)))
    res = service.extract_field(str(corpus_file), "solid", "triaxiality", state=-1, mask="alive")
    assert res["status"] == "succeeded"
    assert res["data"]["element_count"] == 5664
    assert res["data"]["active_count"] == 5050
    assert res["data"]["extrema"]["max"]["id"] == 1681
    assert res["data"]["extrema"]["max"]["state"] == 15
    assert res["data"]["extrema"]["min"]["id"] == 1255
    assert res["data"]["extrema"]["min"]["state"] == 15


def test_real_corpus_shell_elements() -> None:
    """Validate on real public corpus order_d3plot containing shell elements."""
    corpus_file = Path(r"F:\PythonWoking\temp\20260930-lsprepost-mcp-development\corpus\public-results\open-lasso-python__lasso-python\test\test_data\order_d3plot\d3plot")
    if not corpus_file.exists():
        pytest.skip("Corpus file not present")

    service = Service(Settings(corpus_file.parent, allowed_roots=(corpus_file.parent,)))
    res = service.extract_field(str(corpus_file), "shell", "lode_parameter", state=-1, mask="alive")
    assert res["status"] == "succeeded"
    assert res["data"]["element_count"] == 16
    assert res["data"]["active_count"] == 16
    assert res["data"]["extrema"]["max"]["id"] == 26
    assert res["data"]["extrema"]["max"]["state"] == 6
    assert res["data"]["extrema"]["min"]["id"] == 32
    assert res["data"]["extrema"]["min"]["state"] == 6
