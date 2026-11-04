"""I01 GUI-window-only responsiveness probe; it never claims Apply has stopped."""
import json
import os

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.windows_transport import WindowsCommandTransport
from tests.test_save_model import deck
from tests.test_save_model_native import installation as installation

pytestmark = [pytest.mark.native, pytest.mark.gui]


def test_owned_gui_readonly_recovery_probe(installation, pytestconfig):
    if not pytestconfig.getoption("--native-gui") or os.environ.get("LSPP_ALLOW_GUI") != "1":
        pytest.skip("Requires a new authorized unlocked GUI window; --native-gui and LSPP_ALLOW_GUI=1")
    executable, binary, config_sha = installation
    root = pytestconfig._native_root / "readonly-recovery-probe"
    root.mkdir()
    service = Service(Settings(root / "work", executable, (root,), timeout=90))
    model = deck(root / "source")
    started = service.start_gui_session()
    sid = started["session_id"]
    try:
        opened = service.open_in_gui_session(sid, str(model))
        assert opened["status"] == "succeeded", opened
        transport = WindowsCommandTransport(started["process"]["pid"])
        probe = transport.probe_idle()
        assert probe["responsive"] and probe["enabled"] and probe["pid"] == started["process"]["pid"]
        manager = service._session_manager()

        def host_failure(_transport, _directory):
            raise RuntimeError("Owned diagnostic host callback stopped before dispatch; no Apply sent")

        with pytest.raises(RuntimeError, match="Owned diagnostic"):
            manager.dispatch(sid, "gui_mesh_state", {}, _before_submit=host_failure)
        request_id = manager.read(sid)["active_request"]
        request_dir = manager.directory(sid) / "requests" / request_id
        assert not (request_dir / "complete.json").exists()
        recovered = service.recover_gui_session(sid)
        assert recovered["active_request"] is None and recovered["state"] == "uncertain"
        assert recovered["requires_host_validation"] and recovered["dispatch_submitted"] is False
        assert recovered["recovery_probe"]["responsive"]
        context = pytestconfig._native_identity
        (root / "verified.json").write_text(json.dumps(dict(actual_git_revision=context["actual_git_head"],
            working_tree_dirty=context["working_tree_dirty"], git_diff_sha256=context["git_diff_sha256"],
            executable=binary, source_config_sha256=config_sha, probe=probe,
            recovery_probe=recovered["recovery_probe"], model_state=recovered["state"],
            scope="Responsive idle owned GUI only; real busy Apply/background mutation not certified"),separators=(",", ":"))+"\n",encoding="utf8")
    finally:
        assert service.close_gui_session(sid, save_checkpoint=False)["state"] == "closed"
