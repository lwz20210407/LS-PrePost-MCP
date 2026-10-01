"""Bounded, sequential parameter studies over the existing verified workflow runner."""

import csv
import json
import re

from .jobs import atomic_json, check_artifact, now
from .outcomes import result_value
from .workflow_checks import scalar
from .workflow_runtime import compile_workflow


def validate_study(workflow, cases, outputs, session_id):
    if not isinstance(cases, list) or not 1 <= len(cases) <= 20:
        raise ValueError("A parameter study requires 1..20 explicit cases")
    names = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "parameters"}:
            raise ValueError("Each case requires id and parameters")
        name = case["id"]
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name)
            or name in names
            or not isinstance(case["parameters"], dict)
        ):
            raise ValueError("Cases require unique identifier names and parameter objects")
        names.add(name)
    if not isinstance(outputs, dict) or len(outputs) > 32:
        raise ValueError("outputs must map at most 32 names to step_id/path selectors")
    steps = workflow["steps"]
    step_ids = {s["id"] for s in steps}
    for name, spec in outputs.items():
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name)
            or not isinstance(spec, dict)
            or set(spec) != {"step_id", "path"}
            or not isinstance(spec["step_id"], str)
            or spec["step_id"] not in step_ids
            or not isinstance(spec["path"], list)
            or not 1 <= len(spec["path"]) <= 16
            or any(not (isinstance(k, str) and k or type(k) is int and k >= 0) for k in spec["path"])
        ):
            raise ValueError("Invalid study output selector")
    if (
        session_id
        and not workflow.get("initial_model")
        and steps[0]["action"] not in {"open_model", "new_model"}
    ):
        raise ValueError(
            "GUI parameter studies require a recorded initial_model or first open_model/new_model step; cumulative edits are not a parameter study"
        )


class WorkflowSweepTools:
    def run_workflow_sweep(
        self, path: str, cases: list[dict], outputs: dict | None = None, session_id: str | None = None
    ) -> dict:
        """Run 1..20 explicit parameter cases sequentially, preflighting every case first. GUI cases must reset/reopen an explicit baseline. Stop at the first execution, quality or output-selection failure; no retries/rollback/resume. Outputs map names to {step_id,path} finite scalar result selectors. Return a case index, CSV, child job paths and skipped cases; this does not launch a solver or infer engineering parameters."""
        source = self.settings.input_path(path)
        workflow = json.loads(source.read_text(encoding="utf8"))
        if not isinstance(cases, list) or not 1 <= len(cases) <= 20:
            raise ValueError("A parameter study requires 1..20 explicit cases")
        # Check schema and each parameter set before creating a study or changing a model.
        previews = []
        for case in cases:
            if not isinstance(case, dict) or not isinstance(case.get("parameters"), dict):
                raise ValueError("Each case requires a parameter object")
            preview = compile_workflow(self, workflow, case["parameters"], session_id)
            if not preview["ready"]:
                raise ValueError(
                    "Case " + str(case.get("id")) + " preflight failed: " + json.dumps(preview["errors"])
                )
            previews.append(preview)
        outputs = {} if outputs is None else outputs
        validate_study(workflow, cases, outputs, session_id)
        directory, manifest = self.jobs.create(
            "run_workflow_sweep", dict(path=str(source), cases=cases, outputs=outputs, session_id=session_id)
        )
        frozen = directory / "workflow.json"
        atomic_json(frozen, workflow)
        atomic_json(directory / "preflight.json", previews)
        rows = [
            dict(
                case_id=case["id"],
                status="skipped",
                completed_steps=0,
                job_id=None,
                job_directory=None,
                outputs={},
            )
            for case in cases
        ]
        manifest.update(status="running", started_at=now(), job_directory=str(directory))

        def persist():
            manifest["data"] = dict(
                cases=rows,
                automatic_retry=False,
                automatic_rollback=False,
                completed_cases=sum(row["status"] == "succeeded" for row in rows),
                skipped_cases=[row["case_id"] for row in rows if row["status"] == "skipped"],
            )
            atomic_json(directory / "cases.json", rows)
            atomic_json(directory / "job.json", manifest)

        persist()
        for case, row in zip(cases, rows, strict=True):
            row["status"] = "running"
            persist()
            try:
                result = self.run_workflow(str(frozen), parameters=case["parameters"], session_id=session_id)
                row.update(
                    status=result["status"],
                    job_id=result.get("job_id"),
                    job_directory=result.get("job_directory"),
                    completed_steps=result.get("data", {}).get("completed_steps", 0),
                )
                if result["status"] != "succeeded":
                    raise RuntimeError("Child workflow did not pass execution and quality gates")
                for name, spec in outputs.items():
                    value = result_value(result["data"]["steps"][spec["step_id"]], spec["path"])
                    if not scalar(value):
                        raise ValueError("Study output must be a finite JSON scalar: " + name)
                    row["outputs"][name] = value
            except Exception as exc:
                row.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
                manifest.update(status="failed", error=row["error"])
                persist()
                break
            persist()
        else:
            manifest["status"] = "succeeded"
        summary = directory / "summary.csv"
        fields = ["case_id", "status", "completed_steps", "job_id", "job_directory"] + [
            "output." + name for name in outputs
        ]
        with summary.open("w", encoding="utf8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        **{key: row[key] for key in fields[:5]},
                        **{"output." + k: v for k, v in row["outputs"].items()},
                    }
                )
        with summary.open(encoding="utf8", newline="") as stream:
            table = list(csv.reader(stream))
        if (
            table[0] != fields
            or len(table) != len(cases) + 1
            or any(len(row) != len(fields) for row in table)
        ):
            raise ValueError("Case summary CSV readback failed")
        manifest.update(
            finished_at=now(),
            artifacts=[
                check_artifact(directory / name, "case_summary_csv" if name.endswith("csv") else "json")
                for name in ("cases.json", "summary.csv", "workflow.json", "preflight.json")
            ],
        )
        persist()
        return manifest
