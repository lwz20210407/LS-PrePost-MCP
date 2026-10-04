"""Declarative typed workflows and session/native command recordings."""

import json
import os
import re
import uuid
from pathlib import Path

from .jobs import atomic_json, check_artifact, now
from .outcomes import normalize_outcome, result_value
from .sessions import NATIVE_ACTIONS, alive, process_identity
from .workflow_checks import POLICIES, evaluate_gate, validate_checks
from .workflow_runtime import compile_workflow, operation_route

GUI_ACTIONS = {
    "create_gui_segment_pressure",
    "create_gui_nonreflecting_boundary",
    "create_gui_segment_set",
    "create_gui_entity_set",
    "inspect_gui_entity_sets",
    "create_gui_spc",
    "set_gui_entity_visibility",
    "measure_gui_geometry",
    "render_gui_field",
    "export_gui_curve_plot",
    "export_gui_animation",
    "check_gui_keywords",
    "inspect_gui_menu",
    "check_gui_shell_quality",
    "check_gui_solid_quality",
    "combine_gui_selections",
    "save_gui_selection_buffer",
    "load_gui_selection_buffer",
    "select_gui_nodes_by_plane",
    "select_gui_entities",
    "select_gui_nodes_by_box",
    "select_gui_nodes_by_sphere",
    "renumber_gui_entities",
    "set_gui_display",
    "set_gui_part_visibility",
    "control_gui_animation",
    "execute_gui_command",
    "inspect_gui_mesh",
    "merge_gui_duplicate_nodes",
    "reverse_gui_shell_normals",
    "translate_gui_nodes",
    "set_gui_node_coordinates",
    "rotate_gui_nodes",
    "create_gui_nodes",
    "create_gui_elements",
    "inspect_gui_mesh_quality",
}
WORKFLOW_ACTIONS = (
    NATIVE_ACTIONS
    | GUI_ACTIONS
    | {
        "probe_dpf_runtime",
        "inspect_dpf_results",
        "export_dpf_result",
        "inspect_mesh_quality",
        "transform_mesh_deck",
        "merge_duplicate_mesh_nodes",
        "validate_model_references",
        "create_node_set_by_box",
        "create_tensile_shell_plate",
        "compose_keyword_deck",
        "update_keyword_fields",
        "update_keyword_table_row",
        "instantiate_installed_template",
        "extract_native_ascii_curve",
        "extract_native_binout_curve",
        "extract_native_stress",
        "extract_native_fields",
        "build_tensile_curves",
        "combine_history_curves",
        "convert_history_units",
        "assess_energy_balance",
        "native_energy_postprocess",
        "native_tensile_postprocess",
        "prepare_native_program",
        "execute_native_program",
        "create_native_macro",
        "run_native_macro",
        "process_curve",
        "open_model",
        "checkpoint",
        "new_model",
    }
)


def validate_steps(steps):
    if not isinstance(steps, list) or not 1 <= len(steps) <= 100:
        raise ValueError("Workflow requires 1..100 steps")
    names = set()
    for step in steps:
        if not isinstance(step, dict) or set(step) - {
            "id",
            "action",
            "arguments",
            "checks",
            "quality_policy",
        }:
            raise ValueError("Invalid workflow step")
        name = step.get("id")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name)
            or name in names
        ):
            raise ValueError("Step IDs must be unique identifiers")
        names.add(name)
        if not isinstance(step.get("action"), str) or step["action"] not in WORKFLOW_ACTIONS or not isinstance(step.get("arguments", {}), dict):
            raise ValueError("Unsupported workflow action")
        policy = step.get("quality_policy", "auto")
        if not isinstance(policy, str) or policy not in POLICIES:
            raise ValueError("quality_policy must be auto, require_pass or report_only")
        validate_checks(step.get("checks", []))


