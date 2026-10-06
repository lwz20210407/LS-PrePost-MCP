"""A02 native cfile build/save/reopen and source-line diagnostics."""

import json
from pathlib import Path

import pytest

from ls_prepost_mcp.sessions import Sessions
from tests.test_engine_native import native_case  # noqa: F401
from tests.test_script_command_native import node_coordinates

pytestmark = pytest.mark.native


@pytest.mark.parametrize("context", ["batch", "session"])
def test_cfile_build_save_reopen_and_failed_line(native_case, context):  # noqa: F811
    service, _ = native_case
    sid = Sessions(service.settings).start(transport="queue")["session_id"] if context == "session" else None
    code = ('meshing boxsolid create 0 0 0 {{width}} 3 4 1 1 1 0\n'
            'meshing boxsolid accept 1 1 1 boxsolid\n'
            'save keyword "{{filename}}"\n'
            'open keyword "{{filename}}"\n')
    try:
        result = service.run_script("cfile", code, context=context, session_id=sid,
                                    parameters=dict(width=5, filename="box output.k"),
                                    outputs=[dict(name="box output.k", kind="keyword")],
                                    expected_counts=dict(nodes=8, elements=1))
        (service.settings.workspace / "cfile-result.json").write_text(json.dumps(result, indent=2), encoding="utf8")
        assert result["status"] == "succeeded", result
        output = Path(result["artifacts"][0]["path"])
        nodes = node_coordinates(output)
        assert len(nodes) == 8 and max(x[0] for x in nodes.values()) == 5
        assert result["data"]["counts"]["nodes"] == 8
        assert not result["data"]["diagnostics"]
        if sid:
            inspected = service.gui_session_action(sid, "inspect_model", {})
            assert inspected["status"] == "succeeded", inspected
        invalid = service.run_script("cfile", 'top\ninvalid_a02_command\nisometric x\n',
                                     context=context, session_id=sid)
        assert invalid["status"] == "failed", invalid
        assert invalid["data"]["diagnostics"][0]["line"] == 2, invalid
        assert "invalid_a02_command" in invalid["data"]["diagnostics"][0]["message"]
    finally:
        if sid:
            service.close_gui_session(sid, save_checkpoint=False)
