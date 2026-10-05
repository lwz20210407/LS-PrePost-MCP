"""Visible selection/set/motion workflow, parameter replay, conflicts and reopen."""

import argparse
import json
import uuid
from pathlib import Path

from run_element_set_acceptance import fixture

from ls_prepost_mcp.boundary_cards import inspect_boundary_cards
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.entity_cards import inspect_cards
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable, public_keyword=None):
    root = Path(workspace).resolve() / ("pma-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    source = root / "mixed.k"
    fixture(source)
    original = source.read_bytes()
    public_path = Path(public_keyword).resolve() if public_keyword else None
    public_original = public_path.read_bytes() if public_path else None
    s = Service(
        Settings(
            root, Path(executable), allowed_roots=(public_path.parent,) if public_path else (), timeout=90
        )
    )
    meta = s.start_gui_session()
    sid = meta["session_id"]
    atomic_json(root / "session.json", meta)
    s.show_gui_session(sid, maximize=True)
    cases = []
    print(root, flush=True)

    def check(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        cases.append(name)
        print(name, flush=True)
        return result

    def reject(name, call):
        try:
            call()
        except ValueError as exc:
            atomic_json(root / (name + ".json"), dict(status="expected_rejection", message=str(exc)))
            cases.append(name)
            print(name, flush=True)
        else:
            raise AssertionError("Expected rejection: " + name)

    def motion(**kwargs):
        return s.create_gui_prescribed_motion(sid, time_unit="ms", length_unit="mm", **kwargs)

    try:
        check("open", s.open_in_gui_session(sid, str(source)))
        check("set55", s.create_gui_entity_set(sid, "node", 55, "Alternative", entity_ids=[1001, 1002]))
        check("spc-x", s.create_gui_spc(sid, 600, "Support X", [1, 0, 0, 0, 0, 0], node_set_id=41))
        check("hide-solid", s.set_gui_entity_visibility(sid, "solid", "hide", [101]))
        s.start_session_recording(sid)
        selected = check("record-byset", s.select_gui_entities(sid, "node", set_ids=[41]))
        check(
            "record-consumer-set",
            s.create_gui_entity_set(sid, "node", 56, "Driven set", selection_job=selected["job_directory"]),
        )
        check(
            "record-set-displacement",
            motion(
                motion_id=500,
                title="Prescribed Z",
                axis="z",
                motion="displacement",
                curve_id=700,
                node_set_id=56,
                points=[[0.0, 0.0], [0.5, 1.0], [1.0, 3.0]],
                curve_title="Displacement ramp",
                birth=0.1,
                death=2.0,
                scale=1.5,
            ),
        )
        selected_nodes = check(
            "record-node-selection", s.select_gui_entities(sid, "node", entity_ids=[1004, 1005])
        )
        check(
            "record-node-velocity",
            motion(
                motion_id=601,
                title="Nodal velocity",
                axis="y",
                motion="velocity",
                curve_id=701,
                selection_job=selected_nodes["job_directory"],
                points=[[0.0, 0.0], [1.0, 10.0]],
                curve_title="Velocity history",
            ),
        )
        recording = check("stop-recording", s.stop_session_recording(sid))
        workflow = json.loads(Path(recording["workflow"]).read_text(encoding="utf8"))
        assert workflow["steps"][4]["arguments"]["selection_job"] == {
            "$result": "step4",
            "path": ["job_directory"],
        }
        parameterized = s.parameterize_workflow(
            recording["workflow"],
            [
                dict(step_id="step1", path=["set_ids"], parameter="sets"),
                dict(step_id="step3", path=["points"], parameter="motion_points"),
                dict(step_id="step4", path=["entity_ids"], parameter="nodes"),
            ],
        )
        check(
            "replay",
            s.run_workflow(
                parameterized["artifacts"][0]["path"],
                dict(sets=[55], motion_points=[[0.0, 0.0], [0.5, 2.0], [1.0, 6.0]], nodes=[1024, 1025]),
                sid,
            ),
        )
        queried = check("replayed-set", s.inspect_gui_entity_sets(sid, "node", 56))
        assert queried["data"]["member_ids"] == [1001, 1002]
        cards = inspect_boundary_cards(Path(queried["job_directory"]) / "model.k", include_motions=True)
        assert cards["curves"][700]["points"][-1] == [1.0, 6.0]
        assert {m["target_id"] for m in cards["motions"] if m["motion_id"] == 601} == {1024, 1025}
        reject(
            "stale-selection",
            lambda: motion(
                motion_id=990,
                title="Stale",
                axis="x",
                motion="displacement",
                curve_id=700,
                selection_job=selected_nodes["job_directory"],
            ),
        )
        reject(
            "motion-over-spc",
            lambda: motion(
                motion_id=991, title="Conflict", axis="x", motion="displacement", curve_id=700, node_set_id=41
            ),
        )
        reject(
            "spc-over-motion",
            lambda: s.create_gui_spc(sid, 901, "Conflict Z", [0, 0, 1, 0, 0, 0], node_ids=[1001]),
        )
        check(
            "orthogonal-spc", s.create_gui_spc(sid, 902, "Support X new", [1, 0, 0, 0, 0, 0], node_ids=[1001])
        )
        reject(
            "duplicate-motion",
            lambda: motion(
                motion_id=992, title="Duplicate", axis="z", motion="velocity", curve_id=701, node_set_id=56
            ),
        )
        reject(
            "missing-curve",
            lambda: motion(
                motion_id=993, title="Missing", axis="z", motion="velocity", curve_id=999, node_ids=[1100]
            ),
        )
        reject(
            "unknown-node",
            lambda: motion(
                motion_id=994, title="Unknown", axis="z", motion="velocity", curve_id=701, node_ids=[9999999]
            ),
        )
        reject(
            "implicit-group-append",
            lambda: motion(
                motion_id=601,
                title="Nodal velocity",
                axis="z",
                motion="velocity",
                curve_id=701,
                node_ids=[1024],
            ),
        )
        check(
            "explicit-group-append",
            motion(
                motion_id=601,
                title="Nodal velocity",
                axis="z",
                motion="velocity",
                curve_id=701,
                node_ids=[1024, 1025],
                append_to_group=True,
            ),
        )
        check(
            "acceleration-x",
            motion(
                motion_id=800,
                title="Acceleration X",
                axis="x",
                motion="acceleration",
                curve_id=800,
                node_ids=[1100, 1101],
                points=[[0.0, 0.0], [1.0, 2.0]],
                curve_title="Acceleration history",
            ),
        )
        for axis, kind, cid in [
            ("rx", "displacement", 810),
            ("ry", "velocity", 811),
            ("rz", "acceleration", 812),
        ]:
            options = (
                dict(points=[[0.0, 0.0], [1.0, 0.2]], curve_title="Angular history") if cid == 810 else {}
            )
            result = check(
                "rotation-" + axis,
                motion(
                    motion_id=cid,
                    title="Rotation " + axis,
                    axis=axis,
                    motion=kind,
                    curve_id=810,
                    node_ids=[1020, 1021, 1022],
                    **options,
                ),
            )
            assert result["verification"]["value_unit"].startswith("rad")
        reject(
            "set-change-motion-conflict",
            lambda: s.create_gui_entity_set(
                sid, "node", 56, "Driven set", entity_ids=[1024], mode="replace_members"
            ),
        )
        check(
            "set-change-safe",
            s.create_gui_entity_set(
                sid, "node", 56, "Driven set", entity_ids=[1040, 1041], mode="replace_members"
            ),
        )
        saved = check("checkpoint", s.checkpoint_gui_session(sid))
        before = inspect_boundary_cards(Path(saved["artifacts"][0]["path"]), include_motions=True)
        check("native-reopen", s.replace_gui_model(sid, saved["artifacts"][0]["path"]))
        queried = check("reopened-set", s.inspect_gui_entity_sets(sid, "node", 56))
        after = inspect_boundary_cards(Path(queried["job_directory"]) / "model.k", include_motions=True)
        assert before == after and queried["data"]["member_ids"] == [1040, 1041]
        assert len([m for m in after["motions"] if m["motion_id"] == 601]) == 4
        assert len(inspect_cards(Path(queried["job_directory"]) / "model.k")["spcs"]) == 2
        assert source.read_bytes() == original
        if public_path:
            rejected = s.replace_gui_model(sid, str(public_path))
            atomic_json(root / "legacy-partial-rejected.json", rejected)
            assert rejected["status"] == "failed" and rejected["old_model_unloaded"] is False
            failed_load = json.loads(
                (Path(rejected["job_directory"]) / "load-replacement.json").read_text(encoding="utf8")
            )
            assert "Invalid Keyword" in failed_load["error"]["message"]
            assert s.inspect_gui_session(sid)["state"] == "uncertain"
            cases.append("legacy-partial-import-rejected")
            atomic_json(root / "negative-session-close.json", s.close_gui_session(sid, save_checkpoint=False))
            restarted = check("restart-after-rejected-partial-import", s.restart_gui_session(sid))
            sid = restarted["session_id"]
            atomic_json(root / "restarted-session.json", s.inspect_gui_session(sid))
            saved_again = check("recovered-motion-checkpoint", s.checkpoint_gui_session(sid))
            assert before == inspect_boundary_cards(
                Path(saved_again["artifacts"][0]["path"]), include_motions=True
            )
            assert public_path.read_bytes() == public_original
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                cases=cases,
                motion_count=len(after["motions"]),
                original_unchanged=True,
                partial_import_negative_tested=bool(public_path),
                scope="4.13.4 visible global NODE/SET_ID creation, motion/curve group readback, selection dependencies and changed-members/curve replay; six axes and three motion modes; SPC/motion/set-change rejection and native reopen. Native deck contract, no solver/rotational-DOF eligibility certification.",
            ),
        )
    finally:
        atomic_json(root / "closed.json", s.close_gui_session(sid, save_checkpoint=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True)
    p.add_argument("--executable", required=True)
    p.add_argument(
        "--public-keyword",
        help="Optional legacy unsupported-keyword fixture; expected rejection and explicit recovery",
    )
    accept(**vars(p.parse_args()))