def resolve(value, parameters, results):
    if isinstance(value, list):
        return [resolve(v, parameters, results) for v in value]
    if not isinstance(value, dict):
        return value
    if "$param" in value:
        if set(value) != {"$param"} or value["$param"] not in parameters:
            raise ValueError("Missing/invalid workflow parameter")
        return parameters[value["$param"]]
    if "$artifact" in value:
        if set(value) - {"$artifact", "index"}:
            raise ValueError("Invalid artifact binding")
        source = results.get(value["$artifact"])
        index = value.get("index", 0)
        if source is None or type(index) is not int or index < 0 or index >= len(source.get("artifacts", [])):
            raise ValueError("Artifact binding must refer to an earlier successful step")
        return source["artifacts"][index]["path"]
    if "$result" in value:
        if (
            set(value) != {"$result", "path"}
            or value["$result"] not in results
            or not isinstance(value["path"], list)
        ):
            raise ValueError("Invalid result binding")
        return result_value(results[value["$result"]], value["path"])
    if any(str(k).startswith("$") for k in value):
        raise ValueError("Unknown workflow expression")
    return {k: resolve(v, parameters, results) for k, v in value.items()}


def set_parameter_binding(document, path, name):
    if (
        not isinstance(path, list)
        or not path
        or any(type(key) not in (str, int) or (type(key) is int and key < 0) for key in path)
        or not isinstance(name, str)
        or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name)
    ):
        raise ValueError("Invalid parameter binding")
    target = document
    for key in path[:-1]:
        target = target[key]
    original = target[path[-1]]
    target[path[-1]] = {"$param": name}
    return original


def recording_argument_links(template, results, path=()):
    """Preserve only explicit recipe dependencies, never infer links from equal values."""
    links = []
    if isinstance(template, dict):
        if "$param" in template:
            return links  # Parameter values are frozen; explicit reparameterization remains available.
        source = template.get("$result", template.get("$artifact"))
        if source is not None:
            result_path = (
                template["path"] if "$result" in template else ["artifacts", template.get("index", 0), "path"]
            )
            return [
                dict(
                    argument_path=list(path),
                    source_job_directory=results[source].get("job_directory"),
                    result_path=result_path,
                )
            ]
        for key, value in template.items():
            links.extend(recording_argument_links(value, results, (*path, key)))
    elif isinstance(template, list):
        for index, value in enumerate(template):
            links.extend(recording_argument_links(value, results, (*path, index)))
    return links


def restore_recording_links(step, links, positions, target_position):
    for link in links:
        source = link["source_job_directory"]
        if source not in positions or positions[source] >= target_position:
            raise ValueError("Recorded dependency has no earlier uniquely recorded source operation")
        binding = {"$result": "step" + str(positions[source] + 1), "path": link["result_path"]}
        path = link["argument_path"]
        if not path:
            step["arguments"] = binding
        else:
            target = step["arguments"]
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = binding


