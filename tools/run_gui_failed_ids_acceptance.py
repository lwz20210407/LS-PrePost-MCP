"""Opt-in native failed user-ID capture -> selection -> parameterized recording replay."""

import argparse
import json
import uuid
from pathlib import Path

from run_gui_solid_quality_acceptance import MODEL

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json, fingerprint
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("native-failed-ids-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    source = root / "synthetic.k"
    source.write_text(
        MODEL.replace("1,1,1,2,3,4,5,6,7,8", "101,1,1,2,3,4,5,6,7,8").replace(
            "2,1,2,9,10,3,6,11,12,7", "507,1,2,9,10,3,6,11,12,7"
        )
    )
    identity = fingerprint(source)
    service = Service(Settings(root, Path(executable), timeout=60))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session-start.json", session)
    service.show_gui_session(sid, maximize=True)
    assert service.open_in_gui_session(sid, str(source))["status"] == "succeeded"
    service.set_gui_display(sid, view="isometric", center=True, capture=False)
    service.save_gui_selection_buffer(sid, "node", [1, 2], 1)
    service.save_gui_selection_buffer(sid, "node", [3, 4], 2)
    original_buffers = service._session_manager().read(sid)["selection_buffers"]
    criteria = [dict(metric="volume", comparison=c, threshold=1.5) for c in ("gt", "lt")]
    counts = service.check_gui_solid_quality(sid, criteria, "mm")
    assert counts["status"] == "succeeded" and "failed_element_ids" not in counts["verification"]
    assert service._session_manager().read(sid)["selection_buffers"] == original_buffers
    captured = service.check_gui_solid_quality(sid, criteria, "mm", capture_failed_ids=True)
    atomic_json(root / "captured.json", captured)
    assert captured["status"] == "succeeded", captured.get("error")
    report = captured["verification"]
    assert report["failed_element_ids"] == [101, 507] and report["failed_part_ids"] == [1]
    assert [c["failed_element_id_sample"] for c in report["criteria"]] == [[101], [507]]
    assert "1" not in service._session_manager().read(sid)["selection_buffers"]
    backup = json.loads(Path(report["prior_managed_buffer1"]["path"]).read_text())
    assert backup["previous_managed_metadata"] == original_buffers["1"]
    assert service.load_gui_selection_buffer(sid, 2)["verification"]["selected_ids"] == [3, 4]
    cleared = service.check_gui_solid_quality(
        sid, [dict(metric="aspect_ratio", comparison="gt", threshold=10)], "mm", capture_failed_ids=True
    )
    assert cleared["status"] == "succeeded" and cleared["verification"]["failed_element_ids"] == []
    assert service.inspect_gui_mesh(sid, include_entities=True)["data"]["selection_ids"] == []
    recipe = service.create_workflow(
        "Locate failed native solid IDs",
        [
            dict(
                id="quality",
                action="check_gui_solid_quality",
                quality_policy="report_only",
                arguments=dict(
                    checks=[dict(metric="aspect_ratio", comparison="gt", threshold={"$param": "limit"})],
                    units="mm",
                    capture_failed_ids=True,
                ),
            ),
            dict(
                id="locate",
                action="select_gui_entities",
                arguments=dict(
                    entity_type="solid",
                    entity_ids={"$result": "quality", "path": ["verification", "failed_element_ids"]},
                ),
            ),
        ],
        dict(limit=1.5),
    )
    service.start_session_recording(sid)
    first = service.run_workflow(recipe["artifacts"][0]["path"], session_id=sid)
    atomic_json(root / "first.json", first)
    assert first["status"] == "succeeded", first.get("error")
    assert first["data"]["steps"]["locate"]["verification"]["selected_ids"] == [101]
    recording = service.stop_session_recording(sid)
    assert recording["status"] == "succeeded" and recording["managed_steps"] == 2
    template = service.parameterize_workflow(
        recording["workflow"], [dict(step_id="step1", path=["checks", 0, "threshold"], parameter="limit")]
    )
    replay = service.run_workflow(template["artifacts"][0]["path"], dict(limit=0.5), session_id=sid)
    atomic_json(root / "replay.json", replay)
    assert replay["status"] == "succeeded", replay.get("error")
    assert replay["data"]["steps"]["step2"]["verification"]["selected_ids"] == [101, 507]
    assert service._session_manager().read(sid).get("selection_buffers", {}) == {}
    assert fingerprint(source) == identity
    atomic_json(
        root / "acceptance.json",
        dict(
            status="succeeded",
            session_id=sid,
            noncontiguous_user_ids=True,
            disjoint_criterion_capture=True,
            zero_after_failure=True,
            explicit_buffer1_invalidation=True,
            other_buffer_preserved=True,
            dependency_replay=True,
            source_unchanged=True,
        ),
    )
    print(json.dumps(dict(status="succeeded", evidence_directory=str(root))), flush=True)
    service.close_gui_session(sid, save_checkpoint=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    args = parser.parse_args()
    accept(args.workspace, args.executable)
