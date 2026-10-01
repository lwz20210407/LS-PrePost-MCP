"""Opt-in private non-eroding solid result: bulk selection to named native field."""

import argparse
import csv
import re
import uuid
from pathlib import Path

from run_result_selection_acceptance import hashes

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable, source):
    source = Path(source).resolve(strict=True)
    family = [source] + sorted(p for p in source.parent.iterdir()
                               if p.is_file() and re.fullmatch(re.escape(source.name) + r"\d+", p.name))
    identities = hashes(family)
    root = Path(workspace).resolve() / ("native-result-bulk-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    s = Service(Settings(root, Path(executable), allowed_roots=(source.parent,), timeout=240))
    session = s.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session.json", session)
    summary = dict(status="failed")

    def save(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        return result

    try:
        s.show_gui_session(sid, maximize=True)
        opened = save("opened", s.open_in_gui_session(sid, str(source), "d3plot"))
        counts = opened["data"]["counts"]
        assert counts["elements"] > 20000
        page = save("solid-page", s.inspect_gui_mesh(sid, entity_type="solid", limit=3))
        assert page["data"]["total"] == counts["elements"], "Use a solid-only fixture"
        save("late-state", s.set_gui_display(sid, state=counts["states"], view="isometric", center=True, capture=False))
        whole = save("all-solids", s.select_gui_entities(sid, "solid"))
        assert whole["verification"]["selected_count"] == counts["elements"]
        assert whole["verification"]["native_current_state"] == counts["states"]
        assert {row["id"] for row in page["data"]["elements"]} <= set(whole["verification"]["selected_ids"])
        all_nodes = save("all-nodes", s.select_gui_entities(sid, "node"))
        assert all_nodes["verification"]["selected_count"] == counts["nodes"]
        pid = opened["data"]["part_ids"][0]
        save("hide-part", s.set_gui_part_visibility(sid, "hide", [pid]))
        selected = save("hidden-part", s.select_gui_entities(sid, "solid", part_ids=[pid]))
        assert selected["data"]["part_visibility"][str(pid)] is False
        assert selected["verification"]["native_current_state"] == counts["states"]
        save("show-part", s.set_gui_part_visibility(sid, "show", [pid]))
        field = save("native-field", s.render_gui_field(sid, "solid", "von_mises", counts["states"], "model_stress", part_ids=[pid]))
        with Path(field["artifacts"][1]["path"]).open(newline="") as stream:
            exported = {int(row["entity_id"]) for row in csv.DictReader(stream)}
        assert exported == set(selected["verification"]["selected_ids"])
        summary.update(status="succeeded", counts=counts, selected_field_ids_match=True,
                       state_preserved_by_selection=True, hidden_part_preserved_by_selection=True)
    finally:
        summary["source_unchanged"] = identities == hashes(family)
        atomic_json(root / "acceptance.json", summary)
        atomic_json(root / "closed.json", s.close_gui_session(sid, save_checkpoint=False))
    assert summary["source_unchanged"]
    print(str(root), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "executable", "source"):
        parser.add_argument("--" + name, required=True)
    accept(**vars(parser.parse_args()))
