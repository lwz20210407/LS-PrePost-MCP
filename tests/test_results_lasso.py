"""LASSO result backend on a d3plot written by lasso itself (no LS-DYNA run needed).

The backend was also checked against LS-DYNA R11 output of one run written both ways (d3plot
and binout vs ASCII nodout / glstat / elout): node displacement, global energies, binout curves
and all six solid stress components agree within single precision (<= 3.4e-5 relative).
"""
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("lasso")
from lasso.dyna import ArrayType, D3plot  # noqa: E402

from ls_prepost_mcp.domain.results import lasso_backend as lb  # noqa: E402

CUBE = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)


@pytest.fixture()
def d3plot(tmp_path: Path) -> Path:
    """Two solids (IDs 10, 20) in parts 1 and 2; three states; element 20 deleted in the last one."""
    coords = np.vstack([CUBE, CUBE + [0, 0, 1]])
    times = np.array([0.0, 1.0, 2.0])
    plot = D3plot()
    a = plot.arrays
    a[ArrayType.node_coordinates] = coords
    a[ArrayType.node_ids] = np.arange(1, 17)
    a[ArrayType.element_solid_node_indexes] = np.array([np.arange(8), np.arange(8, 16)])
    a[ArrayType.element_solid_part_indexes] = np.array([0, 1])
    a[ArrayType.element_solid_ids] = np.array([10, 20])
    a[ArrayType.part_titles_ids] = np.array([1, 2])
    a[ArrayType.part_titles] = np.array([b"lower".ljust(72), b"upper".ljust(72)])
    a[ArrayType.global_timesteps] = times
    displaced = np.repeat(coords[None], 3, axis=0)
    displaced[:, 8:, 2] += times[:, None] * 0.1  # the upper block moves up
    a[ArrayType.node_displacement] = displaced
    stress = np.zeros((3, 2, 1, 6))
    stress[:, 0, 0, 0] = [0.0, 100.0, 200.0]  # element 10: uniaxial
    stress[:, 1, 0, 3] = [0.0, 50.0, 60.0]  # element 20: shear
    a[ArrayType.element_solid_stress] = stress
    a[ArrayType.element_solid_effective_plastic_strain] = np.zeros((3, 2, 1))
    a[ArrayType.element_solid_is_alive] = np.array([[1, 1], [1, 1], [1, 0]], dtype=float)
    plot.write_d3plot(str(tmp_path / "d3plot"))
    return tmp_path / "d3plot"


def test_overview(d3plot: Path) -> None:
    info = lb.overview(d3plot)
    assert info["states"] == 3 and info["time_range"] == [0.0, 2.0]
    assert info["elements"] == {"solid": {"count": 2, "history_variables": 0, "deleted_at_last_state": 1}}
    assert info["parts"] == [{"id": 1, "title": "lower"}, {"id": 2, "title": "upper"}]


def test_histories(d3plot: Path) -> None:
    node = lb.history(d3plot, "node", "displacement_z", [16, 1])
    assert np.allclose(node[0]["values"], [0.0, 0.1, 0.2], atol=1e-6) and node[1]["values"] == [0.0, 0.0, 0.0]
    solid = lb.history(d3plot, "solid", "von_mises", [20])[0]
    assert np.allclose(solid["values"], [0.0, 50 * np.sqrt(3), 60 * np.sqrt(3)], rtol=1e-6)
    assert solid["note"].startswith("mean of 1 stored points")
    with pytest.raises(lb.ResultsError, match="not in the result"):
        lb.history(d3plot, "solid", "sxx", [99])
    with pytest.raises(lb.ResultsError, match="Unknown element quantity"):
        lb.history(d3plot, "solid", "temperature", [10])


def test_field_masks(d3plot: Path) -> None:
    alive = lb.field(d3plot, "solid", "von_mises", state=-1)
    assert alive["state"] == 2 and alive["extrema"] == {"count": 1, "min": {"value": 200.0, "id": 10},
                                                        "max": {"value": 200.0, "id": 10}}
    every = lb.field(d3plot, "solid", "triaxiality", state=-1, mask="all")
    assert every["extrema"]["max"] == {"value": pytest.approx(1 / 3), "id": 10}
    assert every["extrema"]["min"]["id"] == 20 and every["extrema"]["min"]["value"] == pytest.approx(0.0)
