"""Q03 field export: CSV / NPZ round trip with metadata, refusals."""
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.domain.results.export import export_field, read_field
from ls_prepost_mcp.domain.results.lasso_backend import ResultsError

RESULT = {"backend": "lasso-python 2.0.4", "family": "solid", "quantity": "triaxiality", "state": 3, "time": 1.5e-4,
          "ids": np.array([10, 11, 12]), "values": np.array([0.333333333, -0.25, 1.0e-12]),
          "alive": np.array([True, False, True]), "mask": "alive", "note": "mean of 8 stored points",
          "extrema": {"max": {"id": 10, "value": 0.333333333}}}


@pytest.mark.parametrize("suffix", ["csv", "npz"])
def test_round_trip_keeps_values_and_metadata(tmp_path: Path, suffix: str) -> None:
    written = export_field(RESULT, tmp_path / f"field.{suffix}", units="mm-t-s (stress MPa)")
    assert written["rows"] == 3 and written["format"] == suffix and len(written["sha256"]) == 64
    back = read_field(written["path"])
    assert back["ids"].tolist() == [10, 11, 12] and back["alive"].tolist() == [True, False, True]
    assert np.allclose(back["values"], RESULT["values"], rtol=1e-9, atol=0)
    meta = back["meta"]
    assert meta["quantity"] == "triaxiality" and meta["state"] == 3 and meta["time"] == 1.5e-4
    assert meta["points"] == "mean of 8 stored points" and meta["mask"] == "alive"
    assert meta["units"] == "mm-t-s (stress MPa)" and meta["coordinate_system"].startswith("global")


def test_undeclared_units_are_labelled_not_converted(tmp_path: Path) -> None:
    meta = read_field(export_field(RESULT, tmp_path / "f.csv")["path"])["meta"]
    assert "not converted" in meta["units"]


def test_refusals(tmp_path: Path) -> None:
    with pytest.raises(ResultsError, match="Format"):
        export_field(RESULT, tmp_path / "f.txt")
    export_field(RESULT, tmp_path / "f.csv")
    with pytest.raises(ResultsError, match="exists"):
        export_field(RESULT, tmp_path / "f.csv")
    with pytest.raises(ResultsError, match="differ in length"):
        export_field({**RESULT, "alive": np.array([True])}, tmp_path / "g.npz")
