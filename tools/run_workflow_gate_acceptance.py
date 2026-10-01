"""Reproducible real file-backend gate acceptance; does NOT launch LS-PrePost.

Uses only freshly generated synthetic meshes/curves beneath --workspace.
Native GUI gate acceptance is a separate opt-in activity.
"""

import argparse
import json
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace):
    root = Path(workspace).resolve() / ("gate-acceptance-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    service = Service(Settings(root))
    results = {}
    for label, collapsed in [("good_mesh", False), ("bad_mesh", True)]:
        source = root / (label + ".k")
        source.write_text(
            "*KEYWORD\n*NODE\n1,0,0,0\n2,"
            + ("0" if collapsed else "1")
            + ",0,0\n3,1,1,0\n4,0,1,0\n*ELEMENT_SHELL\n1,1,1,2,3,4\n*END\n"
        )
        original = source.read_bytes()
        workflow = service.create_workflow(
            label,
            [
                dict(
                    id="check", action="inspect_mesh_quality", arguments=dict(model=str(source), units="mm")
                ),
                dict(
                    id="edit",
                    action="transform_mesh_deck",
                    arguments=dict(
                        model=str(source),
                        operation="translate",
                        values=[1, 0, 0],
                        units="mm",
                        native_check=False,
                    ),
                ),
            ],
        )
        result = service.run_workflow(workflow["artifacts"][0]["path"])
        assert result["status"] == ("failed" if collapsed else "succeeded"), result
        assert ("edit" in result["data"]["steps"]) is (not collapsed)
        assert source.read_bytes() == original
        results[label] = result
    example = Path(__file__).resolve().parents[1] / "examples/workflows/energy_screening_gate.json"
    template = root / "energy-workflow.json"
    template.write_bytes(example.read_bytes())
    for label, ke, ie in [("good_energy", 1, 100), ("excess_kinetic", 10, 100), ("undefined_ratio", 1, 0)]:
        paths = {}
        for name, value in [("kinetic", ke), ("internal", ie), ("hourglass", 1)]:
            path = root / (label + "-" + name + ".csv")
            path.write_text("time,value\n" + "".join(f"{t},{value}\n" for t in range(3)))
            paths[name + "_curve"] = str(path)
        result = service.run_workflow(
            str(template), dict(**paths, units="J", kinetic_ratio_limit=0.05, hourglass_ratio_limit=0.05)
        )
        passed = label == "good_energy"
        assert result["status"] == ("succeeded" if passed else "failed"), result
        assert ("selected_energy_sum" in result["data"]["steps"]) is passed
        results[label] = result
    summary = dict(
        mode="synthetic_file_backends",
        native_software_launched=False,
        directory=str(root),
        cases={
            name: dict(
                status=r["status"],
                completed_steps=r["data"]["completed_steps"],
                skipped_steps=r["data"]["skipped_steps"],
                job_directory=r["job_directory"],
            )
            for name, r in results.items()
        },
    )
    atomic_json(root / "acceptance.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace", required=True, help="Explicit directory for fresh synthetic acceptance outputs"
    )
    print(json.dumps(accept(parser.parse_args().workspace), indent=2))
