"""Opt-in BySet -> Node set -> SPC -> changed-set replay -> native reopen."""

import argparse
import json
import uuid
from pathlib import Path

from run_element_set_acceptance import fixture

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.entity_cards import inspect_cards
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("ss-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    source = root / "model.k"
    registry = fixture(source)
    original = source.read_bytes()
    service = Service(Settings(root, Path(executable), timeout=120))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session.json", session)
    cases = []
    print(root, flush=True)

    def checked(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        cases.append(name)
        print(name, flush=True)
        return result

    def selected(name, kind, sets, expected, **kw):
        r = checked(name, service.select_gui_entities(sid, kind, set_ids=sets, **kw))
        assert r["verification"]["selected_ids"] == sorted(expected)
        assert r["verification"]["set_source"]["set_ids"] == sets
        return r

    try:
        service.show_gui_session(sid, maximize=True)
        checked("open", service.open_in_gui_session(sid, str(source)))
        checked("display", service.set_gui_display(sid, view="isometric", center=True, capture=True))
        checked(
            "nodes55",
            service.create_gui_entity_set(sid, "node", 55, "Alternative supports", entity_ids=[1001, 1002]),
        )
        checked("parts41", service.create_gui_entity_set(sid, "part", 41, "Two parts", entity_ids=[1, 2]))
        for kind, members in registry.items():
            checked("create-" + kind, service.create_gui_entity_set(sid, kind, 41, kind, entity_ids=members))
            selected("byset-" + kind, kind, [41], members)
        selected("byset-part", "part", [41], [1, 2])
        checked(
            "hide-element", service.set_gui_entity_visibility(sid, "solid", "hide", [registry["solid"][0]])
        )
        selected("hidden-solid-set", "solid", [41], registry["solid"])
        selected("union-node-sets", "node", [41, 55], [1000, 1001, 1002])
        selected("inverted-part-set", "part", [41], [3], invert=True)
        before = service._session_manager().read(sid)
        try:
            service.select_gui_entities(sid, "node", set_ids=[987654])
        except ValueError as exc:
            assert "does not exist" in str(exc)
            after = service._session_manager().read(sid)
            assert (
                after["state"] == "ready"
                and after["dirty"] == before["dirty"]
                and after["last_checkpoint"] == before["last_checkpoint"]
            )
            checked("missing-set-rejected", dict(status="succeeded", expected_rejection=str(exc)))
        else:
            raise AssertionError("Missing set unexpectedly accepted")
        service.start_session_recording(sid)
        selection = selected("record-byset", "node", [41], [1000])
        checked(
            "consumer-node-set",
            service.create_gui_entity_set(
                sid, "node", 56, "Supports", selection_job=selection["job_directory"]
            ),
        )
        checked(
            "consumer-spc", service.create_gui_spc(sid, 600, "Support X", [1, 0, 0, 0, 0, 0], node_set_id=56)
        )
        recording = checked("recording", service.stop_session_recording(sid))
        w = json.loads(Path(recording["workflow"]).read_text(encoding="utf8"))
        assert w["steps"][0]["arguments"]["set_ids"] == [41]
        assert w["steps"][1]["arguments"]["selection_job"] == {"$result": "step1", "path": ["job_directory"]}
        p = service.parameterize_workflow(
            recording["workflow"], [dict(step_id="step1", path=["set_ids"], parameter="support_sets")]
        )
        checked("replay-set55", service.run_workflow(p["artifacts"][0]["path"], dict(support_sets=[55]), sid))
        query = checked("replay-consumer-members", service.inspect_gui_entity_sets(sid, "node", 56))
        assert query["data"]["member_ids"] == [1001, 1002]
        parsed = inspect_cards(Path(query["job_directory"]) / "model.k")
        assert any(row["target_type"] == "node_set" and row["target_id"] == 56 for row in parsed["spcs"])
        checked(
            "modify-source-set",
            service.create_gui_entity_set(
                sid, "node", 55, "Updated source", entity_ids=[1003, 1004], mode="replace_members"
            ),
        )
        selected("fresh-members-after-modify", "node", [55], [1003, 1004])
        checked("raw-display", service.execute_gui_command(sid, "front", expected_counts={"nodes": 96}))
        before = service._session_manager().read(sid)
        selected("dirty-preserved", "node", [55], [1003, 1004])
        after = service._session_manager().read(sid)
        assert before["dirty"] and after["dirty"] and before["last_checkpoint"] == after["last_checkpoint"]
        saved = checked("checkpoint", service.checkpoint_gui_session(sid))
        path = next(a["path"] for a in saved["artifacts"] if a["kind"] == "keyword")
        checked("reopen", service.open_in_gui_session(sid, path))
        selected("reopened-source-set", "node", [55], [1003, 1004])
        selected("reopened-consumer-set", "node", [56], [1001, 1002])
        assert source.read_bytes() == original
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                cases=cases,
                source_unchanged=True,
                scope="Visible4.13.4 same-domain explicit-list BySet union/invert,hidden entities,missing set,typed recording/changed-set replay to node set+SPC,changed membership refresh,dirty/checkpoint preservation,native reopen. No Generate/General/Collect or result keyword-association certification",
            ),
        )
    finally:
        atomic_json(root / "closed.json", service.close_gui_session(sid, save_checkpoint=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True)
    p.add_argument("--executable", required=True)
    accept(**vars(p.parse_args()))
