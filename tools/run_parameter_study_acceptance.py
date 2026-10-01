"""Synthetic engineering study; optional visible native mesh parameter study.

No solver invocation. All generated inputs and outputs stay beneath --workspace.
"""

import argparse
import json
import uuid
from pathlib import Path

from run_gui_solid_quality_acceptance import MODEL

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json, fingerprint
from ls_prepost_mcp.service import Service


def accept(workspace, executable=None):
    root = Path(workspace).resolve() / ("parameter-study-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    service = Service(Settings(root, Path(executable) if executable else None, timeout=60))
    examples = Path(__file__).resolve().parents[1] / "examples/workflows"
    force, moving, reference = [root / (name + ".csv") for name in ("force", "moving", "reference")]
    force.write_text("time,value\n0,0\n1000,1\n2000,2\n")
    moving.write_text("time,value\n0,0\n1,1\n2,2\n")
    reference.write_text("time,value\n0,0\n1,0.1\n2,0.2\n")
    parameters = dict(
        force_curve=str(force),
        force_unit="kN",
        force_time_unit="ms",
        moving_curve=str(moving),
        moving_unit="mm",
        moving_time_unit="s",
        reference_curve=str(reference),
        reference_unit="mm",
        reference_time_unit="s",
        gauge_length_mm=10,
    )
    path = root / "tensile.json"
    path.write_bytes((examples / "declared_unit_tensile.json").read_bytes())
    outputs = {
        "peak_MPa": dict(step_id="tensile", path=["data", "peak_engineering_stress_MPa"]),
        "work_J": dict(step_id="tensile", path=["data", "work_J"]),
    }
    post = service.run_workflow_sweep(
        str(path),
        [
            dict(id="area10", parameters=dict(parameters, area_mm2=10)),
            dict(id="area20", parameters=dict(parameters, area_mm2=20)),
        ],
        outputs,
    )
    atomic_json(root / "engineering-study.json", post)
    assert post["status"] == "succeeded", post.get("error")
    assert [r["outputs"]["peak_MPa"] for r in post["data"]["cases"]] == [200, 100]
    assert all(abs(r["outputs"]["work_J"] - 1.8) < 1e-12 for r in post["data"]["cases"])
    print("engineering study: two cases passed", flush=True)
    native = None
    if executable:
        source = root / "synthetic.k"
        source.write_text(MODEL, encoding="ascii")
        identity = fingerprint(source)
        recipe = root / "mesh.json"
        recipe.write_bytes((examples / "visible_gui_mesh_transform.json").read_bytes())
        session = service.start_gui_session()
        sid = session["session_id"]
        atomic_json(root / "session-start.json", session)
        service.show_gui_session(sid, maximize=True)
        cases = [
            dict(
                id="shift_one", parameters=dict(model=str(source), part_ids=[1], offset=[1, 0, 0], units="mm")
            ),
            dict(
                id="shift_two", parameters=dict(model=str(source), part_ids=[1], offset=[2, 0, 0], units="mm")
            ),
        ]
        native = service.run_workflow_sweep(
            str(recipe), cases, {"node1_x": dict(step_id="verify", path=["data", "nodes", 0, 1])}, sid
        )
        atomic_json(root / "native-study.json", native)
        assert native["status"] == "succeeded", native.get("error")
        assert [r["outputs"]["node1_x"] for r in native["data"]["cases"]] == [1, 2], (
            "Must not accumulate to 3"
        )
        model_artifacts = []
        for row in native["data"]["cases"]:
            child = service.read_job(row["job_id"])
            assert child["data"]["completed_steps"] == 7
            assert child["data"]["gates"]["quality"]["passed"]
            assert child["data"]["steps"]["verify"]["data"]["counts"]["nodes"] == 12
            model_artifacts.append(child["data"]["steps"]["save"]["artifacts"][0]["path"])
        assert len(set(model_artifacts)) == 2 and all(Path(p).is_file() for p in model_artifacts)
        assert fingerprint(source) == identity
        atomic_json(root / "session-close.json", service.close_gui_session(sid, save_checkpoint=False))
        print("visible native mesh study: two cases passed", flush=True)
    summary = dict(
        status="succeeded",
        engineering_cases=2,
        native_cases=2 if native else 0,
        solver_executed=False,
        evidence=str(root),
    )
    atomic_json(root / "acceptance.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", help="Opt in to a visible owned LS-PrePost GUI")
    args = parser.parse_args()
    print(json.dumps(accept(args.workspace, args.executable), indent=2))
