"""Opt-in visible result selection on staged copies. All source/derived evidence stays in --workspace."""

import argparse
import hashlib
import json
import re
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def hashes(files):
    values = {}
    for path in files:
        with path.open("rb") as stream:
            values[str(path)] = hashlib.file_digest(stream, "sha256").hexdigest()
    return values


def accept(workspace, executable, source):
    source = Path(source).resolve(strict=True)
    family = [source] + sorted(
        p
        for p in source.parent.iterdir()
        if p.is_file() and re.fullmatch(re.escape(source.name) + r"\d+", p.name)
    )
    if sum(p.stat().st_size for p in family) > 4 * 1024**3:
        raise ValueError("Acceptance fixture exceeds staging budget")
    before_hashes = hashes(family)
    root = Path(workspace).resolve() / ("result-selection-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    atomic_json(root / "source-identities.json", before_hashes)
    service = Service(Settings(root, Path(executable), allowed_roots=(source.parent,), timeout=60))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session-start.json", session)
    service.show_gui_session(sid, maximize=True)
    opened = service.open_in_gui_session(sid, str(source), "d3plot")
    assert opened["status"] == "succeeded", opened
    service.set_gui_display(sid, view="isometric", display_mode="shaded", center=True, state=1, capture=False)
    initial = service.inspect_gui_mesh(sid, include_entities=True)
    assert initial["status"] == "succeeded", initial
    node_ids = [row[0] for row in initial["data"]["nodes"][:2]]
    part_ids = [int(pid) for pid, members in initial["data"]["part_elements"].items() if members][:1]
    assert part_ids, "No native part membership found for nonempty result mesh"
    first_element = initial["data"]["elements"][0]
    results = {}

    def check(name, value):
        results[name] = value
        atomic_json(root / "results.json", results)
        print(name, value["status"], flush=True)
        assert value["status"] == "succeeded", value
        assert value["verification"]["model_kind"] == "d3plot"
        assert not value["checkpoint_created"]

    check("node_ids", service.select_gui_entities(sid, "node", node_ids))
    check("element_id", service.select_gui_entities(sid, first_element["type"], [first_element["id"]]))
    check("part_id", service.select_gui_entities(sid, "part", part_ids))
    check("part_connected_nodes", service.select_gui_entities(sid, "node", part_ids=part_ids))
    assert results["part_connected_nodes"]["verification"]["selected_count"] > 0
    check("save_buffer", service.save_gui_selection_buffer(sid, "node", node_ids, 1))
    check("clear", service.select_gui_entities(sid, "node", []))
    if initial["data"]["counts"]["states"] > 1:
        changed = service.set_gui_display(sid, state=2, capture=False)
        assert changed["status"] == "succeeded"
        reference = service.inspect_gui_mesh(sid, include_entities=True)
        assert reference["data"]["nodes"] == initial["data"]["nodes"], (
            "Reference-coordinate claim failed after changing state"
        )
    check("load_buffer_after_state", service.load_gui_selection_buffer(sid, 1))
    point = initial["data"]["nodes"][0][1:]
    radius = max(1.0, max(abs(v) for v in point)) * 1e-6
    check("reference_sphere", service.select_gui_nodes_by_sphere(sid, point, radius, "original model units"))
    assert node_ids[0] in results["reference_sphere"]["verification"]["selected_ids"]
    try:
        service.translate_gui_nodes(sid, node_ids, [1, 0, 0], "original model units")
    except ValueError as exc:
        assert "keyword" in str(exc)
    else:
        raise AssertionError("Result model unexpectedly accepted keyword editing")
    assert hashes(family) == before_hashes, "Original result family changed"
    assert not list((Path(session["directory"]) / "requests").rglob("model.k"))
    summary = dict(
        status="succeeded",
        mode="visible_native_result_selection",
        source_files_unchanged=True,
        keyword_edit_rejected=True,
        keyword_exports=0,
        cases=list(results),
        session_id=sid,
        scope="Representative result fixture, reference coordinates/registered entities; not deformed spatial selection or alive-only filtering",
    )
    atomic_json(root / "acceptance.json", summary)
    atomic_json(root / "source-identities.json", before_hashes)
    print(
        json.dumps(
            dict(status=summary["status"], evidence_directory=str(root), cases=summary["cases"]), indent=2
        ),
        flush=True,
    )
    service.close_gui_session(sid, save_checkpoint=False)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    accept(args.workspace, args.executable, args.source)
