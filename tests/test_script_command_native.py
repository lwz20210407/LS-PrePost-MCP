"""A01: real command execution, native echo and independent artifact checks."""

import json
from pathlib import Path

import pytest

from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.native import commands as nc
from ls_prepost_mcp.sessions import Sessions
from tests.test_engine_native import native_case  # noqa: F401

pytestmark = pytest.mark.native


def node_coordinates(path):
    """Independent fixed-width reader of this synthetic fixture's native save."""
    nodes, in_nodes = {}, False
    for line in Path(path).read_text().splitlines():
        if line.startswith("*"):
            in_nodes = line.strip().upper() == "*NODE"
        elif in_nodes and line.strip() and not line.startswith("$"):
            nodes[int(line[:8])] = tuple(float(line[start:start + 16]) for start in (8, 24, 40))
    return nodes


@pytest.mark.parametrize("context", ["batch", "session"])
def test_command_channel_native_matrix(native_case, context):  # noqa: F811 - shared pytest fixture
    service, source = native_case
    sid = None
    if context == "session":
        sid = Sessions(service.settings).start(transport="queue")["session_id"]
    trace = []
    commands = [
        (f'open keyword "{(source / "input.k").as_posix()}"', {}),
        (nc.selection_add("node", 11), dict(initial_node_ids=[11])),
        ("translate_model 2 3 4", dict(initial_node_ids=[11], capture_model=True)),
        ("translate_model accept", dict(capture_model=True)),
        ("-m 7", {}),
        ("pall", {}),
        ("top", {}),
        ("isometric x", {}),
        ('print png "command.png" opaque enlisted "OGL1x1"',
         dict(outputs=[dict(name="command.png", kind="png")])),
        ('save keyword "command.k"', dict(outputs=[dict(name="command.k", kind="keyword")])),
    ]
    try:
        for index, (command, options) in enumerate(commands):
            args = dict(context=context, expected_counts=dict(nodes=8, elements=3), **options)
            if sid:
                args["session_id"] = sid
            elif index:
                args["model"] = str(source / "input.k")
            result = service.run_script("command", command, **args)
            trace.append(result)
            (service.settings.workspace / "command-matrix.json").write_text(json.dumps(trace, indent=2), encoding="utf8")
            parsed = JobResult.model_validate(result)
            assert parsed.status == "succeeded", result
            echo = parsed.data["native_echo"]
            assert not echo["errors"] and Path(echo["full_text_path"]).is_file(), result
            assert parsed.data["counts"]["nodes"] == 8
            if index == 1:
                assert parsed.data["selection"] == dict(count=1, user_ids=[11]), result
            if index in (4, 5):
                assert parsed.data["part_visibility"] == {"7": index == 5, "42": True}, result
            if index in (2, 3):
                snapshot = next(a for a in parsed.artifacts if a.kind == "keyword")
                coordinates = node_coordinates(snapshot.path)
                expected = (2, 3, 4) if index == 2 or context == "session" else (0, 0, 0)
                assert coordinates[11] == expected
                assert coordinates[13] == (1, 0, 0)
            if index == 8:
                from PIL import Image
                output = next(a for a in parsed.artifacts if a.path.endswith("command.png"))
                with Image.open(output.path) as image:
                    assert image.width > 0 and image.height > 0
                    assert any(low != high for low, high in image.convert("RGB").getextrema())
            if index == 9:
                output = next(a for a in parsed.artifacts if a.path.endswith("command.k"))
                reopened = service.inspect_model(output.path)
                assert reopened["status"] == "succeeded", reopened
                assert reopened["data"]["counts"]["nodes"] == 8
        bad_args = dict(context=context, session_id=sid) if sid else dict(model=str(source / "input.k"))
        bad = service.run_script("command", "invalid_a01_command", **bad_args)
        assert bad["status"] == "failed", bad
        assert any("invalid_a01_command" in line for line in bad["data"]["native_echo"]["errors"]), bad
    finally:
        if sid:
            service.close_gui_session(sid, save_checkpoint=False)
