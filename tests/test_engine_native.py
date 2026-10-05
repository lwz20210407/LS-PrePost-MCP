"""I01 native regression on the M0 synthetic 8-node, 3-state shell fixture."""

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.native import commands as nc
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


def test_command_builders_native_id_buffer_state_and_fringe(native_case):
    service, source = native_case
    commands = [nc.animation("stop"), nc.animation("first", 1), nc.animation("last", 3),
                nc.animation("incr", 1), nc.state(3), nc.fringe(9), nc.plot_fringe(),
                nc.averaging("minmax"), nc.selection("clear"), nc.selection_target("node"),
                nc.selection_add("node", 11), nc.selection_add("node", 79),
                nc.selection_buffer("save", 0), nc.selection("clear"), nc.selection_buffer("load", 0)]
    code = (
        "import json,DataCenter as dc,LsPrePost as lp\n"
        "trace=[]\n"
        "for command in " + repr(commands) + ":\n"
        "    lp.execute_command(command)\n"
        "    n=int(dc.get_data('num_selection'))\n"
        "    selected=sorted(int(v) for v in dc.get_data('selection_ids',type=0)) if n else []\n"
        "    trace.append({'command':command,'count':n,'ids':selected})\n"
        "json.dump(trace,open('command-trace.json','w'))\n"
        "count=int(dc.get_data('num_selection'))\n"
        "ids=sorted(int(v) for v in dc.get_data('selection_ids',type=0)) if count else []\n"
        "assert count==2 and ids==[11,79], repr(ids)\n"
        "current=int(dc.get_data('current_state'))\n"
        "assert current==3, repr(current)\n"
        "json.dump({'selection_ids':ids,'count':count,'state':current},open('selection-proof.json','w'))\n"
        "lp.execute_command('print png \"commands.png\" opaque enlisted \"OGL1x1\"')\n"
    )
    prepared = service.prepare_native_program("python", code=code,
        outputs=[dict(name="selection-proof.json", kind="json"), dict(name="commands.png", kind="png")],
        expected_counts=dict(nodes=8, states=3))
    result = service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"],
                                            model=str(source / "d3plot"), file_type="d3plot")
    assert result["status"] == "succeeded", result
    proof = json.loads((Path(result["job_directory"]) / "selection-proof.json").read_text())
    assert proof == dict(selection_ids=[11, 79], count=2, state=3)
    assert all(a["validated"] for a in result["artifacts"])


class NativeWorkingDirectoryError(AssertionError):
    pass


@pytest.mark.parametrize("workspace_name", ["ascii-workspace",
    pytest.param("space folder", marks=pytest.mark.xfail(strict=True, raises=NativeWorkingDirectoryError, reason="KI-049 native working-directory preference truncates spaces")),
    pytest.param("中文 空格", marks=pytest.mark.xfail(strict=True, raises=NativeWorkingDirectoryError, reason="KI-049 native working-directory preference cannot resolve this Unicode/spaced root"))])
def test_path_builders_batch_unicode_and_spaces_save_png_reopen(native_case, workspace_name):
    service, source = native_case
    service = Service(replace(service.settings, workspace=service.settings.workspace / workspace_name))
    service.settings.workspace.mkdir(parents=True)
    local_source = service.settings.workspace / "模型 空格.k"
    local_source.write_bytes((source / "input.k").read_bytes())
    code = "\n".join(["top", nc.print_png("image.png"), nc.save_keyword("saved.k")])
    prepared = service.prepare_native_program("cfile", code=code,
        outputs=[dict(name="image.png",kind="png"),dict(name="saved.k",kind="keyword")],
        expected_counts=dict(nodes=8,elements=3))
    result = service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"], model=str(local_source))
    if workspace_name != "ascii-workspace" and result["status"] == "failed":
        stderr = Path(result["job_directory"]) / "stderr.log"
        if stderr.is_file() and "cannot open or does not exist" in stderr.read_text(encoding="utf8", errors="replace"):
            raise NativeWorkingDirectoryError("KI-049: native working directory failed to resolve staged input_data")
    assert result["status"] == "succeeded", result
    saved = next(row["path"] for row in result["artifacts"] if row["kind"] == "keyword")
    reopened = service.inspect_model(saved)
    assert reopened["status"] == "succeeded" and reopened["data"]["counts"]["nodes"] == 8, reopened


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
