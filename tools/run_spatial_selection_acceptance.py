"""Native100,000-shell spatial selection with an independent exported-node oracle."""

import argparse
import math
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.deck_backend import api
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.model_deck import load_standalone, table
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("native-spatial-selection-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    s = Service(Settings(root, Path(executable), timeout=240))
    session = s.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session.json", session)
    checks = []
    try:
        s.show_gui_session(sid, maximize=True)
        made = s.gui_session_action(sid, "create_shell_plate", dict(nx=400, ny=250, size=[400., 250.], units="mm"))
        atomic_json(root / "created.json", made)
        assert made["status"] == "succeeded", made.get("error")
        checkpoint = s.checkpoint_gui_session(sid)
        assert checkpoint["status"] == "succeeded"
        _, kw = api()
        frame = table(load_standalone(Path(checkpoint["artifacts"][0]["path"])), kw.Node, "nodes")
        oracle = [(int(row.nid), float(row.x), float(row.y), float(row.z)) for row in frame.itertuples()]
        assert len(oracle) == 100651

        def check(name, result, predicate):
            atomic_json(root / (name + ".json"), result)
            assert result["status"] == "succeeded", result.get("error")
            expected = sorted(row[0] for row in oracle if predicate(*row[1:]))
            assert result["verification"]["selected_ids"] == expected
            assert result["verification"]["mesh_verification"]["whole_mesh_json"] is False
            checks.append(dict(name=name, selected=len(expected)))

        s.start_session_recording(sid)
        check("box", s.select_gui_nodes_by_box(sid, [0., 0., -1., 2., 2., 1.], "mm"),
              lambda x, y, z: 0 <= x <= 2 and 0 <= y <= 2 and -1 <= z <= 1)
        recorded = s.stop_session_recording(sid)
        assert recorded["status"] == "succeeded" and recorded["managed_steps"] == 1
        template = s.parameterize_workflow(recorded["workflow"], [dict(step_id="step1", path=["bounds"], parameter="box")])
        replay = s.run_workflow(template["artifacts"][0]["path"], dict(box=[0., 0., -1., 3., 3., 1.]), sid)
        atomic_json(root / "replay.json", replay)
        assert replay["status"] == "succeeded", replay.get("error")
        check("replayed-box", replay["data"]["steps"]["step1"],
              lambda x, y, z: 0 <= x <= 3 and 0 <= y <= 3 and -1 <= z <= 1)
        check("outside-box", s.select_gui_nodes_by_box(sid, [0., 0., -1., 399., 250., 1.], "mm", inside=False),
              lambda x, y, z: not (0 <= x <= 399 and 0 <= y <= 250 and -1 <= z <= 1))
        check("sphere", s.select_gui_nodes_by_sphere(sid, [0., 0., 0.], 2., "mm"),
              lambda x, y, z: math.hypot(x, y, z) <= 2)
        check("outside-sphere-empty", s.select_gui_nodes_by_sphere(sid, [0., 0., 0.], 1000., "mm", inside=False),
              lambda x, y, z: math.hypot(x, y, z) > 1000)
        for side in ("band", "positive", "negative"):
            origin = 0. if side == "band" else 399. if side == "positive" else 1.
            check("plane-" + side, s.select_gui_nodes_by_plane(sid, [origin, 0., 0.], [2., 0., 0.], "mm", side=side),
                  lambda x, y, z, side=side, origin=origin: abs(x - origin) <= 0 if side == "band" else
                  x > origin if side == "positive" else x < origin)
        atomic_json(root / "acceptance.json", dict(status="succeeded", checks=checks,
                    oracle="Independent PyDYNA read of native exported NODE table; actions and selection readback native"))
    finally:
        atomic_json(root / "closed.json", s.close_gui_session(sid, save_checkpoint=False))
    print(str(root), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    accept(**vars(parser.parse_args()))
