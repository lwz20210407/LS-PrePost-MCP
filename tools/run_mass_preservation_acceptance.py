"""Opt-in mass-only model selection/set/load replay and native reopen."""

import argparse
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.embedded import read_native_masses
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("mps-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    source = root / "point-mass.k"
    source.write_text(
        "*KEYWORD\n*NODE\n11,0,0,0\n22,1,0,0\n*ELEMENT_MASS\n900,11,2.5,0\n901,22,3.5,0\n*END\n",
        encoding="ascii",
    )
    original = source.read_bytes()
    s = Service(Settings(root, Path(executable), timeout=60))
    meta = s.start_gui_session()
    sid = meta["session_id"]
    atomic_json(root / "session.json", meta)
    s.show_gui_session(sid, maximize=True)
    print(root, flush=True)
    cases = []

    def check(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        cases.append(name)
        print(name, flush=True)
        return result

    try:
        check("open-mass-only", s.open_in_gui_session(sid, str(source)))
        s.start_session_recording(sid)
        selected = check("node-selection", s.select_gui_entities(sid, "node", entity_ids=[11]))
        assert selected["verification"]["entity_display_active_preserved"] is None
        check(
            "node-set",
            s.create_gui_entity_set(sid, "node", 55, "Loaded mass", selection_job=selected["job_directory"]),
        )
        load = check(
            "nodal-load",
            s.create_gui_nodal_load(
                sid,
                "z",
                710,
                "s",
                "N",
                "per_node",
                node_set_id=55,
                points=[[0.0, 0.0], [1.0, 10.0]],
                curve_title="Mass force",
            ),
        )
        assert load["verification"]["auxiliary_elements"]["mass_count"] == 2
        assert load["verification"]["display_active_preserved"] is None
        recording = check("recording", s.stop_session_recording(sid))
        parameterized = s.parameterize_workflow(
            recording["workflow"], [dict(step_id="step1", path=["entity_ids"], parameter="nodes")]
        )
        check(
            "changed-node-replay",
            s.run_workflow(parameterized["artifacts"][0]["path"], dict(nodes=[22]), sid),
        )
        members = check("replayed-set-members", s.inspect_gui_entity_sets(sid, "node", 55))
        assert members["data"]["member_ids"] == [22]
        saved = check("save-masses", s.checkpoint_gui_session(sid))
        expected = {900: (11, 2.5, 0), 901: (22, 3.5, 0)}
        assert read_native_masses(saved["artifacts"][0]["path"], 2) == expected
        atomic_json(root / "closed-before-reopen.json", s.close_gui_session(sid, save_checkpoint=False))
        restarted = check("explicit-restart", s.restart_gui_session(sid))
        sid = restarted["session_id"]
        s.show_gui_session(sid, maximize=True)
        saved = check("reopened-save", s.checkpoint_gui_session(sid))
        assert read_native_masses(saved["artifacts"][0]["path"], 2) == expected
        assert source.read_bytes() == original
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                cases=cases,
                source_unchanged=True,
                scope="4.13.4 mass-only two-node/two-mass model; no beam fallback dependency. Node selection, set creation, load, changed-node replay and fresh-process reopen preserve mass/node/part records. Mass glyph display, inertia and other auxiliary families unverified.",
            ),
        )
    finally:
        atomic_json(root / "closed.json", s.close_gui_session(sid, save_checkpoint=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True)
    p.add_argument("--executable", required=True)
    accept(**vars(p.parse_args()))
