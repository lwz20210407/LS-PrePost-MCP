"""Synthetic engineering CSV -> native labeled XYPlot/PNG -> numeric readback and recorded replay."""

import argparse
import json
import re
import uuid
from pathlib import Path

from run_result_selection_acceptance import hashes

from ls_prepost_mcp.config import Settings, command_path
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable, source=None):
    root = Path(workspace).resolve() / ("native-curve-acceptance-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    force, displacement = root / "force.csv", root / "displacement.csv"
    force.write_text("time,value\n0,0\n1,100\n2,200\n3,50\n")
    displacement.write_text("time,value\n0,0\n1,1\n2,2\n3,0.5\n")
    originals = {p: p.read_bytes() for p in (force, displacement)}
    allowed = (Path(source).resolve().parent,) if source else ()
    service = Service(Settings(root, Path(executable), allowed_roots=allowed, timeout=90))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session-start.json", session)
    service.show_gui_session(sid, maximize=True)
    recipe = service.create_workflow(
        "Engineering stress-strain and native plot",
        [
            dict(
                id="tensile",
                action="build_tensile_curves",
                arguments=dict(
                    force_curve=str(force),
                    displacement_curve=str(displacement),
                    area={"$param": "area"},
                    gauge_length=10,
                    force_unit="N",
                    length_unit="mm",
                    time_unit="s",
                ),
            ),
            dict(
                id="plot",
                action="export_gui_curve_plot",
                arguments=dict(
                    path={"$artifact": "tensile"},
                    x_column="engineering_strain",
                    y_column="engineering_stress_MPa",
                    title="Engineering stress-strain",
                    x_label="Strain",
                    y_label="Stress",
                    x_unit="1",
                    y_unit="MPa",
                ),
            ),
        ],
        defaults=dict(area=10),
    )
    service.start_session_recording(sid)
    first = service.run_workflow(recipe["artifacts"][0]["path"], session_id=sid)
    atomic_json(root / "first.json", first)
    assert first["status"] == "succeeded", first.get("error")
    plotted = first["data"]["steps"]["plot"]
    assert plotted["data"]["numeric_verification"]["sample_count"] == 4
    assert first["data"]["steps"]["tensile"]["data"]["peak_engineering_stress_MPa"] == 20
    record = service.stop_session_recording(sid)
    assert record["status"] == "succeeded" and record["managed_steps"] == 2
    template = service.parameterize_workflow(
        record["workflow"], [dict(step_id="step1", path=["area"], parameter="area")]
    )
    second = service.run_workflow(template["artifacts"][0]["path"], dict(area=20), session_id=sid)
    atomic_json(root / "second.json", second)
    assert second["status"] == "succeeded", second.get("error")
    replay_plot = second["data"]["steps"]["step2"]
    assert second["data"]["steps"]["step1"]["data"]["peak_engineering_stress_MPa"] == 10
    assert replay_plot["data"]["plot_id"] != plotted["data"]["plot_id"]
    assert replay_plot["inputs"][0]["path"] != plotted["inputs"][0]["path"]
    old_check = root / "old-plot-after.xy"
    manager = service._session_manager()
    with manager.lock(sid):
        result = manager.dispatch(
            sid,
            "inspect_model",
            {},
            native_commands=[
                f"xyplot {plotted['data']['plot_id']} savefile xypair {command_path(old_check)} 1 all"
            ],
        )
    assert result["status"] == "succeeded"
    assert old_check.read_bytes() == Path(plotted["artifacts"][2]["path"]).read_bytes()
    assert all(p.read_bytes() == raw for p, raw in originals.items())
    summary = dict(
        status="succeeded",
        engineering_peak_stress_MPa=[20, 10],
        plots_created=2,
        native_numeric_roundtrip=True,
        old_plot_preserved=True,
        source_unchanged=True,
        result_dependency_rebound=True,
        evidence=str(root),
    )
    if source:
        source = Path(source).resolve(strict=True)
        family = [source] + sorted(
            p
            for p in source.parent.iterdir()
            if p.is_file() and re.fullmatch(re.escape(source.name) + r"\d+", p.name)
        )
        source_hashes = hashes(family)
        assert service.open_in_gui_session(sid, str(source), "d3plot")["status"] == "succeeded"
        mesh = service.inspect_gui_mesh(sid, include_entities=True)
        nodes = mesh["data"]["nodes"]
        axis = max(range(3), key=lambda i: max(n[i + 1] for n in nodes) - min(n[i + 1] for n in nodes))
        ids = sorted({min(nodes, key=lambda n: n[axis + 1])[0], max(nodes, key=lambda n: n[axis + 1])[0]})
        count = mesh["data"]["counts"]["states"]
        assert len(ids) == 2 and count >= 3
        native_template = (
            Path(__file__).resolve().parents[1]
            / "examples/workflows/visible_gui_relative_displacement_plot.json"
        )
        native_recipe = root / "native-recipe.json"
        native_recipe.write_bytes(native_template.read_bytes())
        assert service.set_gui_display(sid, state=2, capture=False)["status"] == "succeeded"
        result = service.run_workflow(
            str(native_recipe),
            dict(
                node_ids=ids,
                component="xyz"[axis],
                states=sorted({1, count // 2, count}),
                units="model_length",
                time_unit="model_time",
            ),
            sid,
        )
        atomic_json(root / "native-extraction-plot.json", result)
        assert result["status"] == "succeeded", result.get("error")
        assert result["data"]["completed_steps"] == 4
        assert result["data"]["steps"]["plot"]["data"]["numeric_verification"]["sample_count"] == 3
        assert service.inspect_gui_mesh(sid)["data"]["current_state"] == 2
        assert hashes(family) == source_hashes
        summary["native_result_extraction_to_PNG"] = True
    atomic_json(root / "acceptance.json", summary)
    service.close_gui_session(sid, save_checkpoint=False)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument(
        "--source", help="Optional authorized private d3plot for native extraction-to-plot validation"
    )
    args = parser.parse_args()
    accept(args.workspace, args.executable, args.source)
