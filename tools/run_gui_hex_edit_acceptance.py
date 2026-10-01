"""Opt-in native box -> adjacent shared-face Hex8 -> geometric check -> native reopen.

This certifies scoped geometry/topology only, not material/contact/solver setup.
"""

import argparse
import json
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("native-hex-edit-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    service = Service(Settings(root, Path(executable), timeout=60))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session-start.json", session)
    service.show_gui_session(sid, maximize=True)
    box = service.gui_session_action(
        sid, "create_solid_box", dict(divisions=[1, 1, 1], size=[1, 1, 1], units="mm")
    )
    atomic_json(root / "box.json", box)
    assert box["status"] == "succeeded", box.get("error")
    service.set_gui_display(sid, view="isometric", center=True, capture=False)
    initial = service.inspect_gui_mesh(sid, include_entities=True)["data"]
    assert initial["counts"]["nodes"] == 8 and initial["counts"]["elements"] == 1
    lookup = {tuple(row[1:]): row[0] for row in initial["nodes"]}
    next_id = max(lookup.values()) + 1
    new_nodes = [
        dict(id=next_id + i, coordinates=list(xyz))
        for i, xyz in enumerate([(2, 0, 0), (2, 1, 0), (2, 0, 1), (2, 1, 1)])
    ]
    lookup.update({tuple(row["coordinates"]): row["id"] for row in new_nodes})
    conn = [
        lookup[xyz]
        for xyz in [(1, 0, 0), (2, 0, 0), (2, 1, 0), (1, 1, 0), (1, 0, 1), (2, 0, 1), (2, 1, 1), (1, 1, 1)]
    ]
    part = initial["part_ids"][0]
    eid = max(e["id"] for e in initial["elements"]) + 1
    workflow = service.create_workflow(
        "Native shared-face solid edit",
        [
            dict(id="nodes", action="create_gui_nodes", arguments=dict(nodes=new_nodes, units="mm")),
            dict(
                id="solid",
                action="create_gui_elements",
                arguments=dict(
                    element_type="solid", part_id=part, elements=[dict(id=eid, node_ids=conn)], units="mm"
                ),
            ),
            dict(id="quality", action="inspect_gui_mesh_quality", arguments=dict(units="mm")),
            dict(id="save", action="checkpoint", arguments={}),
        ],
    )
    edited = service.run_workflow(workflow["artifacts"][0]["path"], session_id=sid)
    atomic_json(root / "workflow.json", edited)
    print("native_shared_face_hex_edit", edited["status"], flush=True)
    assert edited["status"] == "succeeded", edited.get("error")
    report = edited["data"]["steps"]["quality"]["data"]
    assert report["checked_count"] == 2 and report["failed_count"] == report["unsupported_count"] == 0
    assert report["backend"] == "lsprepost-readback+geometry-math" and not report["native_model_check"]
    saved = edited["data"]["steps"]["save"]["artifacts"][0]["path"]
    assert service.open_in_gui_session(sid, saved)["status"] == "succeeded"
    after = service.inspect_gui_mesh(sid, include_entities=True)["data"]
    assert after["counts"]["nodes"] == 12 and after["counts"]["elements"] == 2
    created = next(e for e in after["elements"] if e["id"] == eid)
    assert created["nodes"] == conn
    original = next(e for e in after["elements"] if e["id"] == initial["elements"][0]["id"])
    assert original == initial["elements"][0]
    assert len(set(original["nodes"]) & set(conn)) == 4
    invalid = [conn[i] for i in [1, 0, 3, 2, 5, 4, 7, 6]]
    try:
        service.create_gui_elements(sid, "solid", part, [dict(id=eid + 1, node_ids=invalid)], "mm")
    except ValueError as exc:
        assert "inverted" in str(exc)
    else:
        raise AssertionError("Inverted Hex8 reached native import")
    final = service.inspect_gui_mesh(sid, include_entities=True)["data"]
    assert final["nodes"] == after["nodes"] and final["elements"] == after["elements"]
    atomic_json(
        root / "acceptance.json",
        dict(
            status="succeeded",
            session_id=sid,
            native_box_and_hex_import=True,
            shared_face_nodes=4,
            nodes=12,
            solids=2,
            inverted_hex_rejected_without_mutation=True,
            native_reopen_verified=True,
            quality_backend="native readback plus geometry math",
            scope="Synthetic Hex8 geometry/connectivity only; native solid Model Checking and physics not certified",
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
