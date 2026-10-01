"""Opt-in native absolute-coordinate edit, quality gate, recording and checkpoint reopen."""

import argparse
import json
import uuid
from pathlib import Path

from run_gui_gate_acceptance import MODEL

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json, fingerprint
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("native-coordinate-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    source = root / "synthetic.k"
    source.write_text(MODEL, encoding="ascii")
    original = fingerprint(source)
    service = Service(Settings(root, Path(executable), timeout=60))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session-start.json", session)
    service.show_gui_session(sid, maximize=True)
    assert service.open_in_gui_session(sid, str(source))["status"] == "succeeded"
    service.set_gui_display(sid, view="top", center=True, capture=False)
    recipe = service.create_workflow(
        "Absolute node alignment and native quality",
        [
            dict(
                id="coordinates",
                action="set_gui_node_coordinates",
                arguments=dict(
                    nodes=[dict(id=uid, coordinates=[{"$param": "width"}, None, None]) for uid in (2, 3)],
                    units="mm",
                ),
            ),
            dict(
                id="quality",
                action="check_gui_shell_quality",
                arguments=dict(thresholds=dict(aspect_ratio=10), units="mm"),
            ),
            dict(id="save", action="checkpoint", arguments={}),
        ],
        dict(width=3),
    )
    service.start_session_recording(sid)
    first = service.run_workflow(recipe["artifacts"][0]["path"], session_id=sid)
    atomic_json(root / "first.json", first)
    print("absolute_edit_quality", first["status"], flush=True)
    assert first["status"] == "succeeded", first.get("error")
    recording = service.stop_session_recording(sid)
    assert recording["status"] == "succeeded" and recording["managed_steps"] == 3
    parameterized = service.parameterize_workflow(
        recording["workflow"],
        [dict(step_id="step1", path=["nodes", i, "coordinates", 0], parameter="width") for i in (0, 1)],
    )
    replay = service.run_workflow(parameterized["artifacts"][0]["path"], dict(width=4), session_id=sid)
    atomic_json(root / "replay.json", replay)
    print("absolute_edit_parameter_replay", replay["status"], flush=True)
    assert replay["status"] == "succeeded", replay.get("error")
    final = replay["data"]["steps"]["step3"]["artifacts"][0]["path"]
    assert service.open_in_gui_session(sid, final)["status"] == "succeeded"

    def coordinates():
        snapshot = service.inspect_gui_mesh(sid, include_entities=True)
        assert snapshot["status"] == "succeeded"
        return snapshot["data"]["nodes"]

    expected = [[1, 0, 0, 0], [2, 4, 0, 0], [3, 4, 1, 0], [4, 0, 1, 0]]
    assert coordinates() == expected
    negative = service.run_workflow(recipe["artifacts"][0]["path"], dict(width=50), session_id=sid)
    atomic_json(root / "negative.json", negative)
    assert negative["status"] == "failed" and negative["data"]["failed_step"] == "quality"
    assert negative["data"]["skipped_steps"] == ["save"]
    baseline = negative["data"]["steps"]["coordinates"]["baseline_checkpoint"]
    assert service.restore_gui_checkpoint(sid, baseline)["status"] == "succeeded"
    assert coordinates() == expected
    assert fingerprint(source) == original
    assert service.set_gui_part_visibility(sid, "hide", [10])["status"] == "succeeded"
    multiple = service.set_gui_node_coordinates(
        sid,
        [
            dict(id=1, coordinates=[-0.5, None, None]),
            dict(id=2, coordinates=[4.5, 0.25, 0.2]),
            dict(id=3, coordinates=[4.5, 1.25, 0.2]),
        ],
        "mm",
    )
    atomic_json(root / "multiple-targets.json", multiple)
    assert multiple["status"] == "succeeded", multiple.get("error")
    assert multiple["verification"]["changed_count"] == 3
    assert multiple["verification"]["part_visibility_preserved"]
    assert service.inspect_gui_mesh(sid)["data"]["part_visibility"] == {"10": False}
    assert service.restore_gui_checkpoint(sid, multiple["baseline_checkpoint"])["status"] == "succeeded"
    assert coordinates() == expected
    summary = dict(
        status="succeeded",
        session_id=sid,
        absolute_axis_targets=True,
        quality_pass_and_fail=True,
        parameterized_recording=True,
        original_unchanged=True,
        checkpoint_reopen_and_restore=True,
        grouped_full_xyz_and_hidden_parts=True,
        scope="Synthetic four-node shell, native translation-based coordinate edit; no full Node Edit/CAD projection coverage",
    )
    atomic_json(root / "acceptance.json", summary)
    print(json.dumps(dict(status="succeeded", evidence_directory=str(root))), flush=True)
    service.close_gui_session(sid, save_checkpoint=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    args = parser.parse_args()
    accept(args.workspace, args.executable)
