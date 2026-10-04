"""Visible reset separates prior undo checkpoint from current restart baseline."""

import argparse
import uuid
from pathlib import Path

from run_element_set_acceptance import fixture

from ls_prepost_mcp.checkpoint_context import restart_source
from ls_prepost_mcp.config import Settings, command_path
from ls_prepost_mcp.entity_cards import native_blocks
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def materials(path):
    return [(name, digest) for name, digest, _ in native_blocks(Path(path)) if name.startswith("*MAT_")]


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("rr-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    model = root / "model.k"
    fixture(model)
    material = root / "material-only.k"
    material.write_text("*KEYWORD\n*MAT_ELASTIC\n777,1,1000,0.3\n*END\n")
    addition = root / "additional-material.k"
    addition.write_text("*KEYWORD\n*MAT_ELASTIC\n778,2,2000,0.25\n*END\n")
    originals = {p: p.read_bytes() for p in (model, material, addition)}
    service = Service(Settings(root, Path(executable), timeout=60))
    sessions = []
    cases = []
    print(root, flush=True)

    def checked(name, r):
        atomic_json(root / (name + ".json"), r)
        assert r["status"] == "succeeded", r.get("error")
        cases.append(name)
        print(name, flush=True)
        return r

    try:
        first = service.start_gui_session()
        sid = first["session_id"]
        sessions.append(sid)
        atomic_json(root / "first.json", first)
        service.show_gui_session(sid, maximize=True)
        checked("open-mesh", service.open_in_gui_session(sid, str(model)))
        reset = checked("reset-mesh", service.reset_gui_session(sid))
        meta = service.inspect_gui_session(sid)
        assert meta["last_checkpoint"] == reset["rollback_checkpoint"]
        assert restart_source(meta) == reset["restart_baseline"] != reset["rollback_checkpoint"]
        service.close_gui_session(sid, save_checkpoint=False)
        child = checked("restart-reset", service.restart_gui_session(sid))
        sid = child["session_id"]
        sessions.append(sid)
        assert child["restoration"]["model_context"]["empty_model_verified"]
        assert child["restoration"]["data"]["counts"]["nodes"] == 0
        checked("open-material-only", service.open_in_gui_session(sid, str(material), expected_empty=True))
        original_checkpoint = service.inspect_gui_session(sid)["last_checkpoint"]
        # Controlled native fixture setup, not a claim that the high-level raw
        # program API supports every empty-model import/context transition.
        manager = service._session_manager()
        with manager.lock(sid):
            checked(
                "native-material-import",
                manager.dispatch(
                    sid, "inspect_model", {}, native_commands=["import keyword " + command_path(addition)]
                ),
            )
        observed = checked("material-before-reset", service.inspect_gui_entity_sets(sid, "node"))
        expected = materials(Path(observed["job_directory"]) / "model.k")
        assert expected and service.inspect_gui_session(sid)["last_checkpoint"] == original_checkpoint
        reset = checked("reset-material-only", service.reset_gui_session(sid))
        assert reset["rollback_checkpoint"] != original_checkpoint
        assert materials(reset["rollback_checkpoint"]) == expected
        checked("restore-material-only", service.restore_gui_checkpoint(sid))
        restored = checked("material-restored", service.inspect_gui_entity_sets(sid, "node"))
        assert materials(Path(restored["job_directory"]) / "model.k") == expected
        reset = checked("reset-before-new-save", service.reset_gui_session(sid))
        checked("new-node", service.create_gui_nodes(sid, [dict(id=301, coordinates=[1.0, 2.0, 3.0])], "mm"))
        meta = service.inspect_gui_session(sid)
        assert restart_source(meta) == meta["last_checkpoint"] != reset["restart_baseline"]
        service.close_gui_session(sid, save_checkpoint=False)
        child = checked("restart-new-checkpoint", service.restart_gui_session(sid))
        sid = child["session_id"]
        sessions.append(sid)
        mesh = checked("new-node-recovered", service.inspect_gui_mesh(sid, include_entities=True))
        assert mesh["data"]["nodes"] == [[301, 1.0, 2.0, 3.0]]
        assert all(p.read_bytes() == raw for p, raw in originals.items())
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                cases=cases,
                source_unchanged=True,
                material_blocks_preserved=len(expected),
                scope="4.13.4 visible active-model reset: prior mesh not restored on restart,material-only checkpoint saved and explicitly restored,newer checkpoint supersedes empty baseline. Clean owned-process exits;not full resident-model unload/in-flight crash certification.",
            ),
        )
    finally:
        for sid in sessions:
            if service.inspect_gui_session(sid)["process_alive"]:
                atomic_json(
                    root / ("closed-" + sid + ".json"), service.close_gui_session(sid, save_checkpoint=False)
                )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True)
    p.add_argument("--executable", required=True)
    accept(**vars(p.parse_args()))
