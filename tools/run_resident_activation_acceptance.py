"""Opt-in visible resident A/B edits, source identity and optional result switching."""

import argparse
import hashlib
import uuid
from pathlib import Path

from run_element_set_acceptance import fixture

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def accept(workspace, executable, d3plot=None):
    root = Path(workspace).resolve() / ("ra-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    a, b = root / "a.k", root / "b.k"
    fixture(a)
    fixture(b)
    b.write_text(b.read_text().replace("Element set acceptance fixture", "Resident B"))
    originals = {p: sha(p) for p in (a, b)}
    if d3plot:
        plot = Path(d3plot).resolve()
        originals.update({p: sha(p) for p in plot.parent.glob(plot.name + "*") if p.is_file()})
    s = Service(Settings(root, Path(executable), allowed_roots=(plot.parent,) if d3plot else (), timeout=60))
    meta = s.start_gui_session()
    sid = meta["session_id"]
    atomic_json(root / "session.json", meta)
    s.show_gui_session(sid, maximize=True)
    cases = []
    print(root, flush=True)

    def checked(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        cases.append(name)
        print(name, flush=True)
        return result

    def rejected(name, call):
        try:
            call()
        except ValueError as e:
            atomic_json(root / (name + ".json"), dict(status="expected_rejection", message=str(e)))
            cases.append(name)
        else:
            raise AssertionError("Expected rejection: " + name)

    def assert_node(name, present, absent):
        result = checked(name, s.inspect_gui_mesh(sid, include_entities=True))
        nodes = {n[0]: n[1:] for n in result["data"]["nodes"]}
        assert nodes[present] == [float(present), 2.0, 3.0] and absent not in nodes

    try:
        checked("open-a", s.open_in_gui_session(sid, str(a)))
        source_a = s.inspect_gui_session(sid)["staged_model"]
        checked("open-b", s.open_in_gui_session(sid, str(b)))
        source_b = s.inspect_gui_session(sid)["staged_model"]
        checked("activate-a", s.activate_gui_model(sid, source_a))
        checked("edit-a", s.create_gui_nodes(sid, [dict(id=301, coordinates=[301, 2, 3])], "mm"))
        checked("buffer-a", s.save_gui_selection_buffer(sid, "node", [301], 1))
        generation = s.inspect_gui_session(sid)["model_generation"]
        checked("activate-b-preserve-a", s.activate_gui_model(sid, source_b))
        assert s.inspect_gui_session(sid)["model_generation"] != generation
        assert not s.inspect_gui_session(sid)["selection_buffers"]
        rejected("reject-old-buffer", lambda: s.load_gui_selection_buffer(sid, 1))
        checked("edit-b", s.create_gui_nodes(sid, [dict(id=401, coordinates=[401, 2, 3])], "mm"))
        checked("return-a-preserve-b", s.activate_gui_model(sid, source_a))
        assert_node("a-memory-retained", 301, 401)
        checked("return-b", s.activate_gui_model(sid, source_b))
        assert_node("b-memory-retained", 401, 301)
        same = checked("same-source-noop", s.activate_gui_model(sid, source_b))
        assert same["already_active"]
        rejected("reject-unmanaged-source", lambda: s.activate_gui_model(sid, str(a)))
        atomic_json(root / "recording-start.json", s.start_session_recording(sid))
        rejected("reject-nonportable-recording", lambda: s.activate_gui_model(sid, source_a))
        atomic_json(root / "recording-stop.json", s.stop_session_recording(sid))
        if d3plot:
            checked("open-result", s.open_in_gui_session(sid, str(plot), "d3plot"))
            result_inventory = s.inspect_gui_session(sid, include_models=True)
            atomic_json(root / "post-result-inventory.json", result_inventory)
            source_plot = s.inspect_gui_session(sid)["staged_model"]
            # The native path now reflects A's latest saved checkpoint, not
            # its original staged input. Public activation must resolve either.
            native_a_path = result_inventory["native_models"]["models"][1]["path"]
            checked("result-to-resident-a-by-saved-path", s.activate_gui_model(sid, native_a_path))
            assert_node("a-after-result-switch", 301, 401)
            checked("resident-a-to-result", s.activate_gui_model(sid, source_plot))
            assert s.inspect_gui_session(sid)["model_kind"] == "d3plot"
            assert s.inspect_gui_session(sid)["last_checkpoint"] is None
            checked("result-to-resident-b", s.activate_gui_model(sid, source_b))
            assert_node("b-after-result-switch", 401, 301)
        final = s.inspect_gui_session(sid, include_models=True)
        atomic_json(root / "final-inventory.json", final)
        assert all(sha(p) == digest for p, digest in originals.items())
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                cases=cases,
                model_count=len(final["native_models"]["models"]),
                sources_unchanged=True,
                result_switch_tested=bool(d3plot),
                scope="Visible4.13.4 owned resident activation, independent A/B edited memory and source/type/checkpoint/cache alignment. No unload/replace/scene replay or full resident crash recovery.",
            ),
        )
    finally:
        atomic_json(root / "closed.json", s.close_gui_session(sid, save_checkpoint=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--d3plot")
    accept(**vars(parser.parse_args()))
