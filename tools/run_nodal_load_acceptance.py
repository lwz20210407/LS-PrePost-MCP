"""Opt-in native load selection/set, distribution, replay and explicit reopen."""

import argparse
import json
import math
import uuid
from pathlib import Path

from run_element_set_acceptance import fixture

from ls_prepost_mcp.boundary_cards import inspect_boundary_cards
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("nla-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    source = root / "mixed.k"
    fixture(source)
    original = source.read_bytes()
    s = Service(Settings(root, Path(executable), timeout=90))
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

    def load(**kw):
        return s.create_gui_nodal_load(sid, time_unit="ms", **kw)

    try:
        check("open", s.open_in_gui_session(sid, str(source)))
        check("set55", s.create_gui_entity_set(sid, "node", 55, "Load nodes", entity_ids=[1000, 1001, 1002]))
        check("spc-x", s.create_gui_spc(sid, 600, "Support X", [1, 0, 0, 0, 0, 0], node_ids=[1000]))
        check("hide-solid", s.set_gui_entity_visibility(sid, "solid", "hide", [101]))
        s.start_session_recording(sid)
        selected = check("select", s.select_gui_entities(sid, "node", entity_ids=[1000, 1001, 1002]))
        total = check(
            "total-from-selection",
            load(
                axis="z",
                curve_id=700,
                value_unit="N",
                distribution="total_equal",
                selection_job=selected["job_directory"],
                points=[[0.0, 0.0], [1.0, 90.0]],
                curve_title="Total force",
            ),
        )
        assert math.isclose(total["verification"]["summed_scale"], 1.0)
        assert total["verification"]["affected_node_count"] == 3
        check(
            "per-node-set",
            load(
                axis="y",
                curve_id=701,
                value_unit="N",
                distribution="per_node",
                node_set_id=55,
                points=[[0.0, 0.0], [1.0, 20.0]],
                curve_title="Per node force",
            ),
        )
        recording = check("stop-recording", s.stop_session_recording(sid))
        flow = json.loads(Path(recording["workflow"]).read_text(encoding="utf8"))
        assert flow["steps"][1]["arguments"]["selection_job"] == {
            "$result": "step1",
            "path": ["job_directory"],
        }
        template = s.parameterize_workflow(
            recording["workflow"],
            [
                dict(step_id="step1", path=["entity_ids"], parameter="nodes"),
                dict(step_id="step2", path=["points"], parameter="force"),
            ],
        )
        check(
            "parameter-replay",
            s.run_workflow(
                template["artifacts"][0]["path"],
                dict(nodes=[1020, 1021], force=[[0.0, 0.0], [1.0, 120.0]]),
                sid,
            ),
        )
        saved = check("save-replay", s.checkpoint_gui_session(sid))
        cards = inspect_boundary_cards(Path(saved["artifacts"][0]["path"]), include_nodal_loads=True)
        rows = [r for r in cards["nodal_loads"] if r["curve_id"] == 700]
        assert {r["target_id"] for r in rows} == {1020, 1021}
        assert all(r["scale"] == 0.5 for r in rows)
        assert cards["curves"][700]["points"][-1] == [1.0, 120.0]
        reject(
            "stale-selection",
            lambda: load(
                axis="x",
                curve_id=700,
                value_unit="N",
                distribution="per_node",
                selection_job=selected["job_directory"],
            ),
        )
        reject(
            "same-dof-overlap",
            lambda: load(axis="y", curve_id=701, value_unit="N", distribution="per_node", node_ids=[1001]),
        )
        check(
            "explicit-superposition",
            load(
                axis="y",
                curve_id=701,
                value_unit="N",
                distribution="per_node",
                node_ids=[1001],
                allow_superposition=True,
                scale=-0.5,
            ),
        )
        constrained = check(
            "load-on-supported-node",
            load(axis="x", curve_id=701, value_unit="N", distribution="per_node", node_ids=[1000]),
        )
        assert constrained["verification"]["constraint_review"]
        for i, axis in enumerate(("rx", "ry", "rz")):
            check(
                "moment-" + axis,
                load(
                    axis=axis,
                    curve_id=710 + i,
                    value_unit="N*mm",
                    distribution="total_equal",
                    node_ids=[1004, 1005],
                    points=[[0.0, 0.0], [1.0, 12.0]],
                    curve_title="Moment " + axis,
                ),
            )
        frozen = check(
            "total-set-snapshot",
            load(
                axis="z",
                curve_id=720,
                value_unit="N",
                distribution="total_equal",
                node_set_id=55,
                points=[[0.0, 0.0], [1.0, 60.0]],
                curve_title="Snapshot total",
            ),
        )
        assert not frozen["verification"]["set_membership_linked"]
        check(
            "change-set-members",
            s.create_gui_entity_set(
                sid, "node", 55, "Load nodes", entity_ids=[1000, 1001], mode="replace_members"
            ),
        )
        reject(
            "missing-curve",
            lambda: load(axis="x", curve_id=999, value_unit="N", distribution="per_node", node_ids=[1100]),
        )
        reject(
            "missing-node",
            lambda: load(axis="x", curve_id=701, value_unit="N", distribution="per_node", node_ids=[999999]),
        )
        reject(
            "curve-collision",
            lambda: load(
                axis="x",
                curve_id=701,
                value_unit="N",
                distribution="per_node",
                node_ids=[1100],
                points=[[0.0, 0.0], [1.0, 1.0]],
                curve_title="Collision",
            ),
        )
        saved = check("final-save", s.checkpoint_gui_session(sid))
        before = inspect_boundary_cards(Path(saved["artifacts"][0]["path"]), include_nodal_loads=True)
        frozen_rows = [r for r in before["nodal_loads"] if r["curve_id"] == 720]
        assert {r["target_id"] for r in frozen_rows} == {1000, 1001, 1002}
        assert len([r for r in before["nodal_loads"] if r["target_type"] == "node_set"]) == 1
        atomic_json(root / "close-before-reopen.json", s.close_gui_session(sid, save_checkpoint=False))
        restarted = check("explicit-restart", s.restart_gui_session(sid))
        sid = restarted["session_id"]
        s.show_gui_session(sid, maximize=True)
        saved = check("reopened-save", s.checkpoint_gui_session(sid))
        assert inspect_boundary_cards(Path(saved["artifacts"][0]["path"]), include_nodal_loads=True) == before
        assert source.read_bytes() == original
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                cases=cases,
                source_unchanged=True,
                scope="4.13.4 native selection/SET loads, total vs per-node, six global DOFs, overlap/SPC reporting, parameter replay, set-snapshot semantics and fresh-process reopen. No solver/follower/local/rigid/old-version/headless certification.",
            ),
        )
    finally:
        atomic_json(root / "closed.json", s.close_gui_session(sid, save_checkpoint=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    accept(**vars(parser.parse_args()))
