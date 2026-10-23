"""Q05 stored-axis counterexamples independent of the new Service wrapper."""

import numpy as np
import pytest

from ls_prepost_mcp.domain.results import lasso_backend as lb
from tests.test_history_tools import history_model as history_model


@pytest.mark.parametrize("fault", ["duplicate", "fractional", "global_vector"])
def test_shared_history_never_guesses_invalid_axes(history_model, monkeypatch, fault):
    arrays = lb._arrays(history_model)
    if fault == "global_vector":
        arrays["global_kinetic_energy"] = np.ones((3, 2))
        args = ("global", "kinetic_energy", None)
    else:
        ids = arrays["node_ids"].copy()
        if fault == "duplicate":
            ids[1] = ids[0]
        else:
            ids = ids.astype(float) + 0.5
        arrays["node_ids"] = ids
        args = ("node", "displacement_z", [1])
    monkeypatch.setattr(lb, "_arrays", lambda *a, **k: arrays)
    with pytest.raises(lb.ResultsError):
        lb.history(history_model, *args)


def test_single_column_global_history_is_explicitly_scalar(history_model, monkeypatch):
    arrays = lb._arrays(history_model)
    arrays["global_kinetic_energy"] = np.array([[0.0], [10.0], [20.0]])
    monkeypatch.setattr(lb, "_arrays", lambda *a, **k: arrays)
    assert lb.history(history_model, "global", "kinetic_energy")[0]["values"] == [0.0, 10.0, 20.0]
