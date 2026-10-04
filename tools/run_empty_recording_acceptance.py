"""Visible zero-entity keyword baseline retains cards across parameter replay."""

import argparse
import json
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.entity_cards import native_blocks
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("er-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    source = root / "material-only.k"
    source.write_text(
        "*KEYWORD\n*TITLE\nZero entity recording baseline\n*MAT_ELASTIC\n777,1.0,1000.0,0.3\n*END\n",
        encoding="ascii",
    )
    original = source.read_bytes()
    service = Service(Settings(root, Path(executable), timeout=60))
    meta = service.start_gui_session()
    sid = meta["session_id"]
    atomic_json(root / "session.json", meta)
    cases = []
    print(root, flush=True)

    def checked(name, r):
        atomic_json(root / (name + ".json"), r)
        assert r["status"] == "succeeded", r.get("error")
        print(name, flush=True)
        cases.append(name)
        return r

    try:
        service.show_gui_session(sid, maximize=True)
        opened = checked(
            "material-only-open", service.open_in_gui_session(sid, str(source), expected_empty=True)
        )
        assert opened["model_context"]["empty_model_verified"]
        start = service.start_session_recording(sid)
        atomic_json(root / "start.json", start)
        assert start["recording"]["initial_expected_empty"]
        baseline = Path(start["recording"]["initial_model"])
        assert baseline.is_file() and "*MAT_" in baseline.read_text()
        nodes = [dict(id=101, coordinates=[0.0, 0.0, 0.0]), dict(id=103, coordinates=[1.0, 0.0, 0.0])]
        checked("create", service.create_gui_nodes(sid, nodes, "mm"))
        recording = checked("record", service.stop_session_recording(sid))
        w = json.loads(Path(recording["workflow"]).read_text(encoding="utf8"))
        assert w["initial_expected_empty"] is True and len(w["steps"]) == 1
        checked(
            "distractor", service.create_gui_nodes(sid, [dict(id=999, coordinates=[9.0, 9.0, 9.0])], "mm")
        )
        p = service.parameterize_workflow(
            recording["workflow"], [dict(step_id="step1", path=["nodes"], parameter="nodes")]
        )
        pw = json.loads(Path(p["artifacts"][0]["path"]).read_text(encoding="utf8"))
        assert pw["initial_expected_empty"]
        replacement = [dict(id=201, coordinates=[0.0, 0.0, 0.0]), dict(id=205, coordinates=[3.0, 2.0, 1.0])]
        checked("replay", service.run_workflow(p["artifacts"][0]["path"], dict(nodes=replacement), sid))
        result = checked("mesh", service.inspect_gui_mesh(sid, include_entities=True))
        assert result["data"]["nodes"] == [[201, 0.0, 0.0, 0.0], [205, 3.0, 2.0, 1.0]]
        saved = checked("checkpoint", service.checkpoint_gui_session(sid))
        final = Path(next(a["path"] for a in saved["artifacts"] if a["kind"] == "keyword"))
        def materials(path):
            return {(n, h) for n, h, _ in native_blocks(path) if n.startswith("*MAT_")}
        assert materials(baseline) and materials(baseline) == materials(final)
        assert source.read_bytes() == original
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                cases=cases,
                source_unchanged=True,
                material_cards_preserved=True,
                final_node_ids=[201, 205],
                scope="4.13.4 active zero-node/element keyword baseline restored with material card preserved; changed-node replay drops prior/distractor nodes in active model. Does not certify unloading other resident model entries.",
            ),
        )
    finally:
        atomic_json(root / "closed.json", service.close_gui_session(sid, save_checkpoint=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True)
    p.add_argument("--executable", required=True)
    accept(**vars(p.parse_args()))
