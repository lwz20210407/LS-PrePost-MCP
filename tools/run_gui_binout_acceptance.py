"""Visible SCL Binout MATSUM cross-reader checks and native overlay replay.

Use a complete explicit single-file database with MATSUM IDs1500 and1501,
such as the downloaded official example fixture; no solver assets are bundled.
"""

import argparse
import csv
import json
import uuid
from pathlib import Path

import numpy as np
from run_element_set_acceptance import fixture

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json, fingerprint
from ls_prepost_mcp.results import open_binout
from ls_prepost_mcp.service import Service


def accept(workspace, executable, source):
    source = Path(source).resolve(strict=True)
    root = Path(workspace).resolve() / ("gb-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    model = root / "model.k"
    fixture(model)
    originals = [fingerprint(p) for p in (source, model)]
    mappings = {
        q: q
        for q in (
            "internal_energy",
            "kinetic_energy",
            "eroded_internal_energy",
            "eroded_kinetic_energy",
            "mass",
        )
    }
    mappings.update({f"momentum_{a}": f"{a}_momentum" for a in "xyz"})
    mappings.update({f"rigid_body_velocity_{a}": f"{a}_rbvelocity" for a in "xyz"})
    with open_binout(str(source)) as db:
        ids = list(map(int, db.read("matsum", "ids")))
        times = np.asarray(db.read("matsum", "time"))
        expected = {q: np.asarray(db.read("matsum", v)) for q, v in mappings.items()}
    assert 1500 in ids and 1501 in ids
    service = Service(Settings(root, Path(executable), allowed_roots=(source.parent,), timeout=90))
    meta = service.start_gui_session()
    sid = meta["session_id"]
    atomic_json(root / "session.json", meta)
    cases = []
    results = {}
    print(root, flush=True)

    def checked(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        cases.append(name)
        print(name, flush=True)
        return result

    def compare(result, quantity, uid):
        with Path(result["artifacts"][0]["path"]).open(newline="") as f:
            rows = list(csv.DictReader(f))
        actual = np.array([[float(r["time"]), float(r["value"])] for r in rows])
        reference = np.column_stack((times, expected[quantity][:, ids.index(uid)]))
        assert actual.shape == reference.shape and np.allclose(actual, reference, rtol=2e-7, atol=1e-10)
        return dict(
            samples=len(actual),
            rtol=2e-7,
            atol=1e-10,
            max_absolute_difference=float(np.max(np.abs(actual - reference))),
        )

    comparisons = {}
    try:
        service.show_gui_session(sid, maximize=True)
        checked("open-model", service.open_in_gui_session(sid, str(model)))
        checked("display", service.set_gui_display(sid, view="isometric", center=True, capture=False))
        before = service._session_manager().read(sid)
        for quantity in mappings:
            r = checked(
                quantity,
                service.extract_native_binout_curve(
                    str(source), "matsum", quantity, "unknown source units", entity_id=1500, session_id=sid
                ),
            )
            assert r["execution_mode"] == "visible_gui_scl_binout" and r["process"] == meta["process"]
            comparisons[quantity] = compare(r, quantity, 1500)
            results[quantity] = r
        after = service._session_manager().read(sid)
        assert all(before[k] == after[k] for k in ("dirty", "last_checkpoint", "model_generation", "source"))
        for name, kwargs in [
            ("missing-id", dict(quantity="internal_energy", entity_id=99999999)),
            ("absent-field", dict(quantity="hourglass_energy", entity_id=1500)),
        ]:
            r = service.extract_native_binout_curve(
                str(source), "matsum", units="unknown source units", session_id=sid, **kwargs
            )
            atomic_json(root / (name + ".json"), r)
            assert r["status"] == "failed" and service.inspect_gui_session(sid)["state"] == "ready"
            cases.append(name)
            print(name, flush=True)
        recipe = service.create_workflow(
            "Native MATSUM energy overlay",
            [
                dict(
                    id="internal",
                    action="extract_native_binout_curve",
                    arguments=dict(
                        path=str(source),
                        branch="matsum",
                        quantity="internal_energy",
                        units="unknown source units",
                        entity_id=1500,
                    ),
                ),
                dict(
                    id="kinetic",
                    action="extract_native_binout_curve",
                    arguments=dict(
                        path=str(source),
                        branch="matsum",
                        quantity="kinetic_energy",
                        units="unknown source units",
                        entity_id=1500,
                    ),
                ),
                dict(
                    id="plot",
                    action="export_gui_curve_plot",
                    arguments=dict(
                        path={"$artifact": "internal"},
                        x_column="time",
                        y_column="value",
                        title="MATSUM energies",
                        x_label="Time",
                        y_label="Energy",
                        x_unit="raw",
                        y_unit="raw",
                        curve_label="Internal",
                        additional_curves=[
                            dict(
                                path={"$artifact": "kinetic"},
                                x_column="time",
                                y_column="value",
                                label="Kinetic",
                                x_unit="raw",
                                y_unit="raw",
                            )
                        ],
                    ),
                ),
            ],
        )
        service.start_session_recording(sid)
        run = checked("energy-workflow", service.run_workflow(recipe["artifacts"][0]["path"], session_id=sid))
        plotted = run["data"]["steps"]["plot"]
        record = checked("recording", service.stop_session_recording(sid))
        workflow = json.loads(Path(record["workflow"]).read_text(encoding="utf8"))
        assert len(workflow["steps"]) == 3
        assert isinstance(workflow["steps"][2]["arguments"]["additional_curves"][0]["path"], dict)
        p = service.parameterize_workflow(
            record["workflow"],
            [
                dict(step_id="step1", path=["entity_id"], parameter="entity"),
                dict(step_id="step2", path=["entity_id"], parameter="entity"),
            ],
        )
        replay = checked("replay", service.run_workflow(p["artifacts"][0]["path"], dict(entity=1501), sid))
        for step, q in [("step1", "internal_energy"), ("step2", "kinetic_energy")]:
            comparisons["replay-" + q] = compare(replay["data"]["steps"][step], q, 1501)
            assert replay["data"]["steps"][step]["execution_mode"] == "visible_gui_scl_binout"
        assert originals == [fingerprint(p) for p in (source, model)]
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                cases=cases,
                source_unchanged=True,
                comparisons=comparisons,
                plot=str(Path(plotted["job_directory"]) / "plot.png"),
                scope="11 MATSUM scalar mappings at stored ID1500,101-step official fixture,LASSO cross-reader agreement;missing ID/absent hourglass reject;same owned GUI/no model association;two energy curves and ID1501 typed replay. No solver/unit certification or universal Binout-format coverage.",
            ),
        )
    finally:
        atomic_json(root / "closed.json", service.close_gui_session(sid, save_checkpoint=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "executable", "source"):
        p.add_argument("--" + name, required=True)
    accept(**vars(p.parse_args()))
