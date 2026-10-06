"""Q04 stress invariants against analytical stress states."""
import math

import numpy as np
import pytest

from ls_prepost_mcp.domain.results.invariants import extrema, invariants, masked

S = 300.0
STATES = {  # xx, yy, zz, xy, yz, zx -> (triaxiality, Lode parameter, Lode angle parameter)
    "uniaxial tension": ([S, 0, 0, 0, 0, 0], 1 / 3, -1.0, 1.0),
    "uniaxial compression": ([-S, 0, 0, 0, 0, 0], -1 / 3, 1.0, -1.0),
    "equibiaxial tension": ([S, S, 0, 0, 0, 0], 2 / 3, 1.0, -1.0),
    "pure shear": ([0, 0, 0, S, 0, 0], 0.0, 0.0, 0.0),
    "plane strain tension (nu=0.5)": ([S, S / 2, 0, 0, 0, 0], 1 / math.sqrt(3), 0.0, 0.0),
}


def test_analytical_states() -> None:
    names = list(STATES)
    q = invariants(np.array([STATES[n][0] for n in names]))
    for i, name in enumerate(names):
        _, eta, lode, lode_angle = STATES[name]
        assert q["triaxiality"][i] == pytest.approx(eta, abs=1e-12), name
        assert q["lode_parameter"][i] == pytest.approx(lode, abs=1e-12), name
        assert q["lode_angle_parameter"][i] == pytest.approx(lode_angle, abs=1e-7), name
    assert q["von_mises"][0] == pytest.approx(S) and q["von_mises"][3] == pytest.approx(math.sqrt(3) * S)
    assert q["principal_1"][3] == pytest.approx(S) and q["principal_3"][3] == pytest.approx(-S)


def test_rotation_invariance_and_hydrostatic_states() -> None:
    rng = np.random.default_rng(1)
    a = rng.normal(size=(50, 6)) * 100
    rotation, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    tensors = np.array([[[x, xy, zx], [xy, y, yz], [zx, yz, z]] for x, y, z, xy, yz, zx in a])
    turned = np.einsum("ij,njk,lk->nil", rotation, tensors, rotation)
    b = np.stack([turned[:, 0, 0], turned[:, 1, 1], turned[:, 2, 2], turned[:, 0, 1], turned[:, 1, 2],
                  turned[:, 0, 2]], axis=1)
    qa, qb = invariants(a), invariants(b)
    for name in ("von_mises", "triaxiality", "lode_parameter", "lode_angle_parameter", "principal_2"):
        assert np.allclose(qa[name], qb[name], atol=1e-9), name
    hydro = invariants([[50.0, 50.0, 50.0, 0, 0, 0], [0, 0, 0, 0, 0, 0]])
    assert np.isnan(hydro["triaxiality"]).all() and np.isnan(hydro["lode_parameter"]).all()
    assert hydro["pressure"].tolist() == [-50.0, -0.0]


def test_masks_and_extrema() -> None:
    values = np.array([1.0, 5.0, np.nan, -2.0, 9.0])
    ids = np.array([11, 12, 13, 14, 15])
    alive = np.array([True, True, True, True, False])
    assert extrema(values, ids, masked(alive)) == {"count": 3, "min": {"value": -2.0, "id": 14},
                                                   "max": {"value": 5.0, "id": 12}}
    assert extrema(values, ids, masked(alive, "deleted"))["max"]["id"] == 15
    assert extrema(values, ids, masked(alive, "all"))["count"] == 4
    with pytest.raises(ValueError):
        masked(alive, "living")
