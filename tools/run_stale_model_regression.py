"""Revisit the public bird keyword/result false-success regression in visible GUI."""

import argparse
import uuid
from pathlib import Path

from run_resident_activation_acceptance import sha

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable, keyword, d3plot):
    root = Path(workspace).resolve() / ("sr-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    keyword, plot = Path(keyword).resolve(), Path(d3plot).resolve()
    originals = {p: sha(p) for p in [keyword, *[f for f in plot.parent.glob(plot.name + "*") if f.is_file()]]}
    service = Service(
        Settings(root, Path(executable), allowed_roots=(keyword.parent, plot.parent), timeout=60)
    )
    sessions = []
    cases = []
    print(root, flush=True)

    def checked(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        print(name, flush=True)
        cases.append(name)
        return result

    def start():
        meta = service.start_gui_session()
        sid = meta["session_id"]
        sessions.append(sid)
        atomic_json(root / ("session-" + sid + ".json"), meta)
        service.show_gui_session(sid, maximize=True)
        return sid

    try:
        sid = start()
        loaded = checked("fresh-keyword", service.open_in_gui_session(sid, str(keyword)))
        counts = loaded["data"]["counts"]
        assert counts["nodes"] == 2957 and counts["elements"] == 3005 and counts["states"] == 1
        checked("keyword-to-result", service.open_in_gui_session(sid, str(plot), "d3plot"))
        before = service.inspect_gui_session(sid)
        direct = service.open_in_gui_session(sid, str(keyword))
        atomic_json(root / "direct-result-to-keyword.json", direct)
        after = service.inspect_gui_session(sid)
        if direct["status"] == "failed":
            assert after["state"] == "uncertain"
            assert all(
                after[k] == before[k] for k in ("source", "staged_model", "model_generation", "model_kind")
            )
            outcome = "native_failure_rejected_without_advancing_source"
        else:
            assert direct["status"] == "succeeded" and direct["data"]["counts"] == counts
            assert (
                after["model_kind"] == "keyword" and after["model_generation"] != before["model_generation"]
            )
            assert direct["model_context"]["active_source_verified"]
            outcome = "native_success_with_verified_new_keyword_context"
        cases.append(outcome)
        service.close_gui_session(sid, save_checkpoint=False)
        sid = start()
        checked("fresh-result", service.open_in_gui_session(sid, str(plot), "d3plot"))
        replaced = checked("explicit-result-to-keyword", service.replace_gui_model(sid, str(keyword)))
        assert replaced["data"]["counts"] == counts and replaced["old_model_unloaded"] is True
        assert len(replaced["native_models"]["models"]) == 2
        assert service.inspect_gui_session(sid)["model_kind"] == "keyword"
        assert all(sha(p) == value for p, value in originals.items())
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                cases=cases,
                direct_open_outcome=outcome,
                source_unchanged=True,
                counts=counts,
                scope="4.13.4 visible public bird source/state false-success regression and explicit replacement. Inventory/source only; no SPH/composite field array or association certification.",
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
    p.add_argument("--keyword", required=True)
    p.add_argument("--d3plot", required=True)
    accept(**vars(p.parse_args()))
