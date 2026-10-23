"""Q05 history must identify the same explicit stored point as Q03/Q04 fields."""
import csv

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import CurveSpec
from ls_prepost_mcp.domain.results import lasso_backend as lb
from ls_prepost_mcp.service import Service


def setup(tmp_path, monkeypatch):
    path = tmp_path / "d3plot"
    path.write_bytes(b"owned array source")
    stress = np.zeros((2, 1, 3, 6))
    stress[:, 0, :, 0] = [[-100., 0., 100.], [-200., 0., 200.]]
    arrays = dict(timesteps=np.array([0., 1.]), element_shell_ids=np.array([17]),
                  element_shell_stress=stress, element_shell_is_alive=np.array([[1.], [0.]]),
                  element_shell_effective_plastic_strain=np.array([[[.01, .02, .03]], [[.04, .05, .06]]]))
    monkeypatch.setattr(lb, "_arrays", lambda *a, **kw: arrays)
    return path, Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))


@pytest.mark.parametrize("quantity,expected", [("sxx", [-100., -200.]), ("von_mises", [100., 200.]),
                                               ("effective_plastic_strain", [.01, .04])])
def test_explicit_shell_history_point_reaches_shared_reader_and_contract(tmp_path, monkeypatch, quantity, expected):
    path, service = setup(tmp_path, monkeypatch)
    result = service.extract_history(str(path), "shell", quantity, [17], units="declared", time_units="s", stored_point=1)
    assert result["status"] == "succeeded", result.get("error")
    spec = CurveSpec.model_validate(service.jobs.get(result["job_id"])["parameters"]["curve_spec"], strict=False)
    assert spec.stored_point == 1
    curve = result["data"]["curves"][0]
    assert curve["sampling_spec"]["index"] == 1 and curve["sampling_spec"]["count"] == 3
    assert curve["sampling_spec"]["native_layer_equivalence"] == "not inferred"
    assert curve["deleted_from_state"] == 2
    with open(result["artifacts"][0]["path"], encoding="utf8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [float(r["value"]) for r in rows] == expected
    assert [r["alive"] for r in rows] == ["1", "0"]


@pytest.mark.parametrize("point", [0, True, 4])
def test_invalid_history_point_cannot_fall_back_to_a_mean(tmp_path, monkeypatch, point):
    path, service = setup(tmp_path, monkeypatch)
    if point in (0, True):
        with pytest.raises(ValueError, match="stored_point"):
            service.extract_history(str(path), "shell", "sxx", [17], units="Pa", time_units="s", stored_point=point)
    else:
        result = service.extract_history(str(path), "shell", "sxx", [17], units="Pa", time_units="s", stored_point=point)
        assert result["status"] == "failed" and "stored_point" in result["error"]["message"]
        assert not result["artifacts"]
