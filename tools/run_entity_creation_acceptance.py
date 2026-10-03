"""Opt-in visible selection -> node/part sets -> SPC -> replay/edit/reopen acceptance."""

import argparse
import json
import uuid
from pathlib import Path

from run_gui_visibility_acceptance import mixed_fixture

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.entity_cards import inspect_cards
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("native-entity-creation-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    source = root / "mixed.k"
    mixed_fixture(source)
    source.write_text(source.read_text().replace("*END", "*SET_NODE_LIST_TITLE\nOriginal attributes\n300,0.25,0.5,0.75,1.0\n11,12\n*END"), encoding="ascii")
    original = source.read_bytes()
    service = Service(Settings(root, Path(executable), timeout=180))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session.json", session)
    cases = []

    def checked(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        print(name, flush=True)
        cases.append(name)
        return result

    def rejected(name, operation, message):
        try:
            operation()
        except ValueError as exc:
            assert message in str(exc), str(exc)
            assert service.inspect_gui_session(sid)["state"] == "ready"
            atomic_json(root / (name + ".json"), dict(expected_rejection=str(exc)))
            cases.append(name)
            print(name, flush=True)
        else:
            raise AssertionError("Expected rejection: " + name)

    try:
        service.show_gui_session(sid, maximize=True)
        checked("open", service.open_in_gui_session(sid, str(source)))
        service.start_session_recording(sid)
        checked("blank", service.set_gui_entity_visibility(sid, "shell", "hide", [101]))
        selected = checked("select-nodes", service.select_gui_entities(sid, "node", [1, 2]))
        checked("node-set", service.create_gui_entity_set(sid, "node", 100, "Support nodes", selection_job=selected["job_directory"]))
        selected_parts = checked("select-parts", service.select_gui_entities(sid, "part", [1, 2]))
        checked("part-set", service.create_gui_entity_set(sid, "part", 200, "Structural parts", selection_job=selected_parts["job_directory"]))
        checked("spc-set", service.create_gui_spc(sid, 1000, "Support XYZ", [1, 1, 1, 0, 0, 0], node_set_id=100))
        recording = checked("recording", service.stop_session_recording(sid))
        definition = json.loads(Path(recording["workflow"]).read_text(encoding="utf-8"))
        assert definition["steps"][2]["arguments"]["selection_job"] == {"$result": "step2", "path": ["job_directory"]}
        parameterized = service.parameterize_workflow(recording["workflow"], [
            dict(step_id="step2", path=["entity_ids"], parameter="support_nodes"),
            dict(step_id="step3", path=["set_id"], parameter="support_set"),
            dict(step_id="step6", path=["node_set_id"], parameter="support_set")])
        checked("changed-selection-replay", service.run_workflow(parameterized["artifacts"][0]["path"],
                                                                 dict(support_nodes=[3, 4], support_set=110), sid))
        query = checked("query", service.inspect_gui_entity_sets(sid, "node", 110))
        assert query["data"]["member_ids"] == [3, 4]
        parts = checked("part-page", service.inspect_gui_entity_sets(sid, "part", 200, limit=1))
        assert parts["data"]["member_ids"] == [1] and parts["data"]["next_offset"] == 1
        rejected("set-collision", lambda: service.create_gui_entity_set(sid, "node", 110, "Collision", entity_ids=[5]), "already exists")
        rejected("unknown-node", lambda: service.create_gui_entity_set(sid, "node", 111, "Unknown", entity_ids=[999999]), "unknown")
        rejected("old-selection", lambda: service.create_gui_entity_set(sid, "node", 112, "Stale", selection_job=selected["job_directory"]), "older model")
        rejected("overlapping-spc", lambda: service.create_gui_spc(sid, 1001, "Duplicate X", [1, 0, 0, 0, 0, 0], node_ids=[3]), "overlaps")
        rejected("constraint-id-collision", lambda: service.create_gui_spc(sid, 1000, "Duplicate ID", [1, 0, 0, 0, 0, 0], node_ids=[9]), "ID already")
        rejected("unknown-coordinate", lambda: service.create_gui_spc(sid, 1002, "Unknown system", [1, 0, 0, 0, 0, 0], node_ids=[9], coordinate_system=999), "coordinate")
        checked("replace-support", service.create_gui_entity_set(sid, "node", 110, "Revised support", entity_ids=[5, 6], mode="replace_members"))
        checked("replace-parts", service.create_gui_entity_set(sid, "part", 200, "Shell only", entity_ids=[2], mode="replace_members"))
        checked("replace-attributes", service.create_gui_entity_set(sid, "node", 300, "Keep attributes", entity_ids=[7, 8], mode="replace_members"))
        attrs = checked("attributes", service.inspect_gui_entity_sets(sid, "node", 300))
        assert attrs["data"]["attributes"] == [0.25, 0.5, 0.75, 1.0]
        final = checked("spc-nodes", service.create_gui_spc(sid, 1003, "Node X", [1, 0, 0, 0, 0, 0], node_ids=[9, 10]))
        rejected("replacement-conflict", lambda: service.create_gui_entity_set(sid, "node", 110, "Conflicting support", entity_ids=[9, 10], mode="replace_members"), "overlaps")
        saved = next(a["path"] for a in final["artifacts"] if a["kind"] == "keyword")
        expected = inspect_cards(Path(saved))
        checked("reopen", service.open_in_gui_session(sid, saved))
        node_query = checked("reopen-node-set", service.inspect_gui_entity_sets(sid, "node", 110))
        assert node_query["data"]["member_ids"] == [5, 6]
        part_query = checked("reopen-part-set", service.inspect_gui_entity_sets(sid, "part", 200))
        assert part_query["data"]["member_ids"] == [2]
        after = inspect_cards(Path(part_query["job_directory"]) / "model.k")
        assert after == expected
        assert source.read_bytes() == original
        atomic_json(root / "acceptance.json", dict(status="succeeded", cases=cases, source_unchanged=True,
                    scope="Standard node/part list sets create/query/member replacement; global SPC_SET/NODE, explicit selection dependency replay; no solver run/Segment/pressure/nonreflecting certification"))
    finally:
        atomic_json(root / "closed.json", service.close_gui_session(sid, save_checkpoint=False))
    print(root, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    accept(**vars(parser.parse_args()))