class WorkflowTools:
    def _recording_workflow_scope(self, session_id, workflow_id, begin):
        """Prevent compiling a recording before its workflow gate annotations arrive."""
        if not session_id or not re.fullmatch(r"[a-f0-9]{32}", session_id):
            return
        manager = self._session_manager()
        if not (manager.directory(session_id) / "session.json").is_file():
            return
        with manager.lock(session_id):
            meta = manager.read(session_id)
            record = meta.get("recording")
            if not record:
                return
            active = record.get("active_workflow")
            if begin:
                if active:
                    raise ValueError(
                        "Recording has an unfinished workflow; finish it or stop the interrupted recording for review"
                    )
                record["active_workflow"] = workflow_id
                record["workflow_owner"] = process_identity(os.getpid())
            elif active == workflow_id:
                record.pop("active_workflow")
                record.pop("workflow_owner", None)
            manager.save(session_id, meta)

    def _record_workflow_gate(
        self,
        session_id,
        result,
        checks,
        policy,
        gate,
        *,
        action=None,
        arguments=None,
        template=None,
        results=None,
    ):
        if not session_id or not re.fullmatch(r"[a-f0-9]{32}", session_id):
            return
        manager = self._session_manager()
        if not (manager.directory(session_id) / "session.json").is_file():
            return
        with manager.lock(session_id):
            if not manager.read(session_id).get("recording"):
                return
            if result.get("session_id") != session_id:
                # Native GUI actions journal themselves. Pure file/engineering
                # steps executed in this workflow also belong to its recording.
                manager.journal(
                    session_id,
                    dict(action=action or "workflow_unrecorded", parameters=arguments or {}, result=result),
                )
            if not result.get("job_directory"):
                return
            manager.journal(
                session_id,
                dict(
                    action="workflow_gate",
                    parameters=dict(
                        operation_job_directory=result["job_directory"],
                        checks=checks,
                        quality_policy=policy,
                        argument_links=recording_argument_links(template or {}, results or {}),
                    ),
                    result=dict(status="succeeded" if gate["passed"] else "failed", gate=gate),
                ),
            )

    def import_command_recording(
        self, path: str, units: str, recorded_model_index: int | None = None
    ) -> dict:
        """Compile recognized cfile operations into a typed GUI recipe. Model-qualified IDs require an explicit recorded model index mapped to the current model; mismatches/unknown/scripts block replay. Does not support multi-model recordings."""
        from .recording_compiler import compile_commands

        source = self.settings.input_path(path)
        compiled = compile_commands(
            source.read_text(encoding="utf-8-sig", errors="replace"), units, recorded_model_index
        )
        for step in compiled["steps"]:
            if step["action"] == "open_model":
                step["arguments"]["path"] = str(
                    self.settings.input_path(step["arguments"]["path"], base=source.parent)
                )
        directory, manifest = self.jobs.create(
            "import_command_recording",
            dict(source=str(source), units=units, recorded_model_index=recorded_model_index),
        )
        atomic_json(directory / "workflow.json", compiled)
        manifest.update(
            status="needs_review"
            if compiled["unrecognized_commands"] or not compiled["steps"]
            else "succeeded",
            data={
                "step_count": len(compiled["steps"]),
                "unrecognized_commands": compiled["unrecognized_commands"],
            },
            artifacts=[check_artifact(directory / "workflow.json", "json")],
            job_directory=str(directory),
            finished_at=now(),
        )
        atomic_json(directory / "job.json", manifest)
        return manifest

    def create_workflow(self, name: str, steps: list[dict], defaults: dict | None = None) -> dict:
        """Save typed steps with parameter/result bindings, optional checks and quality_policy. Known model checks require a true verdict by default; report_only explicitly opts out of that verdict, not explicit checks. No execution occurs here."""
        validate_steps(steps)
        if defaults is not None and not isinstance(defaults, dict):
            raise ValueError("Workflow defaults must be an object")
        if not name.strip() or len(name) > 120:
            raise ValueError("Invalid workflow name")
        directory, manifest = self.jobs.create("create_workflow", dict(name=name))
        workflow = dict(schema_version=1, name=name, steps=steps, defaults=defaults or {})
        atomic_json(directory / "workflow.json", workflow)
        manifest.update(
            status="succeeded",
            finished_at=now(),
            job_directory=str(directory),
            data={"step_count": len(steps)},
            artifacts=[check_artifact(directory / "workflow.json", "json")],
        )
        atomic_json(directory / "job.json", manifest)
        return manifest

    def inspect_workflow(self, path: str, parameters: dict | None = None, session_id: str | None = None) -> dict:
        """Preview a workflow without execution, jobs or GUI access. Report module/routes, dependencies, argument/check errors and deferred result bindings. ready means static composition only, not native support, model validity or available input files."""
        source = self.settings.input_path(path)
        workflow = json.loads(source.read_text(encoding="utf8"))
        return compile_workflow(self, workflow, parameters, session_id)

    def run_workflow(self, path: str, parameters: dict | None = None, session_id: str | None = None) -> dict:
        """Run typed steps with separate execution and quality gates. Known model checks fail closed by default; explicit checks support finite numeric/boolean predicates. Stop before dependent steps, retain evidence/checkpoints and never automatically replay or roll back."""
        source = self.settings.input_path(path)
        workflow = json.loads(source.read_text(encoding="utf8"))
        preflight = compile_workflow(self, workflow, parameters, session_id)
        if not preflight["ready"]:
            raise ValueError("Workflow preflight failed: " + json.dumps(preflight["errors"], ensure_ascii=False))
        steps = workflow["steps"]
        params = {**workflow.get("defaults", {}), **(parameters or {})}
        resolved_checks = {step["id"]: step["resolved_checks"] for step in preflight["steps"]}
        directory, manifest = self.jobs.create(
            "run_workflow", dict(path=str(source), parameters=params, session_id=session_id)
        )
        results, outcomes, gates = {}, {}, {}
        completed, attempted = 0, 0
        failed_step, failure_phase = None, None
        remaining = [step["id"] for step in steps]
        atomic_json(directory / "definition.json", workflow)
        atomic_json(directory / "preflight.json", preflight)
        manifest.update(status="running", started_at=now())
        atomic_json(directory / "job.json", manifest)
        try:
            failure_phase = "recording_setup"
            self._recording_workflow_scope(session_id, manifest["job_id"], True)
            initial = workflow.get("initial_model")
            if initial and session_id:
                failure_phase = "initial_model"
                opened = self.open_in_gui_session(
                    session_id, initial, workflow.get("initial_file_type", "keyword")
                )
                if opened["status"] != "succeeded":
                    raise RuntimeError("Cannot restore recording initial model")
            for step in steps:
                failed_step = step["id"]
                remaining = remaining[1:]
                failure_phase = "argument_resolution"
                action = step["action"]
                arguments = resolve(step.get("arguments", {}), params, results)
                failure_phase = "execution"
                attempted += 1
                try:
                    result = operation_route(self, action, session_id).execute(self, arguments, session_id)
                    if not isinstance(result, dict):
                        raise ValueError("Operation result must be a JSON object")
                    json.dumps(result, allow_nan=False)
                except Exception as exc:
                    result = dict(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
                results[step["id"]] = result
                outcome = normalize_outcome(action, result)
                outcomes[step["id"]] = outcome.to_dict()
                gate = evaluate_gate(
                    outcome, result, resolved_checks[step["id"]], step.get("quality_policy", "auto")
                )
                gates[step["id"]] = gate
                self._record_workflow_gate(
                    session_id,
                    result,
                    resolved_checks[step["id"]],
                    step.get("quality_policy", "auto"),
                    gate,
                    action=action,
                    arguments=arguments,
                    template=step.get("arguments", {}),
                    results=results,
                )
                atomic_json(directory / "steps.json", results)
                atomic_json(directory / "outcomes.json", outcomes)
                atomic_json(directory / "gates.json", gates)
                failure_phase = "quality_gate" if outcome.execution_accepted else "execution"
                if not gate["passed"]:
                    raise RuntimeError(
                        "Workflow stopped at step " + step["id"] + ": " + ", ".join(gate["reasons"])
                    )
                completed += 1
            failed_step, failure_phase = None, None
            manifest.update(status="succeeded")
        except Exception as exc:
            manifest.update(
                status="failed",
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            try:
                self._record_workflow_gate(
                    session_id,
                    dict(status="failed", error=manifest["error"]),
                    [],
                    "auto",
                    dict(passed=False),
                    action="workflow_failure",
                    arguments=dict(failed_step=failed_step, failure_phase=failure_phase),
                )
            except Exception as record_error:
                manifest["warnings"].append("Could not journal workflow failure: " + str(record_error))
        finally:
            try:
                self._recording_workflow_scope(session_id, manifest["job_id"], False)
            except Exception as exc:
                manifest.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
                failure_phase = "recording_finalization"
        manifest["data"] = dict(
            preflight=preflight,
            steps=results,
            outcomes=outcomes,
            gates=gates,
            completed_steps=completed,
            attempted_steps=attempted,
            failed_step=failed_step,
            failure_phase=failure_phase,
            skipped_steps=remaining,
            baseline_checkpoints={
                key: r["baseline_checkpoint"]
                for key, r in results.items()
                if isinstance(r.get("baseline_checkpoint"), str)
            },
            automatic_replay=False,
            automatic_rollback=False,
        )
        for name, content in (("steps.json", results), ("outcomes.json", outcomes), ("gates.json", gates)):
            atomic_json(directory / name, content)
        manifest["artifacts"] = [
            check_artifact(directory / name, "json") for name in ("steps.json", "outcomes.json", "gates.json")
        ]
        manifest.update(finished_at=now(), job_directory=str(directory))
        atomic_json(directory / "job.json", manifest)
        return manifest

    def start_session_recording(self, session_id: str) -> dict:
        """Start capturing managed operations and native lspost.cfile bytes in an owned GUI session. Stores a baseline checkpoint where possible."""
        manager = self._session_manager()
        meta = manager.read(session_id)
        if meta.get("recording"):
            raise ValueError("Recording is already active")
        initial = None
        initial_type = meta["model_kind"]
        if initial_type == "d3plot":
            initial = meta.get("staged_model")
        if meta["model_kind"] == "keyword":
            info = self.gui_session_action(session_id, "inspect_model", {})
            if info["status"] != "succeeded":
                return info
            if info["status"] == "succeeded" and info.get("data", {}).get("counts", {}).get("nodes", 0) > 0:
                snapshot = self.checkpoint_gui_session(session_id)
                if snapshot["status"] != "succeeded":
                    return snapshot
                initial = snapshot["artifacts"][0]["path"]
        root = manager.directory(session_id)
        native = root / "lspost.cfile"
        journal = root / "journal.jsonl"
        with manager.lock(session_id):
            meta = manager.read(session_id)
            record = dict(
                id=uuid.uuid4().hex,
                started_at=now(),
                initial_model=initial,
                initial_file_type=initial_type,
                native_offset=native.stat().st_size if native.exists() else None,
                journal_offset=journal.stat().st_size if journal.exists() else 0,
            )
            meta["recording"] = record
            manager.save(session_id, meta)
        return dict(session_id=session_id, recording=record, native_available=native.exists())

    def stop_session_recording(self, session_id: str) -> dict:
        """Finish a recording, preserving resolved workflow gates and raw cfile. Failed/interrupted records return needs_review and cannot replay. A still-running recorded workflow must finish first."""
        manager = self._session_manager()
        with manager.lock(session_id):
            meta = manager.read(session_id)
            record = meta.get("recording")
            if not record:
                raise ValueError("No active recording")
            review_reasons = []
            if record.get("active_workflow"):
                owner = record.get("workflow_owner")
                if owner is None or alive(owner):
                    raise ValueError(
                        "A recorded workflow is still executing; finish it before stopping recording"
                    )
                review_reasons.append(
                    dict(
                        reason="Recorded workflow owner exited before gate finalization",
                        workflow_id=record["active_workflow"],
                    )
                )
            root = manager.directory(session_id)
            directory = root / "recordings" / record["id"]
            directory.mkdir(parents=True)
            journal = root / "journal.jsonl"
            entries = []
            if journal.exists():
                with journal.open("rb") as f:
                    f.seek(record["journal_offset"])
                    entries = [json.loads(s) for s in f.read().decode("utf8").splitlines() if s.strip()]
            steps = []
            operation_positions = {}
            for entry in entries:
                if not normalize_outcome(entry["action"], entry["result"]).execution_accepted:
                    review_reasons.append(
                        dict(
                            reason="Failed managed operation or gate",
                            action=entry["action"],
                            status=entry["result"]["status"],
                        )
                    )
                if entry["action"] == "workflow_gate":
                    annotations = entry["parameters"]
                    target = annotations.get("operation_job_directory")
                    if target not in operation_positions:
                        raise ValueError("Recorded gate has no uniquely identified native operation")
                    target_step = steps[operation_positions[target]]
                    target_step["quality_policy"] = annotations["quality_policy"]
                    target_step["checks"] = annotations["checks"]
                    try:
                        restore_recording_links(
                            target_step,
                            annotations.get("argument_links", []),
                            operation_positions,
                            operation_positions[target],
                        )
                    except (ValueError, KeyError, IndexError, TypeError) as exc:
                        review_reasons.append(dict(reason="Unresolved recorded dependency", detail=str(exc)))
                    continue
                action = "open_model" if entry["action"] == "open" else entry["action"]
                if action not in WORKFLOW_ACTIONS:
                    review_reasons.append(dict(reason="Unsupported recorded operation", action=action))
                    continue
                steps.append(
                    dict(id="step" + str(len(steps) + 1), action=action, arguments=entry["parameters"])
                )
                if action in ("create_gui_entity_set", "create_gui_segment_set") and entry["parameters"].get("selection_job"):
                    source = entry["parameters"]["selection_job"]
                    if source not in operation_positions:
                        review_reasons.append(dict(reason="Entity-set selection source was not recorded earlier", action=action))
                    else:
                        steps[-1]["arguments"]["selection_job"] = {
                            "$result": "step" + str(operation_positions[source] + 1), "path": ["job_directory"]}
                directory_id = entry["result"].get("job_directory")
                if directory_id:
                    if directory_id in operation_positions:
                        raise ValueError("Repeated native operation identity in recording")
                    operation_positions[directory_id] = len(steps) - 1
            if steps:
                validate_steps(steps)
            workflow = dict(
                schema_version=1,
                name="Session recording",
                defaults={},
                steps=steps,
                initial_model=record["initial_model"],
                initial_file_type=record.get("initial_file_type", "keyword"),
                requires_gui_session=True,
                recording_scope="managed_GUI_operations_and_typed_workflow_steps; manual GUI edits retained only in raw cfile",
            )
            if review_reasons:
                workflow["unrecognized_commands"] = review_reasons
            atomic_json(directory / "workflow.json", workflow)
            native = root / "lspost.cfile"
            raw = b""
            if record["native_offset"] is not None and native.exists():
                with native.open("rb") as f:
                    f.seek(record["native_offset"])
                    raw = f.read()
            (directory / "native.cfile").write_bytes(raw)
            meta["recording"] = None
            manager.save(session_id, meta)
            report = dict(
                status="needs_review" if review_reasons else "succeeded",
                session_id=session_id,
                recording_id=record["id"],
                managed_steps=len(steps),
                native_bytes=len(raw),
                workflow=str(directory / "workflow.json"),
                raw_commands=str(directory / "native.cfile"),
                raw_replay_status="Requires command import/review; managed recipe does not claim capture of arbitrary GUI semantics",
                review_reasons=review_reasons,
            )
            atomic_json(directory / "recording.json", report)
            return report

    def parameterize_workflow(self, path: str, bindings: list[dict]) -> dict:
        """Parameterize JSON paths in step arguments or checks (section), preserving policy and review blockers. No string/code substitution."""
        source = self.settings.input_path(path)
        workflow = json.loads(source.read_text(encoding="utf8"))
        validate_steps(workflow["steps"])
        if not bindings or len(bindings) > 100:
            raise ValueError("Provide 1..100 explicit bindings")
        defaults = dict(workflow.get("defaults", {}))
        for binding in bindings:
            if set(binding) - {"step_id", "path", "parameter", "section"} or not {
                "step_id",
                "path",
                "parameter",
            } <= set(binding):
                raise ValueError("Invalid binding fields")
            section = binding.get("section", "arguments")
            if section not in ("arguments", "checks"):
                raise ValueError("Parameter section must be arguments or checks")
            found = [s for s in workflow["steps"] if s["id"] == binding["step_id"]]
            if len(found) != 1:
                raise ValueError("Unknown step ID")
            default = set_parameter_binding(found[0][section], binding["path"], binding["parameter"])
            if binding["parameter"] in defaults and defaults[binding["parameter"]] != default:
                raise ValueError("Conflicting defaults for shared parameter")
            defaults[binding["parameter"]] = default
        workflow["defaults"] = defaults
        result = self.create_workflow(workflow["name"], workflow["steps"], defaults)
        target = Path(result["artifacts"][0]["path"])
        updated = json.loads(target.read_text())
        for key in (
            "initial_model",
            "initial_file_type",
            "requires_gui_session",
            "recording_scope",
            "unrecognized_commands",
            "output_policy",
            "recorded_model_index",
        ):
            if key in workflow:
                updated[key] = workflow[key]
        atomic_json(target, updated)
        result["artifacts"] = [check_artifact(target, "json")]
        atomic_json(Path(result["job_directory"]) / "job.json", result)
        return result
