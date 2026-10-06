from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.workflow_runtime import operation_route


def service_and_source(tmp_path):
    exe = tmp_path / "native.exe"
    exe.write_bytes(b"identity only")
    source = tmp_path / "binout"
    source.write_bytes(b"not a database: mocked execution")
    return Service(Settings(tmp_path, exe)), source


@pytest.mark.parametrize(
    "quantity,suffix",
    [
        ("internal_energy", "INTERNAL_ENERGY"),
        ("kinetic_energy", "KINETIC_ENERGY"),
        ("eroded_internal_energy", "ERODED_INTERNAL_ENERGY"),
        ("eroded_kinetic_energy", "ERODED_KINETIC_ENERGY"),
        ("mass", "MASS"),
        ("hourglass_energy", "HOURGLASS_ENERGY"),
        ("momentum_x", "MOMENTUM_X"),
        ("momentum_y", "MOMENTUM_Y"),
        ("momentum_z", "MOMENTUM_Z"),
        ("rigid_body_velocity_x", "RBVELOCITY_X"),
        ("rigid_body_velocity_y", "RBVELOCITY_Y"),
        ("rigid_body_velocity_z", "RBVELOCITY_Z"),
    ],
)
def test_matsum_has_explicit_enum_id_lookup_and_valid_time_contract(tmp_path, monkeypatch, quantity, suffix):
    s, source = service_and_source(tmp_path)

    def execute(executable, cfile, directory, **kw):
        text = (directory / "binout.scl").read_text()
        assert "BINOUT_MATSUM_IDS" in text and "BINOUT_MATSUM_NUM_ID" in text
        assert "BINOUT_MATSUM_" + suffix + "," in text and "p.id=1500;" in text
        assert "if(found==0){SCLBinoutClose(h);return;}" in text
        (directory / "native.csv").write_text("time,value\n0,0\n1,2\n")
        return JobResult(operation=kw["operation"], job_id=directory.name, status="unverified", data=dict(returncode=0, timed_out=False))

    monkeypatch.setattr("ls_prepost_mcp.native_results.run_batch", execute)
    r = s.extract_native_binout_curve(str(source), "matsum", quantity, "raw units", entity_id=1500)
    assert r["status"] == "succeeded" and r["data"]["entity_id"] == 1500 and r["data"]["row_count"] == 2
    assert not r["data"]["units_inferred"]


@pytest.mark.parametrize(
    "data",
    [
        None,
        "time,value\n",
        "time,value\n0,1\n",
        "time,value\n0,1\n0,2\n",
        "time,value\n0,1\n1,nan\n",
        "time,value\n1,1\n0,2\n",
    ],
)
def test_missing_or_invalid_native_curve_does_not_succeed(tmp_path, monkeypatch, data):
    s, source = service_and_source(tmp_path)

    def execute(executable, cfile, directory, **kw):
        if data is not None:
            (directory / "native.csv").write_text(data)
        return JobResult(operation=kw["operation"], job_id=directory.name, status="unverified", data=dict(returncode=0, timed_out=False))

    monkeypatch.setattr("ls_prepost_mcp.native_results.run_batch", execute)
    r = s.extract_native_binout_curve(str(source), "matsum", "internal_energy", "raw", entity_id=1500)
    assert r["status"] == "failed"


def test_matsum_requires_stored_id_and_does_not_invent_total_energy(tmp_path):
    s, source = service_and_source(tmp_path)
    with pytest.raises(ValueError):
        s.extract_native_binout_curve(str(source), "matsum", "internal_energy", "raw")
    with pytest.raises(ValueError, match="Supported"):
        s.extract_native_binout_curve(str(source), "matsum", "total_energy", "raw", entity_id=1)


def test_gui_workflow_binout_route_retains_source_and_injects_owned_session(tmp_path):
    s, _ = service_and_source(tmp_path)
    assert operation_route(s, "extract_native_binout_curve", "owned").kind == "session"
    assert operation_route(s, "extract_native_binout_curve", None).kind == "service"


def test_visible_executor_avoids_batch_launch(tmp_path, monkeypatch):
    import ls_prepost_mcp.native_results as module

    s, source = service_and_source(tmp_path)
    monkeypatch.setattr(
        module, "run_batch", lambda *a, **k: pytest.fail("GUI route must not launch batch process")
    )

    def executor(directory, manifest):
        assert (directory / "input_data").read_bytes() == source.read_bytes()
        assert (directory / "binout.scl").is_file()
        (directory / "native.csv").write_text("time,value\n0,0\n1,2\n")
        manifest["execution_mode"] = "visible_gui_scl_binout"

    r = module.native_binout(s.settings, s.jobs, source, "matsum", "mass", 1, "raw", executor=executor)
    assert r["status"] == "succeeded" and r["data"]["requires_python"]
    assert Path(r["artifacts"][0]["path"]).is_file()
