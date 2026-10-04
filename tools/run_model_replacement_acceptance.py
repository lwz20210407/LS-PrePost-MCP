"""Opt-in same-process keyword/result replacement matrix and preserved recovery."""

import argparse
import uuid
from pathlib import Path

from run_element_set_acceptance import fixture
from run_resident_activation_acceptance import sha

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable, d3plot, second_d3plot=None):
    root = Path(workspace).resolve() / ("mr-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    plots = [Path(d3plot).resolve(), Path(second_d3plot or d3plot).resolve()]
    service = Service(
        Settings(root, Path(executable), allowed_roots=tuple({p.parent for p in plots}), timeout=60)
    )
    originals = {p: sha(p) for plot in plots for p in plot.parent.glob(plot.name + "*") if p.is_file()}
    models = {}
    for name in ("keeper", "a", "b"):
        p = root / (name + ".k")
        fixture(p)
        p.write_text(p.read_text().replace("Element set acceptance fixture", name))
        models[name] = p
        originals[p] = sha(p)
    empty = root / "empty.k"
    empty.write_text("*KEYWORD\n*TITLE\nIntentional empty model\n*END\n")
    originals[empty] = sha(empty)
    meta = service.start_gui_session()
    sid = meta["session_id"]
    sessions = [sid]
    atomic_json(root / "session.json", meta)
    service.show_gui_session(sid, maximize=True)
    cases = []
    print(root, flush=True)

    def check(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        cases.append(name)
        print(name, flush=True)
        return result

    def replacement(name, path, kind="keyword", empty_expected=False):
        result = check(name, service.replace_gui_model(sid, str(path), kind, expected_empty=empty_expected))
        assert len(result["native_models"]["models"]) == 3
        assert result["old_model_unloaded"] and result["temporary_model_removed"]
        return result

    def nodes(name, present):
        result = check(name, service.inspect_gui_mesh(sid, include_entities=True))
        ids = {r[0] for r in result["data"]["nodes"]}
        assert present in ids

    try:
        check("open-keeper", service.open_in_gui_session(sid, str(models["keeper"])))
        keeper = service.inspect_gui_session(sid)["staged_model"]
        check("edit-keeper", service.create_gui_nodes(sid, [dict(id=601, coordinates=[601, 2, 3])], "mm"))
        check("save-keeper", service.checkpoint_gui_session(sid))
        check("open-a", service.open_in_gui_session(sid, str(models["a"])))
        check("edit-a", service.create_gui_nodes(sid, [dict(id=301, coordinates=[301, 2, 3])], "mm"))
        old = replacement("keyword-to-result", plots[0], "d3plot")
        replacement("result-to-keyword-checkpoint", old["old_checkpoint"])
        nodes("restored-a-edit", 301)
        replacement("keyword-to-keyword", models["b"])
        replacement("keyword-to-result-again", plots[0], "d3plot")
        replacement("result-to-result", plots[1], "d3plot")
        replacement("result-to-intentional-empty", empty, empty_expected=True)
        info = check("empty-native-readback", service.gui_session_action(sid, "inspect_model", {}))
        assert info["data"]["counts"]["nodes"] == info["data"]["counts"]["elements"] == 0
        check("untargeted-keeper-activation", service.activate_gui_model(sid, keeper))
        nodes("untargeted-keeper-edit-retained", 601)
        failed = service.replace_gui_model(sid, str(empty))
        atomic_json(root / "unexpected-empty-failure.json", failed)
        assert failed["status"] == "failed" and not failed["old_model_unloaded"]
        assert service.inspect_gui_session(sid)["state"] == "uncertain"
        assert Path(failed["old_checkpoint"]).is_file()
        cases.append("unexpected-empty-rejected-with-checkpoint")
        snapshot = service.inspect_gui_session(sid, include_models=True)
        atomic_json(root / "failure-inventory.json", snapshot)
        # Explicit test recovery in a fresh owned process, not automatic replay.
        service.close_gui_session(sid, save_checkpoint=False)
        fresh = service.start_gui_session()
        sid = fresh["session_id"]
        sessions.append(sid)
        service.show_gui_session(sid, maximize=True)
        check("open-failure-checkpoint", service.open_in_gui_session(sid, failed["old_checkpoint"]))
        nodes("failure-checkpoint-keeps-edit", 601)
        assert all(sha(p) == digest for p, digest in originals.items())
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                cases=cases,
                originals_unchanged=True,
                scope="4.13.4 visible keyword/result replacement matrix; each success preserves three resident entries with no temporary accumulation; unrelated edited keeper retained, unexpected empty load rejects before old unload, explicit checkpoint recovery in fresh owned GUI. No association/scene replay/full recordings certification.",
            ),
        )
    finally:
        for ident in sessions:
            if service.inspect_gui_session(ident)["process_alive"]:
                atomic_json(
                    root / ("closed-" + ident + ".json"),
                    service.close_gui_session(ident, save_checkpoint=False),
                )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True)
    p.add_argument("--executable", required=True)
    p.add_argument("--d3plot", required=True)
    p.add_argument("--second-d3plot")
    accept(**vars(p.parse_args()))
