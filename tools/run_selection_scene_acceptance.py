"""Opt-in visible selection/Blank preservation regression on standard mixed elements."""

import argparse
import uuid
from pathlib import Path

from run_gui_visibility_acceptance import mixed_fixture

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.gui_mesh import verify_mesh_digest
from ls_prepost_mcp.gui_selection import part_visibility
from ls_prepost_mcp.gui_visibility import flags
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("native-selection-scene-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    source = root / "mixed.k"
    mixed_fixture(source)
    original = source.read_bytes()
    service = Service(Settings(root, Path(executable), timeout=120))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session.json", session)
    manager = service._session_manager()
    cases = []

    def checked(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        print(name, flush=True)
        return result

    def scene():
        with manager.lock(sid):
            baseline = manager.dispatch(sid, "gui_mesh_digest", {})
            assert baseline["status"] == "succeeded"
            hidden = [pid for pid, shown in part_visibility(baseline["data"]).items() if not shown]
            try:
                shown = manager.dispatch(sid, "gui_mesh_digest", dict(visibility_readback=True),
                                         native_commands=["+m " + pid for pid in hidden])
                assert shown["status"] == "succeeded"
                display = flags(shown["data"], shown["job_directory"])
            finally:
                restored = manager.dispatch(sid, "gui_mesh_digest", {},
                                            native_commands=["-m " + pid for pid in hidden])
                assert restored["status"] == "succeeded"
            verify_mesh_digest(baseline["data"], restored["data"])
            assert part_visibility(baseline["data"]) == part_visibility(restored["data"])
            return baseline["data"], display

    def unchanged(name, call):
        before, old = scene()
        result = checked(name, call())
        after, new = scene()
        assert old == new, (old, new)
        assert before["part_visibility"] == after["part_visibility"]
        assert before["current_state"] == after["current_state"]
        verify_mesh_digest(before, after)
        if "verification" in result:
            assert result["verification"]["entity_display_active_preserved"]
        cases.append(name)

    try:
        service.show_gui_session(sid, maximize=True)
        checked("open", service.open_in_gui_session(sid, str(source), "keyword"))
        checked("hide", service.set_gui_entity_visibility(sid, "element", "hide", [1, 101, 201]))
        unchanged("nodes", lambda: service.select_gui_entities(sid, "node", [1, 2]))
        unchanged("elements", lambda: service.select_gui_entities(sid, "element", [1, 102, 201]))
        unchanged("part-nodes", lambda: service.select_gui_entities(sid, "node", part_ids=[1]))
        unchanged("box", lambda: service.select_gui_nodes_by_box(sid, [-1., -1., -1., 0.5, 2., 2.], "mm"))
        unchanged("boolean", lambda: service.combine_gui_selections(sid, "node", [1, 2], [2, 3], "intersection"))
        unchanged("buffer-save", lambda: service.save_gui_selection_buffer(sid, "node", [1, 2], 1))
        unchanged("buffer-load", lambda: service.load_gui_selection_buffer(sid, 1))
        checked("hide-part", service.set_gui_part_visibility(sid, "hide", [2]))
        unchanged("hidden-part-nodes", lambda: service.select_gui_entities(sid, "node", part_ids=[2]))
        unchanged("hidden-part-shells", lambda: service.select_gui_entities(sid, "shell", part_ids=[2]))
        service.start_session_recording(sid)
        # Recorded workflows reopen their keyword baseline; explicitly record
        # display setup because a keyword checkpoint does not store Blank flags.
        checked("recorded-hide", service.set_gui_entity_visibility(sid, "element", "hide", [1, 101, 201]))
        checked("recorded-hide-part", service.set_gui_part_visibility(sid, "hide", [2]))
        unchanged("recorded", lambda: service.select_gui_entities(sid, "node", [1, 2]))
        recording = checked("recording", service.stop_session_recording(sid))
        unchanged("replay", lambda: service.run_workflow(recording["workflow"], session_id=sid))
        assert source.read_bytes() == original
        atomic_json(root / "acceptance.json", dict(status="succeeded", cases=cases, source_unchanged=True,
                    scope="Mixed shell/solid/beam, hidden parts, explicit/part/box/boolean/buffer selection and replay; native display flags are not erosion"))
    finally:
        atomic_json(root / "closed.json", service.close_gui_session(sid, save_checkpoint=False))
    print(root, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    accept(**vars(parser.parse_args()))
