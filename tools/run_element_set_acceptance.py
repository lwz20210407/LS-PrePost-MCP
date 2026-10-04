"""Opt-in visible GUI selection -> element sets -> parameter replay -> reopen."""

import argparse
import json
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.entity_cards import inspect_cards
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def fixture(path):
    nodes, solids, shells, beams = [], [], [], []
    registry = {kind: [] for kind in ("solid", "shell", "beam")}
    for i in range(12):
        n = [1000 + i * 20 + j for j in range(8)]
        for uid, (x, y, z) in zip(
            n, ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))
        ):
            nodes.append(f"{uid},{3 * i + x},{y},{z}")
        for kind, first in [("solid", 101), ("shell", 1001), ("beam", 2001)]:
            registry[kind].append(first + 7 * i)
        solids.append(",".join(map(str, [registry["solid"][-1], 1, *n])))
        shells.append(",".join(map(str, [registry["shell"][-1], 2, *n[:4]])))
        beams.append(",".join(map(str, [registry["beam"][-1], 3, n[4], n[5], 0])))
    path.write_text(
        "\n".join(
            [
                "*KEYWORD",
                "*TITLE",
                "Element set acceptance fixture",
                "*NODE",
                *nodes,
                "*ELEMENT_SOLID",
                *solids,
                "*ELEMENT_SHELL",
                *shells,
                "*ELEMENT_BEAM",
                *beams,
                "*PART",
                "Solids",
                "1,1,1",
                "*PART",
                "Shells",
                "2,2,1",
                "*PART",
                "Beams",
                "3,3,1",
                "*SECTION_SOLID",
                "1,1",
                "*SECTION_SHELL",
                "2,2",
                "0.1,0.1,0.1,0.1",
                "*SECTION_BEAM",
                "3,1",
                "1,1,0,0,0,0,0,0",
                "*MAT_ELASTIC",
                "1,1,100000,0.3",
                "*SET_NODE_LIST_TITLE",
                "Existing node domain",
                "41",
                "1000",
                "*END",
                "",
            ]
        ),
        encoding="ascii",
    )
    return registry


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("es-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    source = root / "mixed.k"
    registry = fixture(source)
    original = source.read_bytes()
    service = Service(Settings(root, Path(executable), timeout=120))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session.json", session)
    cases = []
    print(str(root), flush=True)

    def checked(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        cases.append(name)
        print(name, flush=True)
        return result

    def rejected(name, call, contains):
        try:
            call()
        except ValueError as exc:
            assert contains in str(exc), str(exc)
            assert service.inspect_gui_session(sid)["state"] == "ready"
            atomic_json(root / (name + ".json"), dict(expected_rejection=str(exc)))
            cases.append(name)
            print(name, flush=True)
        else:
            raise AssertionError("Expected rejection: " + name)

    try:
        service.show_gui_session(sid, maximize=True)
        checked("open", service.open_in_gui_session(sid, str(source)))
        checked("display", service.set_gui_display(sid, view="isometric", center=True, capture=True))
        service.start_session_recording(sid)
        checked("hide", service.set_gui_entity_visibility(sid, "solid", "hide", [registry["solid"][0]]))
        selections = {}
        for kind in ("shell", "solid", "beam"):
            selections[kind] = checked(
                "select-" + kind, service.select_gui_entities(sid, kind, registry[kind])
            )
            checked(
                "create-" + kind,
                service.create_gui_entity_set(
                    sid, kind, 41, kind + " elements", selection_job=selections[kind]["job_directory"]
                ),
            )
        record = checked("record", service.stop_session_recording(sid))
        for kind in registry:
            q = checked("query-" + kind, service.inspect_gui_entity_sets(sid, kind, 41))
            assert q["data"]["member_ids"] == registry[kind] and q["data"]["total"] == 12
        q = checked("page-solid", service.inspect_gui_entity_sets(sid, "solid", 41, offset=8, limit=2))
        assert q["data"]["member_ids"] == registry["solid"][8:10] and q["data"]["next_offset"] == 10
        rejected(
            "wrong-domain",
            lambda: service.create_gui_entity_set(
                sid, "shell", 50, "Wrong", entity_ids=[registry["solid"][0]]
            ),
            "unknown",
        )
        rejected(
            "collision",
            lambda: service.create_gui_entity_set(
                sid, "beam", 41, "Collision", entity_ids=[registry["beam"][0]]
            ),
            "already exists",
        )
        rejected(
            "selection-domain",
            lambda: service.create_gui_entity_set(
                sid, "solid", 50, "Wrong selection", selection_job=selections["shell"]["job_directory"]
            ),
            "entity type",
        )
        definition = json.loads(Path(record["workflow"]).read_text(encoding="utf8"))
        bindings = []
        values = {}
        for step in definition["steps"]:
            # Typed recording retains the selection-result dependency.
            args = step["arguments"]
            kind = args.get("entity_type")
            if step["action"] == "select_gui_entities":
                parameter = kind + "_members"
                bindings.append(dict(step_id=step["id"], path=["entity_ids"], parameter=parameter))
                values[parameter] = registry[kind][-3:]
            if step["action"] == "create_gui_entity_set":
                assert isinstance(args["selection_job"], dict)
                parameter = kind + "_sid"
                bindings.append(dict(step_id=step["id"], path=["set_id"], parameter=parameter))
                values[parameter] = 42
        prepared = service.parameterize_workflow(record["workflow"], bindings)
        checked("replay", service.run_workflow(prepared["artifacts"][0]["path"], values, sid))
        for kind in registry:
            q = checked("replay-query-" + kind, service.inspect_gui_entity_sets(sid, kind, 42))
            assert q["data"]["member_ids"] == registry[kind][-3:]
        rejected(
            "stale-selection",
            lambda: service.create_gui_entity_set(
                sid, "shell", 51, "Stale", selection_job=selections["shell"]["job_directory"]
            ),
            "older model",
        )
        saved = checked("checkpoint", service.checkpoint_gui_session(sid))
        path = next(a["path"] for a in saved["artifacts"] if a["kind"] == "keyword")
        expected = inspect_cards(Path(path))
        checked("reopen", service.open_in_gui_session(sid, path))
        for kind in registry:
            q = checked("reopen-" + kind, service.inspect_gui_entity_sets(sid, kind, 42))
            assert q["data"]["member_ids"] == registry[kind][-3:]
        assert inspect_cards(Path(q["job_directory"]) / "model.k") == expected
        assert source.read_bytes() == original
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                cases=cases,
                source_unchanged=True,
                scope="4.13.4 visible Shell/Solid/Beam explicit lists,12 sparse members/domain,SID namespace,wrong/stale selection,recorded replay and native reopen; no solver/replace/Generate/Collect certification",
            ),
        )
    finally:
        atomic_json(root / "closed.json", service.close_gui_session(sid, save_checkpoint=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    accept(**vars(parser.parse_args()))
