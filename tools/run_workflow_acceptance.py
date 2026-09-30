"""Opt-in synthetic GUI workflow acceptance; never scans user model directories."""

import argparse
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--keep-open", action="store_true")
    args = parser.parse_args()
    root = args.workspace.resolve() / ("synthetic-workflow-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    service = Service(Settings(root, args.executable.resolve(), timeout=60))
    results = []

    def check(name, call):
        result = call()
        results.append(dict(name=name, result=result))
        atomic_json(root / "acceptance.json", results)
        if result.get("status") in ("failed", "partial", "uncertain", "needs_review"):
            raise RuntimeError(name + " failed; inspect " + str(root / "acceptance.json"))
        print(name + ": " + result.get("status", result.get("state", "recorded")), flush=True)
        return result

    meta = check("start", service.start_gui_session)
    sid = meta["session_id"]
    service.show_gui_session(sid)
    check("record-start", lambda: service.start_session_recording(sid))
    check(
        "box",
        lambda: service.gui_session_action(
            sid, "create_solid_box", dict(divisions=[2, 2, 2], size=[2, 2, 2], units="mm")
        ),
    )
    check(
        "display", lambda: service.set_gui_display(sid, view="isometric", display_mode="shaded", center=True)
    )
    recording = check("record-stop", lambda: service.stop_session_recording(sid))
    recipe = check(
        "parameterize",
        lambda: service.parameterize_workflow(
            recording["workflow"], [dict(step_id="step1", path=["size", 0], parameter="width")]
        ),
    )
    check("reset", lambda: service.reset_gui_session(sid))
    check("replay", lambda: service.run_workflow(recipe["artifacts"][0]["path"], {"width": 5}, sid))
    nodes = check("nodes", lambda: service.gui_session_action(sid, "list_nodes", {}))
    if len(nodes["data"]["rows"]) != 27 or max(row[1] for row in nodes["data"]["rows"]) != 5:
        raise RuntimeError("Replay geometry does not match parameters")
    check(
        "translate",
        lambda: service.gui_session_action(
            sid, "translate_mesh_nodes", dict(node_ids=[27], offset=[0.1, 0, 0], units="mm")
        ),
    )
    rotated = check(
        "rotate",
        lambda: service.gui_session_action(
            sid,
            "rotate_mesh_nodes",
            dict(node_ids=list(range(1, 28)), axis="z", angle=90, center=[0, 0, 0], units="mm"),
        ),
    )
    check("quality", lambda: service.inspect_mesh_quality(rotated["artifacts"][0]["path"], "mm"))
    check("hide", lambda: service.set_gui_part_visibility(sid, "hide", [1]))
    check("show", lambda: service.set_gui_part_visibility(sid, "all"))
    saved = check("checkpoint", lambda: service.checkpoint_gui_session(sid))
    check("clear", lambda: service.reset_gui_session(sid))
    restored = check("restore", lambda: service.restore_gui_checkpoint(sid, saved["artifacts"][0]["path"]))
    if (
        restored["data"]["counts"]["nodes"] != 27
        or service.inspect_gui_session(sid)["process"]["pid"] != meta["process"]["pid"]
    ):
        raise RuntimeError("Checkpoint/PID invariant failed")
    check(
        "snapshot", lambda: service.set_gui_display(sid, view="isometric", display_mode="shaded", center=True)
    )
    if not args.keep_open:
        closed = check("close", lambda: service.close_gui_session(sid))
        if closed["state"] != "closed":
            raise RuntimeError("Close is pending; do not report the native process as closed")
    print("Evidence: " + str(root / "acceptance.json"))


if __name__ == "__main__":
    main()
