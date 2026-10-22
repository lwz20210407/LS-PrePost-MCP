"""Tests for tasks.yaml Q04: field metrics and failure masks (extract_field).

Verifies:
1. von Mises, principal stresses, triaxiality, Lode parameter, Lode angle, and effective plastic strain
   on both solid and shell elements match independent calculations from textbook formulas.
2. Formula definitions and Lode conventions written into result metadata.
3. Mask strategies (alive, all, deleted) filter correctly, and extrema return entity ID and state.
4. Public state numbers are 1-based (-1 or "last" for the last state); anything else is refused
   before a job is created, never wrapped.
5. Part filtering by user part ID (the story: all elements of the target plate), including files
   that only carry part_titles_ids.
6. Export to CSV / NPZ and round-trip verification with read_field.
7. Error handling, input validation, and JobResult/v1 contract compliance.
8. Opt-in public corpus validation (LSPP_CORPUS_DIR): target-plate maximum on a solid penetration
   model with deletions, and shells against an independent calculation.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import pytest
import yaml

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.results import export as exp
from ls_prepost_mcp.domain.results import lasso_backend as lb
from ls_prepost_mcp.service import Service

pytest.importorskip("lasso")
from lasso.dyna import ArrayType, D3plot  # noqa: E402

MANIFEST = Path(__file__).parent / "corpus" / "manifest.yaml"
PART_IDS = np.array([7, 9, 300, 400])  # sparse user IDs: solids in 7 / 9, shells in 300 / 400


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


def write_synthetic(plot_path: Path, part_key: ArrayType = ArrayType.part_titles_ids, deletion: bool = True) -> Path:
    """Synthetic d3plot with solids and shells across 3 states with deletions and sparse part IDs."""
    plot = D3plot()
    a = plot.arrays

    a[ArrayType.global_timesteps] = np.array([0.0, 0.5, 1.0])

    # 4 solids: IDs 10, 20 (part 7) and 30, 40 (part 9)
    # 4 shells: IDs 101, 102 (part 300) and 103, 104 (part 400)
    a[ArrayType.node_ids] = np.arange(1, 25)
    a[ArrayType.node_coordinates] = np.zeros((24, 3))

    a[ArrayType.element_solid_ids] = np.array([10, 20, 30, 40])
    a[ArrayType.element_solid_part_indexes] = np.array([0, 0, 1, 1])
    a[ArrayType.element_solid_node_indexes] = np.zeros((4, 8), dtype=int)

    a[ArrayType.element_shell_ids] = np.array([101, 102, 103, 104])
    a[ArrayType.element_shell_part_indexes] = np.array([2, 2, 3, 3])
    a[ArrayType.element_shell_node_indexes] = np.zeros((4, 4), dtype=int)

    a[part_key] = PART_IDS
    if part_key == ArrayType.part_titles_ids:
        a[ArrayType.part_titles] = np.array([b"projectile", b"plate", b"skin", b"rib"])

    # Stresses (states=3, elements=4, points=1, components=6); only the last state is loaded
    solid_stress = np.zeros((3, 4, 1, 6))
    solid_stress[2, 0, 0, :] = [200.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # 10: uniaxial tension
    solid_stress[2, 1, 0, :] = [0.0, 0.0, 0.0, 60.0, 0.0, 0.0]  # 20: pure shear
    solid_stress[2, 2, 0, :] = [150.0, 150.0, 0.0, 0.0, 0.0, 0.0]  # 30: equibiaxial tension
    solid_stress[2, 3, 0, :] = [-100.0, -100.0, -100.0, 0.0, 0.0, 0.0]  # 40: hydrostatic pressure
    a[ArrayType.element_solid_stress] = solid_stress

    shell_stress = np.zeros((3, 4, 1, 6))
    shell_stress[2, 0, 0, :] = [300.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # 101: uniaxial tension
    shell_stress[2, 1, 0, :] = [0.0, 0.0, 0.0, 80.0, 0.0, 0.0]  # 102: pure shear
    shell_stress[2, 2, 0, :] = [180.0, 180.0, 0.0, 0.0, 0.0, 0.0]  # 103: equibiaxial tension
    a[ArrayType.element_shell_stress] = shell_stress  # 104: zero stress

    solid_eps = np.zeros((3, 4, 1))
    solid_eps[2, :, 0] = [0.05, 0.12, 0.08, 0.0]
    a[ArrayType.element_solid_effective_plastic_strain] = solid_eps

    shell_eps = np.zeros((3, 4, 1))
    shell_eps[2, :, 0] = [0.03, 0.15, 0.09, 0.0]
    a[ArrayType.element_shell_effective_plastic_strain] = shell_eps

    # Deletions: solid 20 and shell 102 are deleted at the last state
    deleted_last = np.array([[1, 1, 1, 1], [1, 1, 1, 1], [1, 0, 1, 1]], dtype=float)
    if deletion:  # deletion=False writes a d3plot without element deletion data
        a[ArrayType.element_solid_is_alive] = deleted_last
        a[ArrayType.element_shell_is_alive] = deleted_last.copy()

    plot.write_d3plot(str(plot_path))
    return plot_path


@pytest.fixture()
def synthetic_d3plot(tmp_path: Path) -> Path:
    folder = tmp_path / "model"
    folder.mkdir()
    return write_synthetic(folder / "d3plot")


@pytest.fixture()
def service(synthetic_d3plot: Path, tmp_path: Path) -> Service:
    return Service(Settings(tmp_path / "work", allowed_roots=(synthetic_d3plot.parent,)))


def test_independent_calculation_match_solids(service: Service, synthetic_d3plot: Path) -> None:
    """Acceptance 1: Mises, principals, triaxiality, Lode param/angle, plastic strain on solids match independent calculation."""
    stresses = {
        10: np.array([200.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
        20: np.array([0.0, 0.0, 0.0, 60.0, 0.0, 0.0]),
        30: np.array([150.0, 150.0, 0.0, 0.0, 0.0, 0.0]),
        40: np.array([-100.0, -100.0, -100.0, 0.0, 0.0, 0.0]),
    }

    quantities = [
        "von_mises", "principal_1", "principal_2", "principal_3", "max_shear", "triaxiality",
        "lode_parameter", "lode_angle_rad", "lode_angle_parameter", "mean_stress", "pressure"
    ]

    for q in quantities:
        res = service.extract_field(str(synthetic_d3plot), "solid", q, state=3, mask="all")
        assert res["status"] == "succeeded"
        for eid, val in zip(res["data"]["ids"], res["data"]["values"]):
            expected = independent_stress_metrics(stresses[eid])[q]
            if math.isnan(expected):
                assert val == "nan" or val is None or math.isnan(float(val))
            else:
                assert float(val) == pytest.approx(expected, rel=1e-6, abs=1e-9)

    eps_res = service.extract_field(str(synthetic_d3plot), "solid", "effective_plastic_strain", state=3, mask="all")
    assert eps_res["status"] == "succeeded"
    assert [float(v) for v in eps_res["data"]["values"]] == pytest.approx([0.05, 0.12, 0.08, 0.0], rel=1e-5)


def test_independent_calculation_match_shells(service: Service, synthetic_d3plot: Path) -> None:
    """Acceptance 1: Mises, principals, triaxiality, Lode param/angle, plastic strain on shells match independent calculation."""
    stresses = {
        101: np.array([300.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
        102: np.array([0.0, 0.0, 0.0, 80.0, 0.0, 0.0]),
        103: np.array([180.0, 180.0, 0.0, 0.0, 0.0, 0.0]),
        104: np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
    }

    quantities = [
        "von_mises", "principal_1", "principal_2", "principal_3", "max_shear", "triaxiality",
        "lode_parameter", "lode_angle_rad", "lode_angle_parameter"
    ]

    for q in quantities:
        res = service.extract_field(str(synthetic_d3plot), "shell", q, state=3, mask="all")
        assert res["status"] == "succeeded"
        for eid, val in zip(res["data"]["ids"], res["data"]["values"]):
            expected = independent_stress_metrics(stresses[eid])[q]
            if math.isnan(expected):
                assert val == "nan" or val is None or math.isnan(float(val))
            else:
                assert float(val) == pytest.approx(expected, rel=1e-6, abs=1e-9)

    eps_res = service.extract_field(str(synthetic_d3plot), "shell", "effective_plastic_strain", state=3, mask="all")
    assert eps_res["status"] == "succeeded"
    assert [float(v) for v in eps_res["data"]["values"]] == pytest.approx([0.03, 0.15, 0.09, 0.0], rel=1e-5)


def test_metadata_and_lode_conventions(service: Service, synthetic_d3plot: Path) -> None:
    """Acceptance 2: Formula definition and Lode sign conventions are written into result metadata."""
    res = service.extract_field(str(synthetic_d3plot), "solid", "lode_parameter", state=3, units="MPa")
    assert res["status"] == "succeeded"
    data = res["data"]

    conv = data["conventions"]
    assert "(2 s2 - s1 - s3) / (s1 - s3)" in conv["lode_parameter"]
    assert "lode_angle" in conv
    assert "lode_angle_parameter" in conv
    assert "deviatoric quantities are NaN" in conv["undefined"]

    assert data["formula"] == conv["lode_parameter"]
    assert data["units"] == "MPa"

    # Every computed quantity names its own definition, not a generic placeholder
    for quantity, fragment in (("principal_1", "eigenvalue"), ("max_shear", "(s1 - s3) / 2"),
                               ("mean_stress", "I1/3"), ("sxx", "stored"),
                               ("effective_plastic_strain", "stored"), ("lode_angle_rad", "theta")):
        formula = service.extract_field(str(synthetic_d3plot), "solid", quantity, state=3)["data"]["formula"]
        assert fragment in formula, (quantity, formula)


@pytest.mark.parametrize(("quantity", "fragments"), [
    ("lode_parameter", ["(2 s2 - s1 - s3) / (s1 - s3)", "[-1, 1]", "-1 uniaxial tension", "+1 uniaxial compression"]),
    ("lode_angle_rad", ["acos", "J3 / J2^1.5", "[0, pi/3]", "0 uniaxial tension", "pi/3 uniaxial compression"]),
    ("lode_angle_parameter", ["1 - 6 theta / pi", "[-1, 1]", "+1 uniaxial tension", "-1 uniaxial compression"]),
    ("triaxiality", ["sigma_m / sigma_vm"]),
])
def test_formula_and_sign_conventions_in_result_and_artifacts(service: Service, synthetic_d3plot: Path,
                                                              quantity: str, fragments: list[str]) -> None:
    """Codex P1-b: each quantity carries its formula with range and sign meaning, and the CSV/NPZ
    artifacts carry the same formula and the full convention table."""
    res = service.extract_field(str(synthetic_d3plot), "solid", quantity, state=3, output_format="both")
    formula = res["data"]["formula"]
    for fragment in fragments:
        assert fragment in formula, (quantity, fragment, formula)
    assert len(res["artifacts"]) == 2
    for artifact in res["artifacts"]:
        meta = exp.read_field(artifact["path"])["meta"]
        assert meta["formula"] == formula
        assert meta["conventions"]["lode_parameter"] == res["data"]["conventions"]["lode_parameter"]
        assert "undefined" in meta["conventions"]
    # the stated signs hold on the synthetic states: 10 uniaxial tension, 30 equibiaxial tension
    values = dict(zip(res["data"]["ids"], res["data"]["values"]))
    if quantity == "lode_parameter":
        assert values[10] == pytest.approx(-1.0) and values[30] == pytest.approx(1.0)
    if quantity == "lode_angle_rad":
        assert values[10] == pytest.approx(0.0, abs=1e-6) and values[30] == pytest.approx(math.pi / 3)
    if quantity == "lode_angle_parameter":
        assert values[10] == pytest.approx(1.0) and values[30] == pytest.approx(-1.0)


def test_mask_modes_and_extrema_with_id_and_state(service: Service, synthetic_d3plot: Path) -> None:
    """Acceptance 3: Mask strategies (alive, all, deleted) selectable; extrema include entity ID and 1-based state."""
    res_alive = service.extract_field(str(synthetic_d3plot), "solid", "von_mises", state=3, mask="alive")
    assert res_alive["status"] == "succeeded"
    ext_alive = res_alive["data"]["extrema"]
    assert ext_alive["count"] == 3  # elements 10, 30, 40 (20 is deleted)
    assert ext_alive["max"]["id"] == 10
    assert ext_alive["max"]["value"] == pytest.approx(200.0)
    assert ext_alive["max"]["state"] == 3
    assert ext_alive["min"]["id"] == 40
    assert ext_alive["min"]["value"] == pytest.approx(0.0)
    assert ext_alive["min"]["state"] == 3

    ext_all = service.extract_field(str(synthetic_d3plot), "solid", "von_mises", state=3, mask="all")["data"]["extrema"]
    assert ext_all["count"] == 4
    assert ext_all["max"]["id"] == 10
    assert ext_all["max"]["state"] == 3

    ext_del = service.extract_field(str(synthetic_d3plot), "solid", "von_mises", state=3, mask="deleted")["data"]["extrema"]
    assert ext_del["count"] == 1
    assert ext_del["min"]["id"] == 20
    assert ext_del["min"]["value"] == pytest.approx(60.0 * math.sqrt(3.0))
    assert ext_del["max"]["id"] == 20
    assert ext_del["max"]["state"] == 3

    ext_s_alive = service.extract_field(str(synthetic_d3plot), "shell", "von_mises", state=3, mask="alive")["data"]["extrema"]
    assert ext_s_alive["count"] == 3  # shell 102 excluded
    assert ext_s_alive["max"]["id"] == 101
    assert ext_s_alive["max"]["state"] == 3

    ext_s_del = service.extract_field(str(synthetic_d3plot), "shell", "von_mises", state=3, mask="deleted")["data"]["extrema"]
    assert ext_s_del["count"] == 1
    assert ext_s_del["min"]["id"] == 102
    assert ext_s_del["min"]["state"] == 3
    assert ext_s_del["min"]["value"] == pytest.approx(80.0 * math.sqrt(3.0))


def test_state_is_one_based(service: Service, synthetic_d3plot: Path) -> None:
    """P1-82a: state=1 is the first state; -1, "last" and the default are the last state."""
    first = service.extract_field(str(synthetic_d3plot), "solid", "von_mises", state=1, mask="all")
    assert first["status"] == "succeeded"
    assert first["data"]["state"] == 1
    assert first["data"]["time"] == pytest.approx(0.0)
    assert first["data"]["extrema"]["max"]["state"] == 1

    second = service.extract_field(str(synthetic_d3plot), "solid", "von_mises", state=2, mask="all")
    assert second["data"]["state"] == 2 and second["data"]["time"] == pytest.approx(0.5)

    for last in (3, -1, "last", "LAST", None):
        kwargs = {} if last is None else {"state": last}
        res = service.extract_field(str(synthetic_d3plot), "solid", "von_mises", mask="all", **kwargs)
        assert res["status"] == "succeeded", last
        assert res["data"]["state"] == 3 and res["data"]["time"] == pytest.approx(1.0), last
        assert res["data"]["extrema"]["max"] == {"value": pytest.approx(200.0), "id": 10, "state": 3}

    csv = next(a for a in first["artifacts"] if a["kind"] == "csv")
    assert exp.read_field(csv["path"])["meta"]["state"] == 1
    assert Path(csv["path"]).name == "solid_von_mises_state_1.csv"


@pytest.mark.parametrize("state", [0, 4, -2, -4, True, False, 1.0, "first", "1", "", None])
def test_state_out_of_range_refused_before_job(service: Service, synthetic_d3plot: Path, state: object) -> None:
    """P1-82a: 0, n+1, other negatives, bools and other strings are refused before a job exists."""
    with pytest.raises(ValueError, match="(?i)state"):
        service.extract_field(str(synthetic_d3plot), "solid", "von_mises", state=state)
    assert service.jobs.list() == []


def test_mcp_layer_does_not_coerce_state_or_part_ids(synthetic_d3plot: Path, tmp_path: Path) -> None:
    """Through the MCP server, true / 1.0 are not coerced to state 1, nor true to part 1."""
    import asyncio

    from ls_prepost_mcp.server import build_server

    server = build_server(Settings(tmp_path / "work", allowed_roots=(synthetic_d3plot.parent,)), tool_profile="full")
    base = {"path": str(synthetic_d3plot), "family": "solid", "quantity": "von_mises", "output_format": "none"}
    for extra in ({"state": True}, {"state": 1.0}, {"part_ids": [True]}, {"part_ids": [9.0]}):
        with pytest.raises(Exception, match="(?i)state|part_ids|valid"):
            asyncio.run(server.call_tool("extract_field", {**base, **extra}))
    assert not (tmp_path / "work" / "jobs").exists()
    ok = asyncio.run(server.call_tool("extract_field", {**base, "state": 1, "part_ids": [9]}))
    assert '"state": 1' in str(ok)


def test_backend_field_refuses_out_of_range_state(synthetic_d3plot: Path) -> None:
    """The shared lasso_backend.field takes a 0-based index and refuses instead of wrapping it."""
    assert lb.field(synthetic_d3plot, "solid", "sxx", state=0)["state"] == 0
    assert lb.field(synthetic_d3plot, "solid", "sxx", state=-3)["state"] == 0
    for bad in (3, -4, True):
        with pytest.raises(lb.ResultsError, match="out of range"):
            lb.field(synthetic_d3plot, "solid", "sxx", state=bad)
    assert lb.state_times(synthetic_d3plot).tolist() == pytest.approx([0.0, 0.5, 1.0])


@pytest.mark.parametrize("part_key", [ArrayType.part_titles_ids, ArrayType.part_ids])
def test_backend_field_selects_parts_by_user_id(tmp_path: Path, part_key: ArrayType) -> None:
    """Part IDs resolve through part_ids or, when the file only has titles, part_titles_ids."""
    path = write_synthetic(tmp_path / "d3plot", part_key)
    plate = lb.field(path, "solid", "von_mises", state=-1, part_ids=[9])
    assert plate["ids"].tolist() == [30, 40]
    assert plate["part_ids"] == [9]
    assert plate["extrema"]["max"] == {"value": pytest.approx(150.0), "id": 30}
    both = lb.field(path, "shell", "von_mises", state=-1, mask="all", part_ids=[400, 300])
    assert both["ids"].tolist() == [101, 102, 103, 104]
    whole = lb.field(path, "solid", "von_mises", state=-1)
    assert whole["ids"].tolist() == [10, 20, 30, 40] and whole["part_ids"] is None
    with pytest.raises(lb.ResultsError, match="Part IDs not in the result"):
        lb.field(path, "solid", "von_mises", part_ids=[8])
    with pytest.raises(lb.ResultsError, match="no solid elements"):
        lb.field(path, "solid", "von_mises", part_ids=[300])


def test_part_filter_story_target_plate(service: Service, synthetic_d3plot: Path) -> None:
    """P1-82c story: all elements of the plate (part 9), deleted excluded, element of the maximum."""
    whole = service.extract_field(str(synthetic_d3plot), "solid", "von_mises")
    assert whole["data"]["extrema"]["max"]["id"] == 10  # projectile element wins without the filter

    plate = service.extract_field(str(synthetic_d3plot), "solid", "von_mises", part_ids=[9], output_format="both")
    assert plate["status"] == "succeeded"
    data = plate["data"]
    assert data["part_ids"] == [9]
    assert data["ids"] == [30, 40]
    assert data["element_count"] == 2
    assert data["extrema"]["max"] == {"value": pytest.approx(150.0), "id": 30, "state": 3}
    for artifact in plate["artifacts"]:
        back = exp.read_field(artifact["path"])
        assert back["ids"].tolist() == [30, 40]
        assert back["meta"]["part_ids"] == [9]

    projectile = service.extract_field(str(synthetic_d3plot), "solid", "von_mises", part_ids=[7])
    assert projectile["data"]["active_count"] == 1  # element 20 deleted
    deleted = service.extract_field(str(synthetic_d3plot), "solid", "von_mises", part_ids=[7], mask="deleted")
    assert deleted["data"]["extrema"]["max"]["id"] == 20

    rib = service.extract_field(str(synthetic_d3plot), "shell", "triaxiality", part_ids=[400])
    assert rib["data"]["ids"] == [103, 104]
    assert rib["data"]["extrema"]["max"]["id"] == 103


def test_part_filter_refusals(service: Service, synthetic_d3plot: Path) -> None:
    """Malformed part lists are refused before a job; unknown parts fail explicitly, never silently empty."""
    for bad in ([], [0], [-9], [True], ["9"], 9, [9, 9], "9"):
        with pytest.raises(ValueError, match="(?i)part"):
            service.extract_field(str(synthetic_d3plot), "solid", "von_mises", part_ids=bad)
    assert service.jobs.list() == []

    unknown = service.extract_field(str(synthetic_d3plot), "solid", "von_mises", part_ids=[8])
    assert unknown["status"] == "failed"
    assert "[8]" in unknown["error"]["message"]
    wrong_family = service.extract_field(str(synthetic_d3plot), "solid", "von_mises", part_ids=[300])
    assert wrong_family["status"] == "failed"
    assert "no solid elements" in wrong_family["error"]["message"]


def test_artifact_export_and_round_trip(service: Service, synthetic_d3plot: Path) -> None:
    """Verify CSV and NPZ export artifacts, hashes, and round-trip read."""
    res = service.extract_field(str(synthetic_d3plot), "solid", "triaxiality", state=3,
                                output_format="both", units="MPa")
    assert res["status"] == "succeeded"
    artifacts = res["artifacts"]
    assert len(artifacts) == 2

    csv_art = next(a for a in artifacts if a["kind"] == "csv")
    npz_art = next(a for a in artifacts if a["kind"] == "npz")

    csv_data = exp.read_field(csv_art["path"])
    assert csv_data["ids"].tolist() == [10, 30, 40]  # element 20 is deleted; default mask is alive
    assert csv_data["meta"]["quantity"] == "triaxiality"
    assert csv_data["meta"]["units"] == "MPa"
    assert csv_data["meta"]["state"] == 3

    npz_data = exp.read_field(npz_art["path"])
    assert npz_data["ids"].tolist() == [10, 30, 40]
    assert npz_data["meta"]["mask"] == "alive"


@pytest.mark.parametrize(("family", "mask", "rows", "excluded"), [
    ("solid", "alive", [10, 30, 40], 1), ("solid", "deleted", [20], 3), ("solid", "all", [10, 20, 30, 40], 0),
    ("shell", "alive", [101, 103, 104], 1), ("shell", "deleted", [102], 3),
])
def test_rows_and_artifacts_follow_mask(service: Service, synthetic_d3plot: Path, family: str, mask: str,
                                        rows: list[int], excluded: int) -> None:
    """Codex P1-a: the selected mask filters the returned rows and the CSV/NPZ rows, not only the extrema;
    the metadata states the mask policy and how many elements it excluded."""
    res = service.extract_field(str(synthetic_d3plot), family, "von_mises", state=3, mask=mask, output_format="both")
    assert res["status"] == "succeeded"
    data = res["data"]
    assert data["ids"] == rows
    assert len(data["values"]) == len(data["alive"]) == len(rows)
    assert all(data["alive"]) if mask == "alive" else True
    assert not any(data["alive"]) if mask == "deleted" else True
    assert data["element_count"] == 4 and data["row_count"] == len(rows) and data["excluded_by_mask"] == excluded
    assert data["mask_policy"]["mode"] == mask and data["mask_policy"]["excluded"] == excluded
    assert "deletion flag" in data["mask_policy"]["rule"] or mask == "all"
    for artifact in res["artifacts"]:
        back = exp.read_field(artifact["path"])
        assert back["ids"].tolist() == rows
        assert back["meta"]["rows"] == len(rows)
        assert back["meta"]["mask_policy"] == data["mask_policy"]


def test_missing_deletion_data_refuses_masks_that_need_it(tmp_path: Path) -> None:
    """Codex P1 (730a497): without stored deletion flags the elements are not assumed alive. mask alive /
    deleted are refused before a job; mask all works and reports the deletion status as unknown."""
    folder = tmp_path / "nodel"
    folder.mkdir()
    path = write_synthetic(folder / "d3plot", deletion=False)
    service = Service(Settings(tmp_path / "work", allowed_roots=(folder,)))
    for mask in ("alive", "deleted"):
        with pytest.raises(ValueError, match="deletion data"):
            service.extract_field(str(path), "solid", "von_mises", mask=mask)
        with pytest.raises(lb.ResultsError, match="no element deletion data"):
            lb.field(path, "solid", "von_mises", mask=mask)
    assert service.jobs.list() == []
    res = service.extract_field(str(path), "solid", "von_mises", mask="all", output_format="both")
    assert res["status"] == "succeeded"
    data = res["data"]
    assert data["ids"] == [10, 20, 30, 40] and data["alive"] is None
    assert data["mask_policy"]["deletion_status"].startswith("unknown")
    for artifact in res["artifacts"]:
        meta = exp.read_field(artifact["path"])["meta"]
        assert meta["deletion_status"].startswith("unknown")
    assert lb.field(path, "solid", "von_mises", mask="all")["deletion_data"] is False


def test_zero_row_export_round_trip(service: Service, synthetic_d3plot: Path) -> None:
    """Codex P2 (730a497): a zero-row result (first state, mask deleted) round-trips through CSV and NPZ."""
    res = service.extract_field(str(synthetic_d3plot), "solid", "von_mises", state=1, mask="deleted",
                                output_format="both")
    assert res["status"] == "succeeded"
    assert res["data"]["row_count"] == 0 and res["data"]["ids"] == [] and res["data"]["extrema"]["count"] == 0
    assert len(res["artifacts"]) == 2
    for artifact in res["artifacts"]:
        back = exp.read_field(artifact["path"])
        assert back["ids"].size == back["values"].size == back["alive"].size == 0
        assert back["meta"]["rows"] == 0 and back["meta"]["mask_policy"]["excluded"] == 4


def test_fastmcp_tool_registration(synthetic_d3plot: Path, tmp_path: Path) -> None:
    """Verify extract_field is registered as a first-class MCP tool."""
    from ls_prepost_mcp.server import build_server

    server = build_server(Settings(tmp_path / "work"), tool_profile="full")
    tool_names = {tool.name for tool in server._tool_manager.list_tools()}
    assert "extract_field" in tool_names
    assert "compute_stress_invariants" in tool_names
    assert "inspect_result_validity" in tool_names


def test_input_validation_and_refusals(service: Service, synthetic_d3plot: Path, tmp_path: Path) -> None:
    """Malformed requests and network paths are refused before creating a job."""
    with pytest.raises(ValueError, match="Unknown element family"):
        service.extract_field(str(synthetic_d3plot), "unknown_fam", "von_mises")
    with pytest.raises(ValueError, match="Unknown mask mode"):
        service.extract_field(str(synthetic_d3plot), "solid", "von_mises", mask="invalid_mask")
    with pytest.raises(ValueError, match="Unknown output format"):
        service.extract_field(str(synthetic_d3plot), "solid", "von_mises", output_format="docx")
    with pytest.raises(ValueError, match="Network path"):
        service.extract_field("//remote-server/share/d3plot", "solid", "von_mises")

    outside_file = tmp_path / "outside_file"
    outside_file.write_text("x")
    with pytest.raises(ValueError, match="outside the configured allowed roots"):
        service.extract_field(str(outside_file), "solid", "von_mises")
    assert service.jobs.list() == []


# Opt-in public corpus checks: LSPP_CORPUS_DIR points at the external corpus root (never committed);
# paths come from the registered IDs in tests/corpus/manifest.yaml. Jobs go to tmp_path, not the corpus.

def corpus_d3plot(corpus_id: str) -> Path:
    root = os.environ.get("LSPP_CORPUS_DIR")
    if not root:
        pytest.skip("set LSPP_CORPUS_DIR to the external corpus root")
    registry = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    entries = {e["id"]: e["path"] for section in ("result_sets", "regression_inputs") for e in registry.get(section, [])}
    path = Path(root) / entries[corpus_id]
    if path.is_dir():
        path = path / "d3plot"
    if not path.is_file():
        pytest.skip(corpus_id + " is not present under LSPP_CORPUS_DIR")
    return path


def raw_arrays(path: Path) -> dict:
    return {str(getattr(k, "value", k)): v for k, v in D3plot(str(path)).arrays.items()}


def user_part_ids(arrays: dict) -> np.ndarray:
    key = "part_ids" if np.asarray(arrays.get("part_ids", [])).size else "part_titles_ids"
    return np.asarray(arrays[key]).reshape(-1)


def test_corpus_story_target_plate_maximum(tmp_path: Path) -> None:
    """Story on d3plot_projectile: target plate (part 2) triaxiality and Lode parameter, deleted
    elements excluded, maximum element; checked against an independent read of the raw arrays."""
    source = corpus_d3plot("result.ansys__example-data.result_files.d3plot_projectile")
    service = Service(Settings(tmp_path / "work", allowed_roots=(source.parent,)))
    arrays = raw_arrays(source)
    owner = user_part_ids(arrays)[np.asarray(arrays["element_solid_part_indexes"]).reshape(-1)]
    in_plate = owner == 2
    states = np.asarray(arrays["timesteps"]).size
    alive = np.asarray(arrays["element_solid_is_alive"])[-1][in_plate] != 0
    stress = np.asarray(arrays["element_solid_stress"], dtype=float)[-1][in_plate]
    stress = stress.mean(axis=1) if stress.ndim == 3 else stress
    plate_ids = np.asarray(arrays["element_solid_ids"]).reshape(-1)[in_plate]

    for quantity in ("triaxiality", "lode_parameter"):
        res = service.extract_field(str(source), "solid", quantity, state="last", part_ids=[2])
        assert res["status"] == "succeeded"
        data = res["data"]
        assert data["state"] == states
        assert data["ids"] == plate_ids[alive].tolist()  # deleted plate elements are not returned
        assert data["element_count"] == int(in_plate.sum())
        assert data["excluded_by_mask"] == int((~alive).sum()) > 0
        assert data["active_count"] <= int(alive.sum())
        expected = np.array([independent_stress_metrics(s)[quantity] for s in stress])
        got = np.array([float(v) for v in data["values"]])
        assert np.array_equal(np.isnan(got), np.isnan(expected[alive]))
        assert np.allclose(got[~np.isnan(got)], expected[alive][~np.isnan(expected[alive])], rtol=1e-9, atol=1e-12)
        keep = alive & np.isfinite(expected)
        top = int(np.flatnonzero(keep)[np.argmax(expected[keep])])
        assert data["extrema"]["max"]["id"] == int(plate_ids[top])
        assert data["extrema"]["max"]["state"] == states
        direct = lb.field(source, "solid", quantity, state=-1, part_ids=[2])
        assert direct["extrema"]["max"]["id"] == data["extrema"]["max"]["id"]
        if quantity == "triaxiality":
            assert data["extrema"]["max"]["id"] == 2840
            assert data["extrema"]["max"]["value"] == pytest.approx(1.6415, abs=1e-4)
            whole = service.extract_field(str(source), "solid", quantity, state=-1)
            assert whole["data"]["extrema"]["max"]["id"] == 1681  # projectile element without the filter


def test_corpus_shells_match_independent_calculation(tmp_path: Path) -> None:
    """Shells on the registered shell_d3plot: per-element invariants (layer mean) match an
    independent calculation, and part filtering keeps exactly the shells of the requested part."""
    source = corpus_d3plot("shell_d3plot")
    service = Service(Settings(tmp_path / "work", allowed_roots=(source.parent,)))
    arrays = raw_arrays(source)
    stress = np.asarray(arrays["element_shell_stress"], dtype=float)[-1].mean(axis=1)
    ids = np.asarray(arrays["element_shell_ids"]).reshape(-1)
    owner = user_part_ids(arrays)[np.asarray(arrays["element_shell_part_indexes"]).reshape(-1)]

    for quantity in ("von_mises", "triaxiality", "lode_parameter", "principal_1"):
        res = service.extract_field(str(source), "shell", quantity, state=-1, mask="all")
        assert res["status"] == "succeeded"
        assert res["data"]["ids"] == ids.tolist()
        expected = np.array([independent_stress_metrics(s)[quantity] for s in stress])
        got = np.array([float(v) for v in res["data"]["values"]])
        assert np.array_equal(np.isnan(got), np.isnan(expected))
        assert np.allclose(got[~np.isnan(got)], expected[~np.isnan(expected)], rtol=1e-9, atol=1e-9)

    part = int(owner[0])
    filtered = service.extract_field(str(source), "shell", "von_mises", state=-1, part_ids=[part])
    assert filtered["data"]["ids"] == ids[owner == part].tolist()
