"""The Q06 native adapter was added after 0563045; regress on its current main."""
import hashlib

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.database_native import compare_ascii_forces
from ls_prepost_mcp.service import Service


@pytest.mark.parametrize("times,wrong_times,values,wrong_values", [
    ([0., 1e-12, 2e-12], [0., 2e-12, 3e-12], [0., 1., 2.], [0., 1., 2.]),
    ([0., .1, .2], [1e-12, .1, .2], [0., 1., 2.], [0., 1., 2.]),
    ([0., 1., 2.], [0., 1., 2.], [0., 1e-9, 2e-9], [0., 2e-9, 1e-9]),
    ([0., 1., 2.], [0., 1., 2.], [0., 0., 0.], [0., 1e-12, 0.]),
], ids=["tiny-time", "zero-origin", "tiny-force", "zero-force"])
def test_force_native_check_has_no_time_or_value_unit_floor(tmp_path, monkeypatch, times, wrong_times, values, wrong_values):
    source, reader, native = tmp_path / "secforc", tmp_path / "reader.csv", tmp_path / "native.csv"
    source.write_bytes(b"owned adapter input")
    reader.write_text("time,entity_id,x_force\n" + "".join(f"{t},9,{v}\n" for t, v in zip(times, values)))
    native.write_text("time,value\n" + "".join(f"{t},{v}\n" for t, v in zip(wrong_times, wrong_values)))
    def artifact(path):
        return dict(kind="csv", path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    monkeypatch.setattr(service, "extract_native_ascii_curve", lambda *a, **kw: dict(status="succeeded", job_id="native",
        data={"entity_id": 9}, artifacts=[artifact(native)]))
    result = dict(data=dict(database="secforc", component="x_force", units="declared"), artifacts=[artifact(reader)])
    with pytest.raises(ValueError, match="time axis differs|values disagree"):
        compare_ascii_forces(service, source, result)
