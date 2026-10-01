"""Visible native selection/coordinate edits with complete streamed verification.

Default fixture: native100,000shell plate. Optional --source tests a private deck.
All inputs are staged; no solver runs and no outputs belong in the public repo.
"""

import argparse
import math
import time
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.gui_mesh import verify_mesh_digest
from ls_prepost_mcp.jobs import atomic_json, fingerprint
from ls_prepost_mcp.service import Service


def accept(workspace, executable, source=None):
    source = Path(source).resolve(strict=True) if source else None
    identity = fingerprint(source) if source else None
    root = Path(workspace).resolve() / ("native-scoped-mesh-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    service = Service(Settings(root, Path(executable), allowed_roots=(source.parent,) if source else (), timeout=240))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session.json", session)
    started = time.monotonic()
    summary = dict(status="failed")

    def save(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        return result

    try:
        service.show_gui_session(sid, maximize=True)
        if source:
            save("opened", service.open_in_gui_session(sid, str(source), "keyword"))
        else:
            save("created", service.gui_session_action(sid, "create_shell_plate", dict(
                nx=400, ny=250, size=[400., 250.], units="mm")))
        # Normalize to native save precision before testing a later save/reopen.
        checkpoint = save("normalized", service.checkpoint_gui_session(sid))
        save("normalized-reopen", service.open_in_gui_session(sid, checkpoint["artifacts"][0]["path"], "keyword"))
        page = save("nodes", service.inspect_gui_mesh(sid, entity_type="node", limit=3))
        nodes = page["data"]["nodes"]
        uids = [row[0] for row in nodes]
        manager = service._session_manager()

        def digest():
            with manager.lock(sid):
                return manager.dispatch(sid, "gui_mesh_digest", dict(node_ids=uids))

        before = save("before", digest())
        assert max(before["data"]["counts"][k] for k in ("nodes", "elements")) >= 100000
        chosen = save("selection", service.select_gui_entities(sid, "node", uids))
        assert chosen["verification"]["selected_ids"] == sorted(uids)
        for domain in ("shell", "solid"):
            sample = save(domain + "-page", service.inspect_gui_mesh(sid, entity_type=domain, limit=3))
            eids = [row["id"] for row in sample["data"]["elements"]]
            if eids:
                picked = save(domain + "-selection", service.select_gui_entities(sid, domain, eids))
                assert picked["verification"]["selected_ids"] == sorted(eids)
        pids = before["data"]["part_ids"][:1]
        save("part-selection", service.select_gui_entities(sid, "part", pids))
        combined = save("combined", service.combine_gui_selections(sid, "node", uids[:2], uids[1:], "intersection"))
        assert combined["verification"]["selected_ids"] == uids[1:2]
        save("buffer-save", service.save_gui_selection_buffer(sid, "node", uids, 1))
        save("selection-clear", service.select_gui_entities(sid, "node", []))
        loaded = save("buffer-load", service.load_gui_selection_buffer(sid, 1))
        assert loaded["verification"]["selected_ids"] == sorted(uids)
        save("translate", service.translate_gui_nodes(sid, uids, [0., 0., 0.001], "model_length"))
        try:
            service.load_gui_selection_buffer(sid, 1)
        except ValueError as exc:
            assert "stale" in str(exc)
            atomic_json(root / "stale-buffer-rejection.json", dict(rejected=True, message=str(exc)))
        else:
            raise AssertionError("Changed mesh must invalidate the saved buffer identity")
        save("rotate", service.rotate_gui_nodes(sid, uids, "z", 0.01, [0., 0., 0.], "model_length"))
        targets = [dict(id=row[0], coordinates=[row[1], row[2], row[3] + 0.002]) for row in nodes]
        save("absolute", service.set_gui_node_coordinates(sid, targets, "model_length", tolerance=1e-6))
        after = save("after", digest())
        verify_mesh_digest(before["data"], after["data"], allow_selected_coordinates=True)
        saved = save("saved", service.checkpoint_gui_session(sid))
        save("reopened", service.open_in_gui_session(sid, saved["artifacts"][0]["path"], "keyword"))
        reopened = save("reopened-digest", digest())
        verify_mesh_digest(before["data"], reopened["data"], allow_selected_coordinates=True)
        actual = {row[0]: row[1:] for row in reopened["data"]["nodes"]}
        for row in targets:
            assert all(math.isclose(a, b, rel_tol=0, abs_tol=1e-6)
                       for a, b in zip(actual[row["id"]], row["coordinates"], strict=True))
        summary.update(status="succeeded", counts=before["data"]["counts"],
                       selected_nodes=len(uids), all_unselected_coordinates_verified=True,
                       all_topology_verified=True, native_save_reopen=True,
                       elapsed_seconds=time.monotonic() - started)
    finally:
        summary["source_unchanged"] = identity == fingerprint(source) if source else None
        atomic_json(root / "acceptance.json", summary)
        atomic_json(root / "closed.json", service.close_gui_session(sid, save_checkpoint=False))
    assert source is None or summary["source_unchanged"]
    print(str(root), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "executable"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--source")
    accept(**vars(parser.parse_args()))
