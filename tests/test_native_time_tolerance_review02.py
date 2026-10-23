"""Time alignment must not depend on an implicit seconds-sized absolute floor."""
import hashlib

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.history_tools import _native
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.tensor_field import _native_agreement


def context(tmp_path, monkeypatch):
    source, output = tmp_path / "d3plot", tmp_path / "native.csv"
    source.write_bytes(b"owned stub")
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    def reply(*args, **kwargs):
        return {"status": "succeeded", "job_id": "native", "artifacts": [{"kind": "csv", "path": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}]}
    monkeypatch.setattr(service, "extract_native_fields", reply)
    monkeypatch.setattr(service, "extract_native_binout_curve", reply)
    return source, output, service


@pytest.mark.parametrize("reader,native", [(1e-12, 2e-12), (0., 1e-12)])
def test_tensor_wrong_small_time_is_not_hidden_by_an_absolute_floor(tmp_path, monkeypatch, reader, native):
    source, output, service = context(tmp_path, monkeypatch)
    output.write_text(f"state,time,entity_id,stress_x,stress_y,stress_z,stress_xy,stress_yz,stress_zx\n1,{native},1,0,0,0,0,0,0\n")
    raw = dict(sampling=dict(kind="stored_point", count=1), ids=[1], family="solid", state=1,
               time=reader, units="declared", values=np.zeros((1, 6)))
    with pytest.raises(ValueError, match="state/time"):
        _native_agreement(service, source, raw, "mid")


@pytest.mark.parametrize("kind", ["d3plot", "binout"])
@pytest.mark.parametrize("times,wrong", [([0., 1e-12, 2e-12], [0., 2e-12, 3e-12]),
                                        ([0., .1, .2], [1e-12, .1, .2])])
def test_history_wrong_times_are_not_hidden_by_an_absolute_floor(tmp_path, monkeypatch, kind, times, wrong):
    source, output, service = context(tmp_path, monkeypatch)
    if kind == "d3plot":
        output.write_text("entity_id,state,time,disp_z\n" + "".join(f"1,{i+1},{t},{i}\n" for i, t in enumerate(wrong)))
    else:
        output.write_text("time,value\n" + "".join(f"{t},{i}\n" for i, t in enumerate(wrong)))
    record = dict(entity=1 if kind == "d3plot" else None, time=np.array(times), values=np.array([0., 1., 2.]))
    with pytest.raises(ValueError, match="disagreement"):
        _native(service, source, [source], kind, "node" if kind == "d3plot" else "global",
                "displacement_z" if kind == "d3plot" else "kinetic_energy", [record], "declared")


def test_equal_small_tensor_times_are_still_comparable(tmp_path, monkeypatch):
    source, output, service = context(tmp_path, monkeypatch)
    output.write_text("state,time,entity_id,stress_x,stress_y,stress_z,stress_xy,stress_yz,stress_zx\n1,1e-12,1,0,0,0,0,0,0\n")
    raw = dict(sampling=dict(kind="stored_point", count=1), ids=[1], family="solid", state=1,
               time=1e-12, units="declared", values=np.zeros((1, 6)))
    assert _native_agreement(service, source, raw, "mid")["entities"] == 1
