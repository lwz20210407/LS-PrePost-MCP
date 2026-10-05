"""Official generalized/shell motion acceptance and optional partial-load rejection.

This does not replace the separate heterogeneous-model long-session regression.
"""

import argparse
import uuid
from pathlib import Path

from ls_prepost_mcp.boundary_cards import inspect_boundary_cards
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(
    workspace,
    executable,
    keyword,
    unsupported_keyword=None,
    same_session_replace=False,
    expect_replacement_failure=False,
):
    if expect_replacement_failure and not same_session_replace:
        raise ValueError("Failure regression requires --same-session-replace")
    root = Path(workspace).resolve() / ("pmp-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    source = Path(keyword).resolve()
    original = source.read_bytes()
    negative = Path(unsupported_keyword).resolve() if unsupported_keyword else None
    negative_original = negative.read_bytes() if negative else None
    s = Service(
        Settings(
            root,
            Path(executable),
            allowed_roots=tuple([source.parent] + ([negative.parent] if negative else [])),
            timeout=60,
        )
    )
    meta = s.start_gui_session()
    sid = meta["session_id"]
    atomic_json(root / "session.json", meta)
    s.show_gui_session(sid, maximize=True)
    cases = []
    print(root, flush=True)

    def check(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        cases.append(name)
        print(name, flush=True)
        return result

    try:
        if negative:
            rejected = s.open_in_gui_session(sid, str(negative))
            atomic_json(root / "unsupported-keyword.json", rejected)
            assert rejected["status"] == "failed" and "Invalid Keyword" in rejected["error"]["message"]
            assert rejected["data"]["counts"]["nodes"] == 81 and rejected["data"]["counts"]["elements"] == 64
            state = s.inspect_gui_session(sid)
            assert state["state"] == "uncertain" and state["model_generation"] == meta["model_generation"]
            assert negative.read_bytes() == negative_original
            cases.append("partial-import-rejected-despite-matching-mesh-counts")
            atomic_json(root / "negative-closed.json", s.close_gui_session(sid, save_checkpoint=False))
            meta = s.start_gui_session()
            sid = meta["session_id"]
            atomic_json(root / "positive-session.json", meta)
            s.show_gui_session(sid, maximize=True)
        opened = check("open-public-shell", s.open_in_gui_session(sid, str(source)))
        assert opened["data"]["counts"]["nodes"] == 6 and opened["data"]["counts"]["elements"] == 2
        try:
            s.create_gui_prescribed_motion(
                sid, 901, "Rotation conflict", "ry", "velocity", 1, "s", "mm", node_ids=[1]
            )
        except ValueError as exc:
            atomic_json(
                root / "existing-rotation-conflict.json", dict(status="expected_rejection", message=str(exc))
            )
            cases.append("existing-rotation-conflict")
        else:
            raise AssertionError("Existing prescribed motion was not detected")
        try:
            s.create_gui_prescribed_motion(
                sid, 902, "Inline fixed X", "x", "displacement", 1, "s", "mm", node_ids=[1]
            )
        except ValueError as exc:
            assert "TC/RC" in str(exc)
            cases.append("inline-node-constraint-rejected")
            atomic_json(root / "inline-node-conflict.json", dict(message=str(exc)))
        else:
            raise AssertionError("NODE TC constraint was not checked")
        check(
            "add-y-displacement",
            s.create_gui_prescribed_motion(
                sid,
                901,
                "Additional Y motion",
                "y",
                "displacement",
                901,
                "s",
                "mm",
                node_ids=[3],
                points=[[0.0, 0.0], [0.1, 1.0]],
                curve_title="Additional Y history",
            ),
        )
        saved = check("save", s.checkpoint_gui_session(sid))
        before = inspect_boundary_cards(Path(saved["artifacts"][0]["path"]), include_motions=True)
        assert {(m["target_id"], m["dof"]) for m in before["motions"]} == {(1, 6), (2, 6), (3, 2)}
        if same_session_replace:
            # Explicit diagnostic option: this branch has a retained native
            # failure on the public angular fixture; do not count it as passed.
            replaced = s.replace_gui_model(sid, saved["artifacts"][0]["path"])
            atomic_json(root / "same-session-replace.json", replaced)
            if expect_replacement_failure:
                assert replaced["status"] == "failed" and replaced["old_model_unloaded"] is True
                state = s.inspect_gui_session(sid)
                atomic_json(root / "failed-session.json", state)
                assert not state["process_alive"] and state["state"] != "ready"
                assert (
                    inspect_boundary_cards(Path(replaced["old_checkpoint"]), include_motions=True) == before
                )
                cases.append("native-exit-reported-inside-replacement-with-checkpoint")
                # Explicit acceptance step, never automatic application fallback.
                restarted = check("explicit-recovery-after-exit", s.restart_gui_session(sid))
                sid = restarted["session_id"]
                s.show_gui_session(sid, maximize=True)
            else:
                check("same-session-replace", replaced)
        else:
            atomic_json(root / "before-restart-close.json", s.close_gui_session(sid, save_checkpoint=False))
            restarted = check("fresh-process-native-reopen", s.restart_gui_session(sid))
            sid = restarted["session_id"]
            atomic_json(root / "reopened-session.json", s.inspect_gui_session(sid))
        saved = check("reopened-export", s.checkpoint_gui_session(sid))
        assert before == inspect_boundary_cards(Path(saved["artifacts"][0]["path"]), include_motions=True)
        assert source.read_bytes() == original
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                cases=cases,
                source_unchanged=True,
                reopen_mode="expected native failure followed by explicit fresh-process recovery"
                if expect_replacement_failure
                else "same-session diagnostic"
                if same_session_replace
                else "explicit fresh owned GUI process",
                scope="4.13.4 visible official6-node/2-shell angular model: existing rotation/inline NODE constraints, added Y motion, curve/card preservation and explicit reopen. Optional obsolete linear case must fail on skipped keyword even with81/64 mesh counts. Same-session replacement remains a separate retained native failure; no solver or general long-session certification.",
            ),
        )
    finally:
        atomic_json(root / "closed.json", s.close_gui_session(sid, save_checkpoint=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True)
    p.add_argument("--executable", required=True)
    p.add_argument("--keyword", required=True)
    p.add_argument("--unsupported-keyword")
    p.add_argument("--same-session-replace", action="store_true")
    p.add_argument(
        "--expect-replacement-failure",
        action="store_true",
        help="Verify retained 4.13.4 angular-shell crash is reported inside replacement, then explicitly recover",
    )
    accept(**vars(p.parse_args()))
