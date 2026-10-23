"""Review02 P2: consistent counts/frame and scale-based tensor comparison."""
import hashlib

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.results import invariants as inv
from ls_prepost_mcp.domain.results import lasso_backend as lb
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.tensor_field import _native_agreement


def case(tmp_path, monkeypatch):
    source = tmp_path / "d3plot"
    source.write_bytes(b"owned field source")
    stress = np.zeros((1, 2, 1, 6))
    stress[:, :, :, 0] = 2.
    arrays = {"timesteps": np.array([0.]), "element_solid_ids": np.array([1, 2]),
              "element_solid_stress": stress, "element_solid_is_alive": np.array([[1., 0.]])}
    monkeypatch.setattr(lb, "_arrays", lambda *a, **kw: arrays)
    monkeypatch.setattr(lb, "state_times", lambda *a: arrays["timesteps"])
    monkeypatch.setattr(lb, "header", lambda *a: {"deletion_data_stored": True})
    return Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,))), source


@pytest.mark.parametrize("quantity", ["stress", "sxx"])
def test_alive_total_is_reported_before_the_mask_and_finite_counts_match_rows(tmp_path, monkeypatch, quantity):
    service, source = case(tmp_path, monkeypatch)
    result = service.extract_field(str(source), "solid", quantity, mask="deleted", units="declared")
    assert result["status"] == "succeeded", result.get("error")
    assert result["data"].get("alive_total_count") == 1
    assert result["data"]["active_count"] == 0 and result["data"]["row_count"] == 1
    assert result["data"].get("finite_count") == 1


@pytest.mark.parametrize("quantity", ["stress", "sxx"])
def test_coordinate_label_is_as_stored_without_an_inferred_global_frame(tmp_path, monkeypatch, quantity):
    service, source = case(tmp_path, monkeypatch)
    result = service.extract_field(str(source), "solid", quantity, mask="all", units="declared")
    assert result["status"] == "succeeded", result.get("error")
    assert result["artifacts"][0]["metadata"]["coordinate_system"] == "as stored"
    assert "global" not in inv.definition("sxx").lower()


@pytest.mark.parametrize("reference,wrong", [([1e-9, 2e-9, 0., 0., 0., 0.], [2e-9, 1e-9, 0., 0., 0., 0.]),
                                           ([0.] * 6, [0., 0., 0., 1e-12, 0., 0.])])
def test_small_or_zero_tensor_disagreement_cannot_hide_under_fixed_absolute_tolerance(tmp_path, monkeypatch, reference, wrong):
    source = tmp_path / "d3plot"
    source.write_bytes(b"owned source")
    output = tmp_path / "native.csv"
    fields = ["stress_x", "stress_y", "stress_z", "stress_xy", "stress_yz", "stress_zx"]
    output.write_text("state,time,entity_id," + ",".join(fields) + "\n1,0,1," + ",".join(map(str, wrong)) + "\n")
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    monkeypatch.setattr(service, "extract_native_fields", lambda *a, **kw: {"status": "succeeded", "job_id": "native",
        "artifacts": [{"kind": "csv", "path": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}]})
    raw = {"sampling": {"kind": "stored_point", "count": 1, "index": 1}, "ids": [1], "family": "solid",
           "state": 1, "time": 0., "units": "Pa", "values": np.array([reference])}
    with pytest.raises(ValueError, match="disagreement"):
        _native_agreement(service, source, raw, "mid")
