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
    solids = [e["id"] for e in initial["data"]["elements"] if e["type"] == "solid"]
    assert solids, "This representative field acceptance requires solids"
    elements = sorted({solids[0], solids[len(solids) // 2], solids[-1]})
    service.start_session_recording(sid)
    assert service.set_gui_display(sid, state=2, capture=False)["status"] == "succeeded"
    stress_workflow = service.create_workflow(
        "Visible selected-solid stress history",
        [
            dict(
                id="selected",
                action="select_gui_entities",
                arguments=dict(entity_type="solid", entity_ids=elements),
            ),
            dict(
                id="stress",
                action="extract_native_stress",
                arguments=dict(
                    element_type="solid",
                    element_ids={"$result": "selected", "path": ["verification", "selected_ids"]},
                    states=states,
                    integration_point="mid",
                    units="model_stress",
                ),
                checks=[dict(path=["data", "session_context_preserved"], operator="is_true")],
            ),
        ],
    )
    stresses = service.run_workflow(stress_workflow["artifacts"][0]["path"], session_id=sid)
    atomic_json(root / "stress-workflow.json", stresses)
    print("native_selected_stress_workflow", stresses["status"], flush=True)
    assert stresses["status"] == "succeeded", stresses.get("error")
    stress_result = stresses["data"]["steps"]["stress"]
    assert stress_result["execution_mode"] == "visible_gui_native_scl"
    assert stress_result["data"]["row_count"] == len(elements) * len(states)
    assert np.any(matrix(stress_result["artifacts"][0]["path"])[:, 3:9] != 0), (
        "Zero-only fixture cannot certify stress comparison"
    )
    recording = service.stop_session_recording(sid)
    atomic_json(root / "stress-recording.json", recording)
    assert recording["status"] == "succeeded" and recording["managed_steps"] == 3
    parameterized = service.parameterize_workflow(
        recording["workflow"],
        [
            dict(step_id="step3", path=["states"], parameter="stress_states"),
        ],
    )
    replay = service.run_workflow(
        parameterized["artifacts"][0]["path"], parameters=dict(stress_states=states[:2]), session_id=sid
    )
    atomic_json(root / "stress-recording-replay.json", replay)
    print("native_stress_recording_replay", replay["status"], flush=True)
    assert replay["status"] == "succeeded", replay.get("error")
    assert replay["data"]["steps"]["step3"]["data"]["row_count"] == len(elements) * 2
    strain = service.gui_session_action(
        sid,
        "extract_native_fields",
        dict(
            entity_type="solid",
            entity_ids=elements,
            states=states,
            fields=[
                "effective_plastic_strain",
                "strain_x",
                "strain_y",
                "strain_z",
                "strain_xy",
                "strain_yz",
                "strain_zx",
            ],
            integration_point="mid",
            units="dimensionless native strain convention",
        ),
    )
    atomic_json(root / "strain-fields.json", strain)
    print("native_strain_fields", strain["status"], flush=True)
    assert strain["status"] == "succeeded", strain.get("error")
    assert strain["data"]["row_count"] == len(elements) * len(states)
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
            same_gui_scl_stress_and_mises_crosscheck=True,
            same_gui_strain_fields=True,
            stress_recording_parameter_replay=True,
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
