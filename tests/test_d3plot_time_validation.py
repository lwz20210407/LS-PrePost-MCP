"""I04: reject malformed reader state metadata before selection or engineering math."""
from types import SimpleNamespace

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.results import lasso_backend as lb
from ls_prepost_mcp.service import Service


@pytest.fixture
def reader(tmp_path, monkeypatch):
    lasso = pytest.importorskip("lasso.dyna")
    source = tmp_path / "d3plot"
    source.write_bytes(b"test stub; never parsed")
    arrays = {
        "timesteps": np.array([0., 1., 2.]), "node_ids": np.array([1]),
        "node_coordinates": np.zeros((1, 3)), "node_displacement": np.zeros((3, 1, 3)),
        "element_solid_ids": np.array([10]), "element_solid_stress": np.zeros((3, 1, 6)),
    }
    calls = []

    def load(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(arrays=arrays, header=SimpleNamespace(n_nodes=1, n_shells=0, n_solids=1))

    monkeypatch.setattr(lasso, "D3plot", load)
    monkeypatch.setattr(lb, "_lasso", lambda: (None, None, load))
    return source, arrays, calls


@pytest.mark.parametrize("times", [
    [0., -999999., 1.], [-999999., 1., 2.], [0., 2., 1.],
    [0., np.nan, 2.], [0., np.inf, 2.], [[0., 1., 2.]],
])
@pytest.mark.parametrize("route", ["overview", "history", "field", "inventory", "selected", "nodal"])
def test_invalid_time_axis_never_returns_engineering_results(reader, tmp_path, times, route):
    from ls_prepost_mcp.post_backend import selected_database

    source, arrays, calls = reader
    arrays["timesteps"] = np.array(times)
    before = arrays["timesteps"].copy()
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    if route == "nodal":
        result = service.extract_d3plot_nodal(str(source), node_ids=[1], quantity="displacement",
                                              states=[1], units="mm-ms")
        assert result["status"] == "failed"
        assert "Invalid d3plot time axis" in result["error"]["message"]
        assert not list((tmp_path / "work").rglob("nodal.csv"))
    else:
        actions = {
            "overview": lambda: lb.overview(source),
            "history": lambda: lb.history(source, "node", "displacement_x", [1]),
            "field": lambda: lb.field(source, "solid", "sxx", 0),
            "inventory": lambda: service.inspect_d3plot_database(str(source)),
            # Even state 1 must fail when later metadata reveals a corrupt family.
            "selected": lambda: selected_database(source, [1], ["node_displacement"]),
        }
        with pytest.raises(ValueError, match="Invalid d3plot time axis"):
            actions[route]()
    assert len(calls) == 1
    np.testing.assert_array_equal(arrays["timesteps"], before)


@pytest.mark.parametrize("times", [[-2., -1., 0.], [0., 0., 1.], []])
def test_valid_negative_duplicate_and_empty_times_are_preserved(reader, times):
    source, arrays, _ = reader
    arrays["timesteps"] = np.array(times)
    assert lb.overview(source)["times"] == times


def test_global_timesteps_alias_is_also_validated(reader):
    source, arrays, _ = reader
    arrays["global_timesteps"] = arrays.pop("timesteps")
    arrays["global_timesteps"][1] = -999999.
    with pytest.raises(ValueError, match="Invalid d3plot time axis"):
        lb.overview(source)
