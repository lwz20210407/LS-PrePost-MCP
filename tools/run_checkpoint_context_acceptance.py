"""Opt-in controlled exits of owned GUI test processes, then saved-model recovery."""

import argparse
import uuid
from pathlib import Path

import psutil

from ls_prepost_mcp.checkpoint_context import checkpoint_expected_empty
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.entity_cards import native_blocks
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.sessions import alive, process_identity


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("cr-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    source = root / "baseline.k"
    source.write_text("*KEYWORD\n*TITLE\nCheckpoint recovery fixture\n*MAT_ELASTIC\n777,1,1000,0.3\n*END\n")
    originals = {source: source.read_bytes()}
    service = Service(Settings(root, Path(executable), timeout=60))
    sessions = []
    cases = []
    print(root, flush=True)

    def checked(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        cases.append(name)
        print(name, flush=True)
        return result

    def terminate_owned(sid):
        meta = service.inspect_gui_session(sid)
        assert meta["process_alive"] and not meta.get("active_request")
        identity = meta["process"]
        assert process_identity(identity["pid"]) == identity
        psutil.Process(identity["pid"]).terminate()
        psutil.Process(identity["pid"]).wait(10)
        assert not alive(identity)
        atomic_json(
            root / ("exit-" + sid + ".json"),
            dict(process=identity, owned_idle_process=True, confirmed_exited=True),
        )

    try:
        first = service.start_gui_session()
        sid = first["session_id"]
        sessions.append(sid)
        atomic_json(root / "first.json", first)
        service.show_gui_session(sid, maximize=True)
        checked("open-zero", service.open_in_gui_session(sid, str(source), expected_empty=True))
        saved = checked("save-zero", service.checkpoint_gui_session(sid))
        saved_path = next(a["path"] for a in saved["artifacts"] if a["kind"] == "keyword")
        assert checkpoint_expected_empty(saved_path, sid)
        program = service.prepare_native_program(
            "cfile",
            code='meshing boxsolid create 0 0 0 1 1 1 1 1 1 0\nmeshing boxsolid accept 1 1 1 boxsolid\n',
            expected_counts=dict(nodes=8, elements=1),
        )
        checked(
            "unsaved-mesh",
            service.execute_native_program(program["job_id"], program["data"]["sha256"], session_id=sid),
        )
        meta = service.inspect_gui_session(sid)
        assert meta["dirty"] and meta["last_checkpoint"] == saved_path
        terminate_owned(sid)
        restarted = checked("restart-zero", service.restart_gui_session(sid))
        child = restarted["session_id"]
        sessions.append(child)
        assert restarted["restoration"]["model_context"]["empty_model_verified"]
        assert restarted["restoration"]["data"]["counts"]["nodes"] == 0
        assert checked("repeat-restart", service.restart_gui_session(sid))["reused"]
        assert service.restart_gui_session(sid)["session_id"] == child
        child_saved = checked("verify-material", service.checkpoint_gui_session(child))
        child_path = next(a["path"] for a in child_saved["artifacts"] if a["kind"] == "keyword")

        def materials(path):
            return [(n, h) for n, h, _ in native_blocks(Path(path)) if n.startswith("*MAT_")]

        assert materials(saved_path) and materials(saved_path) == materials(child_path)
        checked(
            "save-child-node",
            service.create_gui_nodes(child, [dict(id=201, coordinates=[4.0, 5.0, 6.0])], "mm"),
        )
        last = service.inspect_gui_session(child)["last_checkpoint"]
        assert not checkpoint_expected_empty(last, child)
        terminate_owned(child)
        try:
            service.restart_gui_session(sid)
        except ValueError as exc:
            assert "restart that session" in str(exc)
            cases.append("old-parent-rejected")
        else:
            raise AssertionError("Must not lose child checkpoint by restarting parent again")
        third = checked("restart-nonempty-child", service.restart_gui_session(child))
        grandchild = third["session_id"]
        sessions.append(grandchild)
        observed = checked("recovered-node", service.inspect_gui_mesh(grandchild, include_entities=True))
        assert observed["data"]["nodes"] == [[201, 4.0, 5.0, 6.0]]
        assert all(p.read_bytes() == raw for p, raw in originals.items())
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                cases=cases,
                source_unchanged=True,
                zero_checkpoint_restored=True,
                unsaved_node_not_replayed=True,
                child_checkpoint_restored=True,
                scope="4.13.4 visible GUI: two controlled idle owned-process exits; file-bound zero/nonzero saved-model expectation,material preservation,restart reuse and descendant checkpoint. Not in-flight crash,all view/selection restoration or full model-list lifecycle certification.",
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
