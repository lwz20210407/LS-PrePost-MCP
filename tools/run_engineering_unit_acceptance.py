"""Synthetic mixed-unit force/displacement -> stress/strain/work acceptance. No native software."""

import argparse
import csv
import json
import uuid
from pathlib import Path

import numpy as np

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace):
    root = Path(workspace).resolve() / ("engineering-units-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    service = Service(Settings(root))
    source_rows = dict(
        force=[(0, 0), (1000, 1), (2000, 2)],
        moving=[(0, 0), (1, 0.1), (2, 0.2)],
        reference=[(0, 0), (1000, 0.1), (2000, 0.2)],
    )
    paths = {}
    originals = {}
    for name, rows in source_rows.items():
        path = root / (name + ".csv")
        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time", "value"])
            writer.writerows(rows)
        paths[name] = str(path)
        originals[path] = path.read_bytes()
    template = root / "workflow.json"
    template.write_bytes(
        (Path(__file__).resolve().parents[1] / "examples/workflows/declared_unit_tensile.json").read_bytes()
    )
    params = dict(
        force_curve=paths["force"],
        force_unit="kN",
        force_time_unit="ms",
        moving_curve=paths["moving"],
        moving_unit="cm",
        moving_time_unit="s",
        reference_curve=paths["reference"],
        reference_unit="mm",
        reference_time_unit="ms",
        area_mm2=10,
        gauge_length_mm=10,
    )
    result = service.run_workflow(str(template), params)
    atomic_json(root / "accepted.json", result)
    assert result["status"] == "succeeded", result.get("error")
    tensile = result["data"]["steps"]["tensile"]
    with Path(tensile["artifacts"][0]["path"]).open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert np.allclose([float(r["engineering_strain"]) for r in rows], [0, 0.09, 0.18])
    assert np.allclose([float(r["engineering_stress_MPa"]) for r in rows], [0, 100, 200])
    assert np.isclose(tensile["data"]["work_J"], 1.8)
    assert result["data"]["steps"]["relative"]["data"]["unit_contract"]["dimensional_compatibility_checked"]
    rejected = service.run_workflow(str(template), dict(params, force_unit="MPa"))
    atomic_json(root / "rejected.json", rejected)
    assert rejected["status"] == "failed" and rejected["data"]["failed_step"] == "force"
    assert rejected["data"]["skipped_steps"] == ["relative", "tensile"]
    assert all(p.read_bytes() == data for p, data in originals.items())
    report = dict(
        status="succeeded",
        scope="Synthetic Python unit/curve math; no LS-PrePost or physical model validation",
        converted_then_aligned=True,
        stress_strain_work_truth=True,
        incompatible_units_stop_workflow=True,
        source_files_unchanged=True,
    )
    atomic_json(root / "acceptance.json", report)
    print(json.dumps(dict(report, evidence_directory=str(root)), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    accept(args.workspace)
