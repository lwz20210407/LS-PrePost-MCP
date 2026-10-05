"""I01 native regression on the M0 synthetic 8-node, 3-state shell fixture."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.sessions import Sessions

pytestmark = pytest.mark.native


@pytest.fixture
def native_case(tmp_path):
    executable = os.environ.get("LSPP_ENGINE_EXECUTABLE")
    fixture = os.environ.get("LSPP_ENGINE_FIXTURE")
    if not executable or not fixture:
        pytest.skip("Set LSPP_ENGINE_EXECUTABLE and LSPP_ENGINE_FIXTURE for I01 native regression")
    source = Path(fixture)
    assert all((source / name).is_file() for name in ("input.k", "d3plot", "d3plot01"))
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file()}
    service = Service(Settings(tmp_path, Path(executable), (source,), timeout=60))
    yield service, source
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file()}


@pytest.mark.parametrize("caller", ["service", "scl_backend", "native_results", "native_batch", "programs"])
def test_five_batch_callers_use_isolated_engine(native_case, caller):
    service, source = native_case
    if caller == "service":
        result = service.inspect_model(str(source / "input.k"))
        assert result.get("data", {}).get("counts", {}).get("nodes") == 8, result
    elif caller == "scl_backend":
        result = service.inspect_d3plot_scl(str(source / "d3plot"))
    elif caller == "native_results":
        result = service.extract_native_fields(str(source / "d3plot"), "node", [11, 79], [1, 3],
                                               ["disp_x"], "mid", "mm-ms-N")
    elif caller == "native_batch":
        result = service.native_postprocess_case(str(source / "d3plot"), "mm-ms-N")
    else:
        prepared = service.prepare_native_program("command", code="top", expected_counts={"nodes": 8})
        result = service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"],
                                                model=str(source / "input.k"))
    assert result["status"] == "succeeded", result
    process = result["process"]
    assert process["engine_status"] == "unverified"  # Domain checks above provide the success verdict.
    assert process["configuration"]["source_modified"] is False
    assert "-nographics" in process["argv"]


def test_queue_session_reuses_pid_and_never_uses_win32(native_case, monkeypatch):
    service, source = native_case
    monkeypatch.setattr("ls_prepost_mcp.sessions.WindowsCommandTransport",
                        lambda *a, **kw: pytest.fail("Queue must not use Win32"))
    manager = Sessions(service.settings)
    meta = manager.start(transport="queue")
    sid, pid = meta["session_id"], meta["process"]["pid"]
    try:
        opened = service.open_in_gui_session(sid, str(source / "input.k"), discard=True)
        assert opened["status"] == "succeeded", opened
        for _ in range(3):
            result = service.gui_session_action(sid, "inspect_model", {})
            assert result["status"] == "succeeded" and result["data"]["counts"]["nodes"] == 8, result
            assert manager.read(sid)["process"]["pid"] == pid
            evidence = json.loads((Path(result["job_directory"]) / "engine-result.json").read_text())
            assert evidence["contract"] == "JobResult/v1" and evidence["status"] == "succeeded"
        saved = service.checkpoint_gui_session(sid)
        assert saved["status"] == "succeeded", saved
        reopened = service.restore_gui_checkpoint(sid)
        assert reopened["status"] == "succeeded", reopened
    finally:
        closed = service.close_gui_session(sid, save_checkpoint=False)
        assert closed["state"] == "closed", closed


def test_native_diagnostic_is_visible_to_program_caller(native_case):
    service,source=native_case
    prepared=service.prepare_native_program("command",code="invalid_i01_native_command")
    result=service.execute_native_program(prepared["job_id"],prepared["data"]["sha256"],model=str(source/"input.k"))
    assert result["status"]=="failed",result
    assert result["process"]["returncode"]==0
    assert "invalid_i01_native_command" in result["error"]["message"]


def test_public_win32_session_engine_round_trip(native_case):
    if os.environ.get("LSPP_ALLOW_GUI") != "1":
        pytest.skip("Requires an authorized, unlocked GUI window")
    service, source = native_case
    started = service.start_gui_session()
    sid, pid = started["session_id"], started["process"]["pid"]
    try:
        opened = service.open_in_gui_session(sid, str(source / "input.k"), discard=True)
        assert opened["status"] == "succeeded", opened
        result = service.gui_session_action(sid, "inspect_model", {})
        assert result["status"] == "succeeded" and result["data"]["counts"]["nodes"] == 8, result
        evidence = json.loads((Path(result["job_directory"]) / "engine-result.json").read_text())
        assert evidence["contract"] == "JobResult/v1" and evidence["status"] == "succeeded"
        assert service.checkpoint_gui_session(sid)["status"] == "succeeded"
        assert service.restore_gui_checkpoint(sid)["status"] == "succeeded"
        assert Sessions(service.settings).read(sid)["process"]["pid"] == pid
    finally:
        closed = service.close_gui_session(sid, save_checkpoint=False)
        assert closed["state"] == "closed", closed
