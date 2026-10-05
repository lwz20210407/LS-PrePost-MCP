"""Native load edits on the unchanged official Example11 beam input copy.

Units are explicit test labels, not an inferred physical unit system of the
historical example. No solver response/units validation is claimed.
"""

import argparse
import uuid
from pathlib import Path

from ls_prepost_mcp.boundary_cards import inspect_boundary_cards
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable, keyword):
    root = Path(workspace).resolve() / ("nlp-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    source = Path(keyword).resolve()
    original = source.read_bytes()
    s = Service(Settings(root, Path(executable), allowed_roots=(source.parent,), timeout=90))
    meta = s.start_gui_session()
    sid = meta["session_id"]
    atomic_json(root / "session.json", meta)
    s.show_gui_session(sid, maximize=True)
    print(root, flush=True)
    cases = []

    def check(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        print(name, flush=True)
        cases.append(name)
        return result

    try:
        check("open-official", s.open_in_gui_session(sid, str(source)))
        saved = check("before", s.checkpoint_gui_session(sid))
        before = inspect_boundary_cards(Path(saved["artifacts"][0]["path"]), include_nodal_loads=True)
        assert before["nodal_loads"] and 1 in before["curves"]
        try:
            result = s.create_gui_nodal_load(sid, "y", 1, "s", "N", "per_node", node_ids=[12])
            atomic_json(root / "overlap-attempt.json", result)
            if result["status"] != "succeeded":
                raise RuntimeError(
                    "Native prerequisite failed before overlap check: " + str(result.get("error"))
                )
        except ValueError as exc:
            assert "overlap" in str(exc)
            atomic_json(root / "overlap.json", dict(status="expected_rejection", message=str(exc)))
            cases.append("existing-set-load-overlap")
        else:
            raise AssertionError("Existing node-set load overlap was missed")
        check("reuse-curve-add-x", s.create_gui_nodal_load(sid, "x", 1, "s", "N", "per_node", node_ids=[12]))
        check(
            "explicit-y-superposition",
            s.create_gui_nodal_load(
                sid, "y", 1, "s", "N", "per_node", node_ids=[12], scale=-0.5, allow_superposition=True
            ),
        )
        saved = check("saved", s.checkpoint_gui_session(sid))
        expected = inspect_boundary_cards(Path(saved["artifacts"][0]["path"]), include_nodal_loads=True)
        assert (
            expected["curves"] == before["curves"]
            and len(expected["nodal_loads"]) == len(before["nodal_loads"]) + 2
        )
        atomic_json(root / "closed-before-reopen.json", s.close_gui_session(sid, save_checkpoint=False))
        restarted = check("explicit-restart", s.restart_gui_session(sid))
        sid = restarted["session_id"]
        s.show_gui_session(sid, maximize=True)
        saved = check("reopened", s.checkpoint_gui_session(sid))
        assert (
            inspect_boundary_cards(Path(saved["artifacts"][0]["path"]), include_nodal_loads=True) == expected
        )
        assert source.read_bytes() == original
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                cases=cases,
                source_unchanged=True,
                source_url="https://lsdyna.ansys.com/example-11/",
                scope=__doc__,
            ),
        )
    finally:
        atomic_json(root / "closed.json", s.close_gui_session(sid, save_checkpoint=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--keyword", required=True)
    accept(**vars(parser.parse_args()))
