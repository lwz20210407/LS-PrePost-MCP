"""Opt-in native MP4, recording and parameter replay on one private result family."""

import argparse
import json
import re
import uuid
from pathlib import Path

from run_result_selection_acceptance import hashes

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable, source):
    source = Path(source).resolve(strict=True)
    family = [source] + sorted(
        p
        for p in source.parent.iterdir()
        if p.is_file() and re.fullmatch(re.escape(source.name) + r"\d+", p.name)
    )
    before = hashes(family)
    root = Path(workspace).resolve() / ("native-movie-acceptance-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    service = Service(Settings(root, Path(executable), allowed_roots=(source.parent,), timeout=120))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session-start.json", session)
    service.show_gui_session(sid, maximize=True)
    assert service.open_in_gui_session(sid, str(source), "d3plot")["status"] == "succeeded"
    info = service.set_gui_display(sid, state=2, view="isometric", center=True, capture=False)
    assert info["status"] == "succeeded" and info["data"]["counts"]["states"] >= 4
    recipe = service.create_workflow(
        "Native movie output",
        [
            dict(
                id="movie",
                action="export_gui_animation",
                arguments=dict(last={"$param": "last"}, fps=12, width=640, height=480),
            )
        ],
        defaults=dict(last=3),
    )
    service.start_session_recording(sid)
    first = service.run_workflow(recipe["artifacts"][0]["path"], session_id=sid)
    atomic_json(root / "first.json", first)
    assert first["status"] == "succeeded", first.get("error")
    movie = first["data"]["steps"]["movie"]
    assert movie["data"]["video"]["decoded_frames"] == 3
    assert movie["state_restoration"]["observed"] == 2
    recorded = service.stop_session_recording(sid)
    atomic_json(root / "recorded.json", recorded)
    assert recorded["status"] == "succeeded" and recorded["managed_steps"] == 1
    parametrized = service.parameterize_workflow(
        recorded["workflow"], [dict(step_id="step1", path=["last"], parameter="last")]
    )
    replay = service.run_workflow(parametrized["artifacts"][0]["path"], dict(last=4), session_id=sid)
    atomic_json(root / "replay.json", replay)
    assert replay["status"] == "succeeded", replay.get("error")
    assert replay["data"]["steps"]["step1"]["data"]["video"]["decoded_frames"] == 4
    whole = service.export_gui_animation(sid, width=640, height=480)
    atomic_json(root / "whole.json", whole)
    assert whole["status"] == "succeeded", whole.get("error")
    assert whole["data"]["video"]["decoded_frames"] == info["data"]["counts"]["states"]
    assert before == hashes(family)
    summary = dict(
        status="succeeded",
        recorded_replay_frames=[3, 4],
        full_timeline_frames=whole["data"]["video"]["decoded_frames"],
        source_unchanged=True,
        scope="Native H264, start1/step1/current display only; no arbitrary ranges or fringe semantic certification",
        evidence=str(root),
    )
    atomic_json(root / "acceptance.json", summary)
    service.close_gui_session(sid, save_checkpoint=False)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "executable", "source"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    accept(args.workspace, args.executable, args.source)
