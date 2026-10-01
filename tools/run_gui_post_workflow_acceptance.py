"""Opt-in native selection -> nodal history -> relative displacement workflow.

Uses one staged result family. IDs, values, source paths and all evidence remain
in the caller's private --workspace; no source file is modified or uploaded.
"""

import argparse
import csv
import json
import re
import uuid
from pathlib import Path

import numpy as np
from run_result_selection_acceptance import hashes

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def matrix(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return np.asarray([[float(v) for v in row] for row in list(csv.reader(stream))[1:]])


def accept(workspace, executable, source):
    source = Path(source).resolve(strict=True)
    family = [source] + sorted(
        p
        for p in source.parent.iterdir()
        if p.is_file() and re.fullmatch(re.escape(source.name) + r"\d+", p.name)
    )
    identities = hashes(family)
    root = Path(workspace).resolve() / ("native-post-workflow-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    atomic_json(root / "source-identities.json", identities)
    service = Service(Settings(root, Path(executable), allowed_roots=(source.parent,), timeout=60))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session-start.json", session)
    service.show_gui_session(sid, maximize=True)
    assert service.open_in_gui_session(sid, str(source), "d3plot")["status"] == "succeeded"
    initial = service.inspect_gui_mesh(sid, include_entities=True)
    assert initial["status"] == "succeeded"
    nodes = initial["data"]["nodes"]
    axis = max(range(3), key=lambda i: max(n[i + 1] for n in nodes) - min(n[i + 1] for n in nodes))
    selected = sorted({min(nodes, key=lambda n: n[axis + 1])[0], max(nodes, key=lambda n: n[axis + 1])[0]})
    assert len(selected) == 2, "A two-node extent is required for this representative fixture"
    count = initial["data"]["counts"]["states"]
    states = sorted({1, max(2, count // 2), count})
    assert count >= 2
    assert (
        service.set_gui_display(sid, state=2, view="isometric", center=True, capture=False)["status"]
        == "succeeded"
    )
    defaults = dict(
        node_ids=selected,
        states=states,
        component="xyz"[axis],
        units="model_length",
        time_unit="model_time",
    )
    template = json.loads(
        (
            Path(__file__).resolve().parents[1] / "examples/workflows/visible_gui_relative_displacement.json"
        ).read_text(encoding="utf-8")
    )
    definition = service.create_workflow(template["name"], template["steps"], defaults)
    path = definition["artifacts"][0]["path"]
    results = []
    for index, component in enumerate(["xyz"[axis], "xyz"[(axis + 1) % 3]]):
        result = service.run_workflow(path, parameters=dict(component=component), session_id=sid)
        results.append(result)
        atomic_json(root / "workflow-results.json", results)
        print("native_post_workflow", index + 1, result["status"], flush=True)
        assert result["status"] == "succeeded", result
        steps = result["data"]["steps"]
        assert result["data"]["completed_steps"] == 3
        curves = steps["history"]["data"]["curves"]
        a, b = [matrix(c["path"]) for c in curves]
        relative = matrix(steps["relative"]["artifacts"][0]["path"])
        assert np.array_equal(a[:, 0], b[:, 0]) and np.array_equal(relative[:, 0], a[:, 0])
        assert np.allclose(relative[:, 1], a[:, 1] - b[:, 1], rtol=1e-12, atol=1e-12)
        after = service.inspect_gui_mesh(sid, include_entities=True)
        assert after["data"]["current_state"] == 2
        assert after["data"]["selection_ids"] == selected
        assert after["data"]["nodes"] == initial["data"]["nodes"]
        assert after["data"]["part_visibility"] == initial["data"]["part_visibility"]

    # Independent native quantity identity: position - reference = displacement.
    position = service.gui_session_action(
        sid,
        "extract_node_history",
        dict(node_ids=selected, quantity="position", states=states, units="model_length"),
    )
    assert position["status"] == "succeeded", position
    displacement = matrix(results[0]["data"]["steps"]["history"]["artifacts"][0]["path"])
    coordinates = matrix(position["artifacts"][0]["path"])
    reference = {n[0]: np.asarray(n[1:]) for n in nodes}
    assert np.array_equal(coordinates[:, :3], displacement[:, :3])
    for row, disp in zip(coordinates, displacement):
        assert np.allclose(row[3:6] - reference[int(row[2])], disp[3:6], rtol=2e-5, atol=1e-5)
    assert hashes(family) == identities
    assert not list((Path(session["directory"]) / "requests").rglob("model.k"))
    atomic_json(
        root / "acceptance.json",
        dict(
            status="succeeded",
            session_id=sid,
            workflow_runs=2,
            steps_per_run=3,
            state_selection_geometry_visibility_preserved=True,
            source_files_unchanged=True,
            native_position_displacement_identity=True,
            keyword_exports=0,
            scope="Native nodal vectors and component difference; units are explicit unknown model labels, no physical conversion or force/stress inference",
        ),
    )
    print("succeeded", str(root), flush=True)
    service.close_gui_session(sid, save_checkpoint=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    accept(args.workspace, args.executable, args.source)
