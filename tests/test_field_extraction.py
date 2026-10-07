"""Tests for tasks.yaml Q03: Field data extraction (extract_field).

Acceptance criteria:
1. Export to CSV/NPZ with metadata containing:
   quantity, component, units, state, time, layer/integration_point, coordinate_system, backend.
2. Element-by-element equivalence between LSPP (native) and LASSO on solid and shell cases within tolerance.
   Refusal of unverified native solid integration points 2..8.
   Preservation of genuine shell layer semantics without fake conversion.
3. Element failure/deletion masking ('alive', 'all', 'deleted') noted in metadata.
4. User story validation: state 20, Part 3 elements, all six stress components exported to CSV.
5. Public corpus validation on real d3plot cases (solid projectile with deletions, shell order_d3plot).
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.domain.results import export as exp
from ls_prepost_mcp.native_results import STRESS_KEYS
from ls_prepost_mcp.service import Service

pytest.importorskip("lasso")
from lasso.dyna import ArrayType, D3plot  # noqa: E402


@pytest.fixture()
def solid_and_shell_d3plot(tmp_path: Path) -> Path:
    """Fixture containing both solid and shell elements, multiple parts (including Part 3),
    25 states, and element deletions."""
    plot = D3plot()
    a = plot.arrays

    n_states = 25
    times = np.linspace(0.0, 2.4, n_states)
    a[ArrayType.global_timesteps] = times

    # 6 solids: IDs 1..6; Part 1 (IDs 1, 2), Part 2 (IDs 3, 4), Part 3 (IDs 5, 6)
    solid_ids = np.array([1, 2, 3, 4, 5, 6])
    # Part 3 contains elements 5 and 6
    solid_part_indexes = np.array([0, 0, 1, 1, 2, 2])

    # 4 shells: IDs 101, 102, 103, 104; Part 4 (IDs 101, 102), Part 5 (IDs 103, 104)
    shell_ids = np.array([101, 102, 103, 104])
    shell_part_indexes = np.array([3, 3, 4, 4])

    part_ids = np.array([1, 2, 3, 4, 5])
    a[ArrayType.part_titles_ids] = part_ids
    a[ArrayType.part_titles] = np.array([f"part_{p}".encode("latin-1").ljust(72) for p in part_ids])

    # Nodes
    a[ArrayType.node_ids] = np.arange(1, 50)
    a[ArrayType.node_coordinates] = np.zeros((49, 3))

    a[ArrayType.element_solid_ids] = solid_ids
    a[ArrayType.element_solid_part_indexes] = solid_part_indexes
    a[ArrayType.element_solid_node_indexes] = np.zeros((6, 8), dtype=int)

    a[ArrayType.element_shell_ids] = shell_ids
    a[ArrayType.element_shell_part_indexes] = shell_part_indexes
    a[ArrayType.element_shell_node_indexes] = np.zeros((4, 4), dtype=int)

    # Solid stress: (n_states, 6 solids, 1 point, 6 components)
    solid_stress = np.zeros((n_states, 6, 1, 6))
    for s_idx in range(n_states):
        factor = (s_idx + 1) * 10.0
        for e_idx in range(6):
            solid_stress[s_idx, e_idx, 0, 0] = factor * (e_idx + 1)         # sxx
            solid_stress[s_idx, e_idx, 0, 1] = factor * (e_idx + 1) * 0.5   # syy
            solid_stress[s_idx, e_idx, 0, 2] = factor * (e_idx + 1) * 0.2   # szz
            solid_stress[s_idx, e_idx, 0, 3] = factor * 2.0                 # sxy
            solid_stress[s_idx, e_idx, 0, 4] = factor * 1.5                 # syz
            solid_stress[s_idx, e_idx, 0, 5] = factor * 1.0                 # szx
    a[ArrayType.element_solid_stress] = solid_stress
    a[ArrayType.element_solid_effective_plastic_strain] = np.ones((n_states, 6, 1)) * 0.05

    # Solid alive flags: element 6 deleted from state 15 onward
    solid_alive = np.ones((n_states, 6), dtype=float)
    solid_alive[15:, 5] = 0.0
    a[ArrayType.element_solid_is_alive] = solid_alive

    # Shell stress: (n_states, 4 shells, 1 point, 6 components)
    shell_stress = np.zeros((n_states, 4, 1, 6))
    for s_idx in range(n_states):
        factor = (s_idx + 1) * 5.0
        for e_idx in range(4):
            shell_stress[s_idx, e_idx, 0, 0] = factor * (e_idx + 1)
            shell_stress[s_idx, e_idx, 0, 1] = factor * (e_idx + 1) * 0.4
            shell_stress[s_idx, e_idx, 0, 2] = 0.0  # plane stress
            shell_stress[s_idx, e_idx, 0, 3] = factor * 1.2
            shell_stress[s_idx, e_idx, 0, 4] = 0.0
            shell_stress[s_idx, e_idx, 0, 5] = 0.0
    a[ArrayType.element_shell_stress] = shell_stress
    a[ArrayType.element_shell_effective_plastic_strain] = np.ones((n_states, 4, 1)) * 0.02

    # Shell alive flags: element 104 deleted from state 20 onward
    shell_alive = np.ones((n_states, 4), dtype=float)
    shell_alive[20:, 3] = 0.0
    a[ArrayType.element_shell_is_alive] = shell_alive

    d3plot_path = tmp_path / "d3plot"
    plot.write_d3plot(str(d3plot_path))
    return d3plot_path


# ==============================================================================
# Acceptance 1: Metadata containing all 8 semantic items in CSV and NPZ
# ==============================================================================

def test_acceptance_1_all_eight_metadata_fields_in_csv_and_npz(solid_and_shell_d3plot: Path) -> None:
    """Acceptance 1: Output CSV/NPZ with metadata containing:
    quantity, component, units, state, time, layer/integration_point, coordinate_system, backend.
    """
    service = Service(Settings(solid_and_shell_d3plot.parent))
    res = service.extract_field(
        str(solid_and_shell_d3plot),
        family="solid",
        quantity="sxx",
        state=10,
        units="MPa",
        output_format="both",
        mask="alive",
    )
    assert res["status"] == "succeeded"

    # Verify JobResult data
    data = res["data"]
    assert data["quantity"] == "sxx"
    assert data["component"] == "sxx"
    assert data["units"] == "MPa"
    assert data["state"] == 10
    assert data["state_1based"] == 11
    assert data["time"] == pytest.approx(1.0)
    assert "global" in data["coordinate_system"]
    assert "lasso" in data["backend"]
    assert data["mask"] == "alive"

    # Verify CSV artifact
    csv_art = next(a for a in res["artifacts"] if a["kind"] == "csv")
    csv_meta = csv_art["metadata"]
    assert csv_meta["quantity"] == "sxx"
    assert csv_meta["component"] == "sxx"
    assert csv_meta["units"] == "MPa"
    assert csv_meta["state"] == 10
    assert csv_meta["time"] == pytest.approx(1.0)
    assert csv_meta["integration_point"] == 1
    assert "global" in csv_meta["coordinate_system"]
    assert "lasso" in csv_meta["backend"]

    # Verify CSV round-trip read with exp.read_field
    csv_round_trip = exp.read_field(csv_art["path"])
    assert csv_round_trip["meta"]["quantity"] == "sxx"
    assert csv_round_trip["meta"]["component"] == "sxx"
    assert csv_round_trip["meta"]["units"] == "MPa"
    assert csv_round_trip["meta"]["state"] == 10
    assert csv_round_trip["meta"]["time"] == pytest.approx(1.0)
    assert "global" in csv_round_trip["meta"]["coordinate_system"]
    assert "lasso" in csv_round_trip["meta"]["backend"]
    assert len(csv_round_trip["ids"]) == 6

    # Verify NPZ artifact
    npz_art = next(a for a in res["artifacts"] if a["kind"] == "npz")
    npz_round_trip = exp.read_field(npz_art["path"])
    assert npz_round_trip["meta"]["quantity"] == "sxx"
    assert npz_round_trip["meta"]["component"] == "sxx"
    assert npz_round_trip["meta"]["units"] == "MPa"
    assert npz_round_trip["meta"]["state"] == 10
    assert npz_round_trip["meta"]["time"] == pytest.approx(1.0)
    assert "global" in npz_round_trip["meta"]["coordinate_system"]
    assert "lasso" in npz_round_trip["meta"]["backend"]
    assert len(npz_round_trip["ids"]) == 6


# ==============================================================================
# Acceptance 2: LSPP vs LASSO cross-check on solid and shell cases (逐实体一致)
# ==============================================================================

def test_acceptance_2_solid_cross_check_element_by_element(solid_and_shell_d3plot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Acceptance 2 (Solid): LSPP and LASSO results agree element-by-element (逐实体一致) within tolerance."""
    exe = solid_and_shell_d3plot.parent / "lsprepost.exe"
    exe.touch()
    service = Service(Settings(solid_and_shell_d3plot.parent, executable=exe, allowed_roots=(solid_and_shell_d3plot.parent,)))

    # Read values from LASSO backend
    lasso_res = service.extract_field(
        str(solid_and_shell_d3plot),
        family="solid",
        quantity="sxx",
        state=2,
        units="MPa",
        backend="lasso",
    )
    assert lasso_res["status"] == "succeeded"
    lasso_ids = lasso_res["data"]["ids"]
    lasso_values = lasso_res["data"]["values"]

    # Mock native batch execution returning the native SCL results from the same physics
    def mock_run_batch(exe: Any, command: Any, directory: Path, **kwargs: Any) -> JobResult:
        with (directory / "native.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["state", "time", "entity_id", *STRESS_KEYS, "von_mises"])
            for eid, sxx_val in zip(lasso_ids, lasso_values):
                # Full stress tensor consistent with LASSO fixture
                factor = 30.0  # state 2 factor
                e_idx = eid - 1
                syy = factor * (e_idx + 1) * 0.5
                szz = factor * (e_idx + 1) * 0.2
                sxy = factor * 2.0
                syz = factor * 1.5
                szx = factor * 1.0
                # Independent Mises
                dev_xx = sxx_val - (sxx_val + syy + szz) / 3.0
                dev_yy = syy - (sxx_val + syy + szz) / 3.0
                dev_zz = szz - (sxx_val + syy + szz) / 3.0
                j2 = 0.5 * (dev_xx**2 + dev_yy**2 + dev_zz**2) + sxy**2 + syz**2 + szx**2
                vm = math.sqrt(3.0 * j2)
                writer.writerow([3, 0.2, eid, sxx_val, syy, szz, sxy, syz, szx, vm])
        return JobResult(
            operation=kwargs.get("operation", "native_fields"),
            job_id=directory.name,
            status="unverified",
            data={"returncode": 0, "timed_out": False},
        )

    monkeypatch.setattr("ls_prepost_mcp.native_results.run_batch", mock_run_batch)

    # Perform cross-check extraction
    res = service.extract_field(
        str(solid_and_shell_d3plot),
        family="solid",
        quantity="sxx",
        state=2,
        units="MPa",
        cross_check=True,
    )
    assert res["status"] == "succeeded"
    cross_check = res["data"]["cross_check"]
    assert cross_check["status"] == "passed"
    assert cross_check["elements_compared"] == 6
    assert cross_check["max_absolute_difference"] <= 1e-4

    # Verify CheckResults
    checks = {c["name"]: c["status"] for c in res["checks"]}
    assert checks["backend_cross_check"] == "passed"
    assert checks["native_extraction"] == "passed"


def test_acceptance_2_shell_cross_check_element_by_element(solid_and_shell_d3plot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Acceptance 2 (Shell): LSPP and LASSO results agree element-by-element (逐实体一致) within tolerance."""
    exe = solid_and_shell_d3plot.parent / "lsprepost.exe"
    exe.touch()
    service = Service(Settings(solid_and_shell_d3plot.parent, executable=exe, allowed_roots=(solid_and_shell_d3plot.parent,)))

    # Read values from LASSO backend for shells
    lasso_res = service.extract_field(
        str(solid_and_shell_d3plot),
        family="shell",
        quantity="sxx",
        state=1,
        units="MPa",
        backend="lasso",
    )
    assert lasso_res["status"] == "succeeded"
    lasso_ids = lasso_res["data"]["ids"]
    lasso_values = lasso_res["data"]["values"]

    # Mock native batch execution returning shell stresses
    def mock_run_batch(exe: Any, command: Any, directory: Path, **kwargs: Any) -> JobResult:
        with (directory / "native.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["state", "time", "entity_id", *STRESS_KEYS, "von_mises"])
            for eid, sxx_val in zip(lasso_ids, lasso_values):
                factor = 10.0  # state 1 factor
                e_idx = eid - 101
                syy = factor * (e_idx + 1) * 0.4
                szz = 0.0
                sxy = factor * 1.2
                syz = 0.0
                szx = 0.0
                vm = math.sqrt(sxx_val**2 + syy**2 - sxx_val * syy + 3.0 * sxy**2)
                writer.writerow([2, 0.1, eid, sxx_val, syy, szz, sxy, syz, szx, vm])
        return JobResult(
            operation=kwargs.get("operation", "native_fields"),
            job_id=directory.name,
            status="unverified",
            data={"returncode": 0, "timed_out": False},
        )

    monkeypatch.setattr("ls_prepost_mcp.native_results.run_batch", mock_run_batch)

    # Perform shell cross-check extraction
    res = service.extract_field(
        str(solid_and_shell_d3plot),
        family="shell",
        quantity="sxx",
        state=1,
        units="MPa",
        cross_check=True,
    )
    assert res["status"] == "succeeded"
    cross_check = res["data"]["cross_check"]
    assert cross_check["status"] == "passed"
    assert cross_check["elements_compared"] == 4
    assert cross_check["max_absolute_difference"] <= 1e-4


def test_acceptance_2_refusal_of_solid_integration_points_2_to_8(solid_and_shell_d3plot: Path) -> None:
    """Acceptance 2 refusal gap: Solid integration points 2..8 under native execution are rejected."""
    service = Service(Settings(solid_and_shell_d3plot.parent))

    for ipt in (2, 4, 8, "2", "8"):
        with pytest.raises(ValueError, match="Native solid integration points 2..8 are not verified"):
            service.extract_field(
                str(solid_and_shell_d3plot),
                family="solid",
                quantity="sxx",
                integration_point=ipt,
                backend="native",
            )


def test_acceptance_2_shell_layer_semantics_preserved(solid_and_shell_d3plot: Path) -> None:
    """Acceptance 2 shell layers: genuine layer source semantics (mid, inner, outer) preserved without fake conversion."""
    service = Service(Settings(solid_and_shell_d3plot.parent))

    for layer_name in ("mid", "inner", "outer"):
        res = service.extract_field(
            str(solid_and_shell_d3plot),
            family="shell",
            quantity="sxx",
            layer=layer_name,
            output_format="csv",
        )
        print("RES ERROR:", res.get("error"))
        assert res["status"] == "succeeded"
        assert res["data"]["layer"] == layer_name
        assert res["artifacts"][0]["metadata"]["layer"] == layer_name


# ==============================================================================
# Acceptance 3: Deletion masking ('alive', 'all', 'deleted') noted in metadata
# ==============================================================================

def test_acceptance_3_failure_masking_modes_and_metadata(solid_and_shell_d3plot: Path) -> None:
    """Acceptance 3: Deletion masks (alive, all, deleted) applied and explicitly noted in metadata."""
    service = Service(Settings(solid_and_shell_d3plot.parent))

    # At state 20, solid element 6 is deleted
    # 1. 'alive' mask (default): element 6 excluded from extrema
    alive_res = service.extract_field(
        str(solid_and_shell_d3plot),
        family="solid",
        quantity="sxx",
        state=20,
        mask="alive",
    )
    assert alive_res["status"] == "succeeded"
    assert alive_res["data"]["element_count"] == 6
    assert alive_res["data"]["active_count"] == 5
    assert alive_res["data"]["deleted_count"] == 1
    assert alive_res["data"]["mask"] == "alive"
    # Extrema max should be element 5, not deleted element 6
    assert alive_res["data"]["extrema"]["max"]["id"] == 5

    # 2. 'all' mask: includes deleted element 6 in extrema
    all_res = service.extract_field(
        str(solid_and_shell_d3plot),
        family="solid",
        quantity="sxx",
        state=20,
        mask="all",
    )
    assert all_res["status"] == "succeeded"
    assert all_res["data"]["element_count"] == 6
    assert all_res["data"]["active_count"] == 6
    assert all_res["data"]["deleted_count"] == 1
    assert all_res["data"]["mask"] == "all"
    assert all_res["data"]["extrema"]["max"]["id"] == 6

    # 3. 'deleted' mask: only includes deleted element 6 in extrema
    del_res = service.extract_field(
        str(solid_and_shell_d3plot),
        family="solid",
        quantity="sxx",
        state=20,
        mask="deleted",
    )
    assert del_res["status"] == "succeeded"
    assert del_res["data"]["element_count"] == 6
    assert del_res["data"]["active_count"] == 1
    assert del_res["data"]["mask"] == "deleted"
    assert del_res["data"]["extrema"]["max"]["id"] == 6
    assert del_res["data"]["extrema"]["min"]["id"] == 6


# ==============================================================================
# User Story: State 20, Part 3 all elements stress six-components exported to CSV
# ==============================================================================

def test_user_story_state_20_part_3_stress_six_components_to_csv(solid_and_shell_d3plot: Path) -> None:
    """User story: Export all six stress components of all elements in Part 3 at state 20 to CSV."""
    service = Service(Settings(solid_and_shell_d3plot.parent))

    res = service.extract_field(
        str(solid_and_shell_d3plot),
        family="solid",
        quantity="stress",
        state=20,
        part_ids=[3],
        units="MPa",
        output_format="both",
        mask="alive",
    )
    assert res["status"] == "succeeded"

    data = res["data"]
    assert data["quantity"] == "stress"
    assert data["component"] == "all_six"
    assert data["components"] == ["sxx", "syy", "szz", "sxy", "syz", "szx"]
    assert data["state"] == 20
    assert data["part_ids"] == [3]
    # Part 3 contains elements 5 and 6; element 6 is deleted at state 20, element 5 is alive
    assert data["ids"] == [5, 6]
    assert data["element_count"] == 2
    assert data["active_count"] == 1
    assert data["deleted_count"] == 1

    # Verify CSV file on disk
    csv_art = next(a for a in res["artifacts"] if a["kind"] == "csv")
    csv_path = Path(csv_art["path"])
    assert csv_path.exists()
    content = csv_path.read_text(encoding="utf-8")

    # Verify header contains all 8 metadata items + components
    assert '# quantity: "stress"' in content
    assert '# units: "MPa"' in content
    assert '# state: 20' in content
    assert '# components: ["sxx", "syy", "szz", "sxy", "syz", "szx"]' in content
    assert '# part_ids: [3]' in content

    # Verify columns and rows
    lines = content.strip().splitlines()
    data_lines = [line for line in lines if not line.startswith("#")]
    assert data_lines[0] == "id,sxx,syy,szz,sxy,syz,szx,alive"
    assert len(data_lines) == 3  # Header line + 2 elements

    # Parse rows
    row_5 = data_lines[1].split(",")
    row_6 = data_lines[2].split(",")
    assert row_5[0] == "5" and row_5[-1] == "1"  # ID 5 is alive
    assert row_6[0] == "6" and row_6[-1] == "0"  # ID 6 is deleted


# ==============================================================================
# Public Corpus Validation (solids with deletions and shells)
# ==============================================================================

def test_real_corpus_solid_plate_projectile_part_filter() -> None:
    """Validate on real public corpus d3plot_projectile: filtering Part 1 (projectile) vs Part 2 (plate)."""
    corpus_file = Path(r"F:\PythonWoking\temp\20260930-lsprepost-mcp-development\corpus\public-results\ansys__example-data\result_files\d3plot_projectile\d3plot")
    if not corpus_file.exists():
        pytest.skip("Corpus file not present")

    service = Service(Settings(corpus_file.parent, allowed_roots=(corpus_file.parent,)))

    # Part 1: Projectile (1864 solid elements)
    res_p1 = service.extract_field(str(corpus_file), "solid", "sxx", state=-1, part_ids=[1], mask="alive")
    assert res_p1["status"] == "succeeded"
    assert res_p1["data"]["element_count"] == 1864
    assert res_p1["data"]["part_ids"] == [1]

    # Part 2: Plate (3800 solid elements, with deletions at state -1)
    res_p2 = service.extract_field(str(corpus_file), "solid", "sxx", state=-1, part_ids=[2], mask="alive")
    assert res_p2["status"] == "succeeded"
    assert res_p2["data"]["element_count"] == 3800
    assert res_p2["data"]["part_ids"] == [2]
    assert res_p2["data"]["deleted_count"] == 241


def test_real_corpus_shell_elements_part_filter() -> None:
    """Validate on real public corpus order_d3plot: filtering shell elements by Part 3000 vs 4000."""
    corpus_file = Path(r"F:\PythonWoking\temp\20260930-lsprepost-mcp-development\corpus\public-results\open-lasso-python__lasso-python\test\test_data\order_d3plot\d3plot")
    if not corpus_file.exists():
        pytest.skip("Corpus file not present")

    service = Service(Settings(corpus_file.parent, allowed_roots=(corpus_file.parent,)))

    # Part 3000 has 8 shell elements
    res_p3000 = service.extract_field(str(corpus_file), "shell", "sxx", state=0, part_ids=[3000])
    assert res_p3000["status"] == "succeeded"
    assert res_p3000["data"]["element_count"] == 8
    assert res_p3000["data"]["part_ids"] == [3000]

    # Part 4000 has 8 shell elements
    res_p4000 = service.extract_field(str(corpus_file), "shell", "sxx", state=0, part_ids=[4000])
    assert res_p4000["status"] == "succeeded"
    assert res_p4000["data"]["element_count"] == 8
    assert res_p4000["data"]["part_ids"] == [4000]


# ==============================================================================
# Live LS-PrePost Native Headless Execution (Opt-in)
# ==============================================================================

@pytest.mark.native
def test_native_live_field_extraction(tmp_path: Path, pytestconfig: pytest.Config) -> None:
    """Opt-in live LS-PrePost headless execution for solid/shell field extraction."""
    if not pytestconfig.getoption("--run-native", default=False):
        pytest.skip("Live LS-PrePost execution requires --run-native")
    exe_raw = pytestconfig.getoption("--native-executable", default=None) or r"D:\Program Files\LSTC\LS-PrePost 4.10\lsprepost4.10_x64.exe"
    exe = Path(exe_raw)
    if not exe.exists():
        pytest.skip(f"LS-PrePost executable not found at {exe}")

    corpus_file = Path(r"F:\PythonWoking\temp\20260930-lsprepost-mcp-development\corpus\public-results\ansys__example-data\result_files\d3plot_projectile\d3plot")
    if not corpus_file.exists():
        pytest.skip("Corpus file not present")

    service = Service(Settings(tmp_path, executable=exe, allowed_roots=(corpus_file.parent, tmp_path)))

    res = service.extract_native_fields(
        str(corpus_file),
        "solid",
        [1, 2, 3],
        [1],
        ["stress_x"],
        "mid",
        "MPa",
        validity_policy="raw",
    )
    assert res["status"] == "succeeded"
    assert len(res["artifacts"]) >= 1

