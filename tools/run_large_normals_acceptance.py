"""Native100,000-shell all/partial normal reversal, full preservation and reopen proof."""

import argparse
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.gui_mesh import verify_mesh_digest
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("native-large-normals-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    s = Service(Settings(root, Path(executable), timeout=240))
    session = s.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session.json", session)

    def checked(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        return result

    try:
        s.show_gui_session(sid, maximize=True)
        checked("created", s.gui_session_action(sid, "create_shell_plate", dict(nx=400, ny=250, size=[400., 250.], units="mm")))
        checked("display", s.set_gui_display(sid, view="isometric", center=True, capture=True))
        def coordinates():
            result, offset = {}, 0
            while offset is not None:
                page = s.inspect_gui_mesh(sid, entity_type="node", offset=offset, limit=5000)
                assert page["status"] == "succeeded", page.get("error")
                for row in page["data"]["nodes"]:
                    assert row[0] not in result
                    result[row[0]] = row[1:]
                offset = page["data"]["next_offset"]
            return result
        generated = coordinates()
        baseline_file = checked("initial-save", s.checkpoint_gui_session(sid))
        checked("initial-reopen", s.open_in_gui_session(sid, baseline_file["artifacts"][0]["path"], "keyword"))
        normalized = coordinates()
        assert generated.keys() == normalized.keys()
        maximum_delta = max(abs(a - b) for uid in generated for a, b in zip(generated[uid], normalized[uid], strict=True))
        atomic_json(root / "initial-serialization.json", dict(maximum_coordinate_delta_mm=maximum_delta,
                    tolerance_mm=1e-4, nodes_checked=len(generated), operation="native-generated mesh to first keyword representation"))
        assert maximum_delta <= 1e-4, "Initial native save precision exceeds the declared synthetic-fixture tolerance"
        manager = s._session_manager()
        def digest():
            with manager.lock(sid):
                return manager.dispatch(sid, "gui_mesh_digest", {})
        original = checked("original", digest())
        first = checked("all-reversed", s.reverse_gui_shell_normals(sid, "mm"))
        assert first["verification"]["reversed_shells"] == 100000
        checked("all-restored", s.reverse_gui_shell_normals(sid, "mm"))
        restored = checked("restored", digest())
        verify_mesh_digest(original["data"], restored["data"])
        page = checked("sample", s.inspect_gui_mesh(sid, entity_type="shell", limit=3))
        shell_ids = [row["id"] for row in page["data"]["elements"]]
        checked("hidden", s.set_gui_part_visibility(sid, "hide", [1]))
        partial = checked("partial-reversed", s.reverse_gui_shell_normals(sid, "mm", shell_ids))
        assert partial["verification"]["reversed_shells"] == 3
        assert partial["data"]["part_visibility"] == {"1": False}
        after = checked("after-partial", digest())
        saved = checked("checkpoint", s.checkpoint_gui_session(sid))
        checked("reopen", s.open_in_gui_session(sid, saved["artifacts"][0]["path"], "keyword"))
        reopened = checked("reopened-digest", digest())
        verify_mesh_digest(after["data"], reopened["data"])
        checked("shown", s.set_gui_part_visibility(sid, "all"))
        checked("image", s.set_gui_display(sid, view="isometric", center=True, capture=True))
        atomic_json(root / "acceptance.json", dict(status="succeeded", shells=100000,
                    full_reverse_twice_restored=True, partial_reverse_preserved_others=True,
                    hidden_part_preserved=True, native_save_reopen=True))
    finally:
        atomic_json(root / "closed.json", s.close_gui_session(sid, save_checkpoint=False))
    print(str(root), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    accept(**vars(parser.parse_args()))
