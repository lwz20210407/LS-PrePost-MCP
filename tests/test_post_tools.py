import csv
import math

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.post_backend import result_ids
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.stress import NULLABLE, stress_metrics


@pytest.mark.parametrize("tensor,mises,eta,angle,mu", [
    ([100, 0, 0, 0, 0, 0], 100, 1/3, 1, -1),
    ([-100, 0, 0, 0, 0, 0], 100, -1/3, -1, 1),
    ([0, 0, 0, 50, 0, 0], math.sqrt(3)*50, 0, 0, 0),
    ([100, 100, 0, 0, 0, 0], 100, 2/3, -1, 1),
])
def test_stress_analytical_states(tensor, mises, eta, angle, mu):
    r = stress_metrics(tensor)
    assert r["von_mises"] == pytest.approx(mises)
    assert r["triaxiality"] == pytest.approx(eta)
    assert r["lode_angle_parameter"] == pytest.approx(angle, abs=2e-8)
    assert r["lode_parameter"] == pytest.approx(mu)


def test_hydrostatic_undefined_and_rotation_invariance():
    for pressure in (0, 12, -12):
        r = stress_metrics([pressure]*3 + [0]*3)
        assert all(r[k] is None for k in NULLABLE)
        assert r["von_mises"] == 0
    q, _ = np.linalg.qr(np.random.default_rng(42).normal(size=(3, 3)))
    tensor = np.array([[8, 2, 3], [2, -4, 1], [3, 1, 10]])
    rotated = q @ tensor @ q.T
    def six(t):
        return [t[0, 0], t[1, 1], t[2, 2], t[0, 1], t[1, 2], t[0, 2]]
    a, b = stress_metrics(six(tensor)), stress_metrics(six(rotated))
    for key in ("von_mises", "triaxiality", "j2", "j3", "lode_parameter", "lode_angle_parameter"):
        assert a[key] == pytest.approx(b[key])
    with pytest.raises(ValueError):
        stress_metrics([float("nan")]*6)


def test_rigid_shell_mapping_is_not_positional():
    arrays = {"element_shell_ids": np.array([10, 20, 30]),
              "element_shell_part_indexes": np.array([0, 1, 0]), "part_material_type": np.array([1, 20])}
    assert result_ids(arrays, "shell", 2).tolist() == [10, 30]
    with pytest.raises(ValueError):
        result_ids(arrays, "shell", 1)


def test_nonuniform_curve_derivative_integral_and_repeated_times(tmp_path):
    p = tmp_path / "curve.csv"
    p.write_text("t,v\n0,0\n1,1\n3,9\n")
    s = Service(Settings(tmp_path))
    result = s.process_curve(str(p), "differentiate", "mm")
    assert result["status"] == "succeeded", result
    with open(result["artifacts"][0]["path"], newline="") as f:
        rows = list(csv.DictReader(f))
    assert [float(r["value"]) for r in rows] == pytest.approx([0, 2, 6])
    assert result["data"]["summary"]["integral"] == pytest.approx(10.5)
    p.write_text("t,v\n0,1\n0,2\n")
    assert s.process_curve(str(p), "integrate", "mm")["status"] == "failed"


def test_ascii_d_exponents_and_malformed_row(tmp_path):
    p = tmp_path / "curve.txt"
    p.write_text("$ comment\n0 1D+2\n1 2d+2\n")
    s = Service(Settings(tmp_path))
    assert s.extract_ascii_curve(str(p), 1, 2, "mm")["status"] == "succeeded"
    p.write_text("0 1\nMALFORMED\n1 2\n")
    assert s.extract_ascii_curve(str(p), 1, 2, "mm")["status"] == "failed"


def test_native_staging_and_missing_id_fail_closed(tmp_path, monkeypatch):
    from ls_prepost_mcp.native_results import native_fields
    p = tmp_path / "input" / "d3plot"
    p.parent.mkdir()
    p.write_bytes(b"geometry")
    p.with_name("d3plot01").write_bytes(b"state")
    exe = tmp_path / "fake.exe"
    exe.touch()
    s = Service(Settings(tmp_path / "work", exe, allowed_roots=(p.parent,)))
    def fake(exe, command, directory, **kwargs):
        assert (directory / "d3plot").read_bytes() == b"geometry"
        assert str(p) not in command.read_text()
        (directory / "native.csv").write_text("state,time,entity_id,stress_x\n1,0,42,2\n")
        return {"returncode": 0, "timed_out": False}
    monkeypatch.setattr("ls_prepost_mcp.native_results.execute", fake)
    r = native_fields(s.settings, s.jobs, p, "solid", [42, 43], [1], ["stress_x"], "mid", "MPa")
    assert r["status"] == "failed"
    assert p.read_bytes() == b"geometry"
