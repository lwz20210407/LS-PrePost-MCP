"""Opt-in named-field PNG/CSV, independent native values, replay and custom-field movie checks."""

import argparse
import csv
import json
import math
import re
import uuid
from pathlib import Path

from run_result_selection_acceptance import hashes

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def table(result, index=1):
    with Path(result["artifacts"][index]["path"]).open(newline="") as stream:
        return list(csv.DictReader(stream))


def accept(workspace, executable, source, part):
    source = Path(source).resolve(strict=True)
    family = [source] + sorted(
        p
        for p in source.parent.iterdir()
        if p.is_file() and re.fullmatch(re.escape(source.name) + r"\d+", p.name)
    )
    identities = hashes(family)
    root = Path(workspace).resolve() / ("native-fringe-acceptance-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    s = Service(Settings(root, Path(executable), allowed_roots=(source.parent,), timeout=120))
    session = s.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session-start.json", session)
    s.show_gui_session(sid, maximize=True)
    assert s.open_in_gui_session(sid, str(source), "d3plot")["status"] == "succeeded"
    info = s.set_gui_display(sid, view="isometric", center=True, capture=False)
    last = info["data"]["counts"]["states"]
    target = max(2, last // 2)
    assert last >= 3
    late = s.render_gui_field(sid, "solid", "von_mises", target, "model_stress", part_ids=[part])
    atomic_json(root / "late.json", late)
    assert late["status"] == "succeeded", late.get("error")
    values = table(late)
    assert late["data"]["value_max"] > 0, "Use a loaded nontrivial solid fixture"
    selected = sorted(
        {
            int(min(values, key=lambda r: float(r["von_mises"]))["entity_id"]),
            int(max(values, key=lambda r: float(r["von_mises"]))["entity_id"]),
            int(values[len(values) // 2]["entity_id"]),
        }
    )
    check = s.gui_session_action(
        sid,
        "extract_native_stress",
        dict(
            element_type="solid",
            element_ids=selected,
            states=[target],
            integration_point="mid",
            units="model_stress",
        ),
    )
    atomic_json(root / "independent-stress.json", check)
    assert check["status"] == "succeeded", check.get("error")
    lookup = {int(r["entity_id"]): float(r["von_mises"]) for r in values}
    for row in table(check, 0):
        assert math.isclose(lookup[int(row["entity_id"])], float(row["von_mises"]), rel_tol=2e-6, abs_tol=0)
    pressure = s.render_gui_field(sid, "solid", "pressure", target, "model_stress", part_ids=[part])
    atomic_json(root / "pressure.json", pressure)
    assert pressure["status"] == "succeeded", pressure.get("error")
    pressure_values = {int(r["entity_id"]): float(r["pressure"]) for r in table(pressure)}
    for row in table(check, 0):
        expected = -(float(row["stress_x"]) + float(row["stress_y"]) + float(row["stress_z"])) / 3
        assert math.isclose(pressure_values[int(row["entity_id"])], expected, rel_tol=2e-6, abs_tol=0)
    mean = s.render_gui_field(sid, "solid", "mean_stress", target, "model_stress", part_ids=[part])
    atomic_json(root / "mean-stress.json", mean)
    assert mean["status"] == "succeeded", mean.get("error")
    for row in table(mean):
        assert math.isclose(
            float(row["mean_stress"]), -pressure_values[int(row["entity_id"])], rel_tol=2e-6, abs_tol=0
        )
    nodes = s.render_gui_field(sid, "node", "disp_magnitude", target, "model_length", part_ids=[part])
    atomic_json(root / "node-magnitude.json", nodes)
    assert nodes["status"] == "succeeded", nodes.get("error")
    node_rows = table(nodes)
    chosen = sorted(
        {
            int(min(node_rows, key=lambda r: float(r["disp_magnitude"]))["entity_id"]),
            int(max(node_rows, key=lambda r: float(r["disp_magnitude"]))["entity_id"]),
        }
    )
    vectors = s.gui_session_action(
        sid,
        "extract_nodal_results",
        dict(node_ids=chosen, quantity="displacement", state=target, units="model_length"),
    )
    atomic_json(root / "independent-vectors.json", vectors)
    assert vectors["status"] == "succeeded", vectors.get("error")
    node_values = {int(r["entity_id"]): float(r["disp_magnitude"]) for r in node_rows}
    for row in table(vectors, 0):
        assert math.isclose(
            node_values[int(row["node_id"])], float(row["magnitude"]), rel_tol=2e-6, abs_tol=0
        )
    pick = s.select_gui_entities(sid, "node", part_ids=[part])
    assert set(pick["verification"]["selected_ids"]) == set(node_values), (
        "This acceptance uses non-eroding visible connected nodes"
    )
    try:
        s.export_gui_animation(sid, last=2, width=640, height=480)
    except ValueError as exc:
        assert "not defined" in str(exc)
    else:
        raise AssertionError("Sparse custom-fringe movie should be rejected")
    fixed = [0, late["data"]["value_max"] * 1.05]
    made = s.create_workflow(
        "Verified named field scene",
        [
            dict(
                id="field",
                action="render_gui_field",
                arguments=dict(
                    entity_type="solid",
                    field="von_mises",
                    state={"$param": "state"},
                    units="model_stress",
                    part_ids=[part],
                    color_range=fixed,
                ),
            )
        ],
        defaults=dict(state=1),
    )
    s.start_session_recording(sid)
    first = s.run_workflow(made["artifacts"][0]["path"], session_id=sid)
    atomic_json(root / "first.json", first)
    assert first["status"] == "succeeded", first.get("error")
    recording = s.stop_session_recording(sid)
    assert recording["status"] == "succeeded" and recording["managed_steps"] == 1
    template = s.parameterize_workflow(
        recording["workflow"], [dict(step_id="step1", path=["state"], parameter="state")]
    )
    replay = s.run_workflow(template["artifacts"][0]["path"], dict(state=target), sid)
    atomic_json(root / "replay.json", replay)
    assert replay["status"] == "succeeded", replay.get("error")
    assert (
        first["data"]["steps"]["field"]["data"]["color_range"]
        == replay["data"]["steps"]["step1"]["data"]["color_range"]
    )
    assert (
        replay["data"]["steps"]["step1"]["data"]["value_max"]
        != first["data"]["steps"]["field"]["data"]["value_max"]
    )
    # Reopened recording baseline clears old coverage: build a consistent contiguous pair.
    second_state = s.render_gui_field(sid, "solid", "von_mises", 2, "model_stress", part_ids=[part])
    assert second_state["status"] == "succeeded" and second_state["data"]["value_max"] > 0
    movie_bounds = [0, second_state["data"]["value_max"] * 1.05]
    for state in (1, 2):
        frame = s.render_gui_field(
            sid, "solid", "von_mises", state, "model_stress", part_ids=[part], color_range=movie_bounds
        )
        assert frame["status"] == "succeeded", frame.get("error")
        atomic_json(root / f"movie-field-{state}.json", frame)
    movie = s.export_gui_animation(sid, last=2, width=640, height=480)
    atomic_json(root / "field-movie.json", movie)
    assert movie["status"] == "succeeded", movie.get("error")
    assert (
        movie["data"]["managed_field"]["coverage_verified"] and movie["data"]["video"]["decoded_frames"] == 2
    )
    assert hashes(family) == identities
    summary = dict(
        status="succeeded",
        native_stress_and_vector_crosschecks=True,
        native_connected_node_set=True,
        state_switch_and_fixed_range_replay=True,
        sparse_movie_rejected=True,
        consistent_custom_movie=True,
        source_unchanged=True,
        evidence=str(root),
    )
    atomic_json(root / "acceptance.json", summary)
    s.close_gui_session(sid, save_checkpoint=False)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "executable", "source"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--part", required=True, type=int)
    a = p.parse_args()
    accept(a.workspace, a.executable, a.source, a.part)
