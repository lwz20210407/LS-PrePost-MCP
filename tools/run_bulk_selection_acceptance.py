"""Visible large native part/visibility selections with shared-node truth sets."""

import argparse
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.deck_backend import api
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.model_deck import load_standalone, table
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("native-bulk-selection-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    s = Service(Settings(root, Path(executable), timeout=240))
    session = s.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session.json", session)
    results = []
    try:
        s.show_gui_session(sid, maximize=True)
        made = s.gui_session_action(sid, "create_shell_plate", dict(nx=400, ny=250, size=[400., 250.], units="mm"))
        assert made["status"] == "succeeded", made.get("error")
        checkpoint = s.checkpoint_gui_session(sid)
        assert checkpoint["status"] == "succeeded"
        _, kw = api()
        deck = load_standalone(Path(checkpoint["artifacts"][0]["path"]))
        all_nodes = {int(row.nid) for row in table(deck, kw.Node, "nodes").itertuples()}
        conn = {int(row.eid): {int(getattr(row, "n%d" % n)) for n in range(1, 5)}
                for row in table(deck, kw.ElementShell, "elements").itertuples()}
        moved = set(sorted(conn)[:250])
        reassigned = s.gui_session_action(sid, "move_elements_to_part", dict(
            element_ids=sorted(moved), element_type="shell", part_id=2))
        atomic_json(root / "reassigned.json", reassigned)
        assert reassigned["status"] == "succeeded", reassigned.get("error")
        part1 = set().union(*(ns for eid, ns in conn.items() if eid not in moved))
        part2 = set().union(*(conn[eid] for eid in moved))
        assert part1 & part2 and part1 - part2 and part2 - part1
        flags = {"1": False, "2": True}
        assert s.set_gui_part_visibility(sid, "isolate", [2])["status"] == "succeeded"
        assert s.set_gui_display(sid, view="top", center=True, capture=False)["status"] == "succeeded"

        def check(name, result, expected):
            atomic_json(root / (name + ".json"), result)
            assert result["status"] == "succeeded", result.get("error")
            assert result["verification"]["selected_ids"] == sorted(expected)
            assert result["verification"]["part_visibility_preserved"]
            assert result["data"]["part_visibility"] == flags
            results.append(dict(name=name, selected=len(expected), strategy=result["verification"]["command_strategy"]))

        check("whole-nodes", s.select_gui_entities(sid, "node"), all_nodes)
        check("hidden-large-shell-part", s.select_gui_entities(sid, "shell", part_ids=[1]), set(conn) - moved)
        check("hidden-large-node-part", s.select_gui_entities(sid, "node", part_ids=[1]), part1)
        check("active-nodes", s.select_gui_entities(sid, "node", scope="active_parts"), part2)
        check("shared-hidden-active", s.select_gui_entities(sid, "node", part_ids=[1], scope="active_parts"), part1 & part2)
        check("inverted-within-active", s.select_gui_entities(sid, "node", part_ids=[1], scope="active_parts", invert=True), part2 - part1)
        hidden_node = min(part1 - part2)
        check("explicit-hidden-filtered", s.select_gui_entities(sid, "node", [hidden_node], scope="active_parts"), set())
        assert s.set_gui_part_visibility(sid, "hide", [2])["status"] == "succeeded"
        flags = {"1": False, "2": False}
        check("empty-active", s.select_gui_entities(sid, "node", scope="active_parts"), set())
        atomic_json(root / "acceptance.json", dict(status="succeeded", cases=results,
                    scope="Native100000shells, full-domain selections plus hidden/shared-node semantics; exported NODE/ELEMENT oracle"))
    finally:
        atomic_json(root / "closed.json", s.close_gui_session(sid, save_checkpoint=False))
    print(str(root), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    accept(**vars(parser.parse_args()))
