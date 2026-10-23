"""Review02 P2 #125: small-unit curves cannot pass under a fixed 1e-6 floor."""
import hashlib

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.history_tools import _native
from ls_prepost_mcp.service import Service


@pytest.mark.parametrize("values,wrong", [([0., 1e-9, 2e-9], [0., 2e-9, 1e-9]),
                                        ([0., 0., 0.], [0., 1e-12, 0.])])
def test_wrong_small_or_zero_history_is_not_accepted_by_a_unit_dependent_floor(tmp_path, monkeypatch, values, wrong):
    source = tmp_path / "d3plot"
    source.write_bytes(b"owned stub")
    csv = tmp_path / "native.csv"
    csv.write_text("entity_id,state,time,disp_z\n" + "".join(
        f"1,{n + 1},{n},{v}\n" for n, v in enumerate(wrong)))
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    monkeypatch.setattr(service, "extract_native_fields", lambda *a, **kw: {
        "status": "succeeded", "job_id": "native", "artifacts": [{"kind": "csv", "path": str(csv),
            "sha256": hashlib.sha256(csv.read_bytes()).hexdigest()}]})
    record = {"entity": 1, "time": np.array([0., 1., 2.]), "values": np.array(values)}
    with pytest.raises(ValueError, match="disagreement"):
        _native(service, source, [source], "d3plot", "node", "displacement_z", [record], "declared_units")


@pytest.mark.parametrize("domain,quantity,diagnostic", [("beam", "sxx", "beam.*unsupported"),
                                                      ("solid", "not_a_native_component", "does not support quantity")])
def test_unsupported_native_history_has_a_precise_error_not_a_keyerror(domain, quantity, diagnostic):
    record = {"entity": 1, "time": np.array([0., 1.]), "values": np.array([1., 2.])}
    with pytest.raises(ValueError, match=diagnostic):
        _native(None, None, [], "d3plot", domain, quantity, [record], "units")
