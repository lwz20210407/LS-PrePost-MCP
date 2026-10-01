import csv
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


def tensile_recipe(tmp_path):
    force, displacement = tmp_path / "force.csv", tmp_path / "u.csv"
    force.write_text("time,value\n0,0\n1,100\n2,200\n")
    displacement.write_text("time,value\n0,0\n1,1\n2,2\n")
    service = Service(Settings(tmp_path))
    result = service.create_workflow(
        "Parameter study of declared area",
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
            )
        ],
    )
    return service, result["artifacts"][0]["path"]


def test_engineering_sweep_has_independent_outputs_known_values_and_frozen_recipe(tmp_path):
    service, path = tensile_recipe(tmp_path)
    outputs = {
        "peak_MPa": dict(step_id="tensile", path=["data", "peak_engineering_stress_MPa"]),
        "work_J": dict(step_id="tensile", path=["data", "work_J"]),
    }
    result = service.run_workflow_sweep(
        path, [dict(id="A", parameters=dict(area=10)), dict(id="B", parameters=dict(area=20))], outputs
    )
    assert result["status"] == "succeeded", result
    cases = result["data"]["cases"]
    assert [case["outputs"]["peak_MPa"] for case in cases] == [20, 10]
    assert [case["outputs"]["work_J"] for case in cases] == [0.2, 0.2]
    assert cases[0]["job_directory"] != cases[1]["job_directory"]
    root = Path(result["job_directory"])
    assert json.loads((root / "workflow.json").read_text()) == json.loads(Path(path).read_text())
    with (root / "summary.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [float(row["output.peak_MPa"]) for row in rows] == [20, 10]
    assert result["data"]["completed_cases"] == 2
    assert not result["data"]["automatic_retry"]


def test_later_case_missing_parameter_prevents_all_execution(tmp_path, monkeypatch):
    service, path = tensile_recipe(tmp_path)
    calls = []
    monkeypatch.setattr(service, "run_workflow", lambda *a, **kw: calls.append(1))
    before = set((tmp_path / "jobs").iterdir())
    with pytest.raises(ValueError, match="preflight"):
        service.run_workflow_sweep(
            path, [dict(id="A", parameters=dict(area=10)), dict(id="B", parameters={})]
        )
    assert not calls and set((tmp_path / "jobs").iterdir()) == before


def test_runtime_engineering_failure_stops_remaining_cases_and_preserves_earlier_results(tmp_path):
    service, path = tensile_recipe(tmp_path)
    result = service.run_workflow_sweep(
        path,
        [
            dict(id=name, parameters=dict(area=area))
            for name, area in [("good", 10), ("bad", -1), ("skip", 20)]
        ],
    )
    assert result["status"] == "failed"
    assert [c["status"] for c in result["data"]["cases"]] == ["succeeded", "failed", "skipped"]
    assert result["data"]["skipped_cases"] == ["skip"]
    first = result["data"]["cases"][0]
    assert Path(first["job_directory"], "job.json").is_file()


def test_missing_summary_value_is_a_failure_not_empty_success(tmp_path):
    service, path = tensile_recipe(tmp_path)
    result = service.run_workflow_sweep(
        path,
        [dict(id="A", parameters=dict(area=10)), dict(id="B", parameters=dict(area=20))],
        {"missing": dict(step_id="tensile", path=["data", "nonexistent"])},
    )
    assert result["status"] == "failed" and result["data"]["skipped_cases"] == ["B"]
    child = result["data"]["cases"][0]
    assert service.read_job(child["job_id"])["status"] == "succeeded"


def test_gui_study_requires_explicit_baseline_before_any_mutation(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))
    recipe = service.create_workflow(
        "No cumulative edits",
        [
            dict(
                id="edit",
                action="translate_gui_nodes",
                arguments=dict(node_ids=[1], offset=[1, 0, 0], units="mm"),
            )
        ],
    )
    calls = []
    monkeypatch.setattr(service, "run_workflow", lambda *a, **kw: calls.append(1))
    with pytest.raises(ValueError, match="baseline|initial_model"):
        service.run_workflow_sweep(
            recipe["artifacts"][0]["path"], [dict(id="A", parameters={})], session_id="s"
        )
    assert not calls


@pytest.mark.parametrize(
    "cases",
    [
        [],
        [dict(id="same", parameters=dict(area=10))] * 2,
        [dict(id="A", parameters=dict(area=10))] * 21,
        [dict(id="../invalid", parameters=dict(area=10))],
    ],
)
def test_case_names_and_bounds_are_checked(tmp_path, cases):
    service, path = tensile_recipe(tmp_path)
    with pytest.raises(ValueError):
        service.run_workflow_sweep(path, cases)
