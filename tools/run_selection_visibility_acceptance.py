"""Opt-in visible native selection/display contract on a synthetic two-part mesh."""

import argparse
import json
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service

MODEL = """*KEYWORD
*TITLE
Synthetic selection visibility acceptance
*NODE
1,0,0,0
2,1,0,0
3,1,1,0
4,0,1,0
5,2,0,0
6,2,1,0
7,4,4,0
*ELEMENT_SHELL
100,10,1,2,3,4
200,20,2,5,6,3
*PART
Visible test part
10,1,1
*PART
Hidden test part
20,1,1
*SECTION_SHELL
1,2,0.833333,3
1,1,1,1
*MAT_ELASTIC
1,1,100,0.3
*END
"""


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("selection-visibility-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    source = root / "synthetic.k"
    source.write_text(MODEL, encoding="ascii")
    service = Service(Settings(root, Path(executable), timeout=45))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session-start.json", session)
    service.show_gui_session(sid, maximize=True)
    assert service.open_in_gui_session(sid, str(source))["status"] == "succeeded"
    assert service.set_gui_display(sid, view="top", center=True, capture=False)["status"] == "succeeded"
    assert service.set_gui_part_visibility(sid, "isolate", [10])["status"] == "succeeded"
    expected_flags = {"10": True, "20": False}
    results = {}

    def check(name, operation, expected):
        value = operation()
        results[name] = value
        atomic_json(root / "results.json", results)
        print(name, value["status"], flush=True)
        assert value["status"] == "succeeded", value
        assert value["verification"]["selected_ids"] == sorted(expected)
        assert value["verification"]["part_visibility_preserved"]
        snapshot = service.inspect_gui_mesh(sid)
        assert snapshot["data"]["part_visibility"] == expected_flags

    check("all_includes_hidden_and_orphan", lambda: service.select_gui_entities(sid, "node"), range(1, 8))
    check(
        "active_parts_shared_nodes",
        lambda: service.select_gui_entities(sid, "node", scope="active_parts"),
        [1, 2, 3, 4],
    )
    check(
        "inverse_within_active_parts",
        lambda: service.select_gui_entities(sid, "node", [1], invert=True, scope="active_parts"),
        [2, 3, 4],
    )
    check(
        "hidden_ids_filtered", lambda: service.select_gui_entities(sid, "node", [5], scope="active_parts"), []
    )
    check("hidden_part_explicit", lambda: service.select_gui_entities(sid, "shell", part_ids=[20]), [200])
    check("hidden_buffer_save", lambda: service.save_gui_selection_buffer(sid, "node", [5], 1), [5])
    check("hidden_buffer_clear", lambda: service.select_gui_entities(sid, "node", []), [])
    check("hidden_buffer_load", lambda: service.load_gui_selection_buffer(sid, 1), [5])
    assert service.set_gui_part_visibility(sid, "hide", [10])["status"] == "succeeded"
    expected_flags = {"10": False, "20": False}
    check("all_parts_hidden", lambda: service.select_gui_entities(sid, "part", scope="active_parts"), [])
    assert source.read_text(encoding="ascii") == MODEL
    summary = dict(
        status="succeeded",
        cases=list(results),
        session_id=sid,
        scope="Synthetic keyword model; native part flags, not per-element screen visibility",
    )
    atomic_json(root / "acceptance.json", summary)
    print(json.dumps(dict(status="succeeded", evidence_directory=str(root), cases=list(results))), flush=True)
    service.close_gui_session(sid, save_checkpoint=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    args = parser.parse_args()
    accept(args.workspace, args.executable)
