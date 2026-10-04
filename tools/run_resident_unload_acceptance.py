"""Visible owned unload: preserve survivor edits, sparse numbering and explicit undo."""

import argparse
import uuid
from pathlib import Path

from run_element_set_acceptance import fixture
from run_resident_activation_acceptance import sha

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable, d3plot=None):
    root = Path(workspace).resolve() / ("ru-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    plot = Path(d3plot).resolve() if d3plot else None
    service = Service(
        Settings(root, Path(executable), allowed_roots=(plot.parent,) if plot else (), timeout=60)
    )
    meta = service.start_gui_session()
    sid = meta["session_id"]
    atomic_json(root / "session.json", meta)
    service.show_gui_session(sid, maximize=True)
    cases, sources, originals = [], {}, {}
    print(root, flush=True)

    def check(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        cases.append(name)
        print(name, flush=True)
        return result

    def reject(name, call):
        try:
            call()
        except ValueError as exc:
            atomic_json(root / (name + ".json"), dict(status="expected_rejection", message=str(exc)))
            cases.append(name)
        else:
            raise AssertionError("Expected rejection: " + name)

    def node(name, present, absent):
        result = check(name, service.inspect_gui_mesh(sid, include_entities=True))
        nodes = {r[0]: r[1:] for r in result["data"]["nodes"]}
        assert nodes[present] == [float(present), 2.0, 3.0]
        assert all(uid not in nodes for uid in absent)

    try:
        for name, uid in [("a", 301), ("b", 401), ("c", 501)]:
            path = root / (name + ".k")
            fixture(path)
            path.write_text(path.read_text().replace("Element set acceptance fixture", "Resident " + name))
            originals[path] = sha(path)
            check("open-" + name, service.open_in_gui_session(sid, str(path)))
            sources[name] = service.inspect_gui_session(sid)["staged_model"]
            check(
                "edit-" + name, service.create_gui_nodes(sid, [dict(id=uid, coordinates=[uid, 2, 3])], "mm")
            )
            check("save-" + name, service.checkpoint_gui_session(sid))
        if plot:
            originals.update({p: sha(p) for p in plot.parent.glob(plot.name + "*") if p.is_file()})
            check("open-result", service.open_in_gui_session(sid, str(plot), "d3plot"))
            sources["plot"] = service.inspect_gui_session(sid)["staged_model"]
            check("back-to-c", service.activate_gui_model(sid, sources["c"]))
        reject("reject-same-survivor", lambda: service.unload_gui_model(sid, sources["c"], sources["c"]))
        a = check("unload-inactive-a", service.unload_gui_model(sid, sources["a"], sources["c"]))
        b = check("unload-sparse-b", service.unload_gui_model(sid, sources["b"], sources["c"]))
        assert a["remove_display_number"] == 2 and b["remove_display_number"] == 3
        node("c-retained-after-two-removals", 501, [301, 401])
        reject("reject-removed-a", lambda: service.activate_gui_model(sid, sources["a"]))
        check("reopen-removed-a-checkpoint", service.restore_gui_checkpoint(sid, a["removed_checkpoint"]))
        restored = service.inspect_gui_session(sid)["staged_model"]
        node("a-checkpoint-retains-edit", 301, [401, 501])
        atomic_json(
            root / "after-restore-inventory.json", service.inspect_gui_session(sid, include_models=True)
        )
        check("unload-active-restored-a", service.unload_gui_model(sid, restored, sources["c"]))
        node("c-after-active-removal", 501, [301, 401])
        if plot:
            result = check("unload-result", service.unload_gui_model(sid, sources["plot"], sources["c"]))
            assert result["removed_checkpoint"] is None
            node("c-after-result-removal", 501, [301, 401])
        final = service.inspect_gui_session(sid, include_models=True)
        atomic_json(root / "final-inventory.json", final)
        assert len(final["native_models"]["models"]) == 2
        assert all(sha(p) == value for p, value in originals.items())
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                cases=cases,
                sources_unchanged=True,
                remaining_models=2,
                result_unload_tested=bool(plot),
                scope="Visible4.13.4 owned active/inactive keyword unload, sparse native remove numbering, explicit saved checkpoint reopen, survivor edit retention and optional result unload. No source file deletion, full scene/crash recovery or automatic replacement certification.",
            ),
        )
    finally:
        atomic_json(root / "closed.json", service.close_gui_session(sid, save_checkpoint=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True)
    p.add_argument("--executable", required=True)
    p.add_argument("--d3plot")
    accept(**vars(p.parse_args()))
