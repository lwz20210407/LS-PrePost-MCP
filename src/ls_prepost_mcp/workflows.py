"""Declarative typed workflows and session/native command recordings."""

import json
import re
import uuid
from pathlib import Path

from .jobs import atomic_json, check_artifact, now
from .sessions import NATIVE_ACTIONS

GUI_ACTIONS = {
    "check_gui_keywords",
    "inspect_gui_menu",
    "check_gui_shell_quality",
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
    "rotate_gui_nodes",
    "create_gui_nodes",
    "create_gui_elements",
    "inspect_gui_mesh_quality",
}
WORKFLOW_ACTIONS = (
    NATIVE_ACTIONS
    | GUI_ACTIONS
    | {
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
        if not isinstance(step, dict) or set(step) - {"id", "action", "arguments"}:
            raise ValueError("Invalid workflow step")
        name = step.get("id")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name)
            or name in names
        ):
            raise ValueError("Step IDs must be unique identifiers")
        names.add(name)
        if step.get("action") not in WORKFLOW_ACTIONS or not isinstance(step.get("arguments", {}), dict):
            raise ValueError("Unsupported workflow action")


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
        current = results[value["$result"]]
        for key in value["path"]:
            if not isinstance(key, (str, int)):
                raise ValueError("Invalid result selector")
            current = current[key]
        return current
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


class WorkflowTools:
    def import_command_recording(self, path: str, units: str) -> dict:
        """Compile recognized recorded cfile operations into a typed GUI recipe; unknown/script/system commands block replay and are listed for review."""
        from .recording_compiler import compile_commands

        source = self.settings.input_path(path)
        compiled = compile_commands(source.read_text(encoding="utf-8-sig", errors="replace"), units)
        for step in compiled["steps"]:
            if step["action"] == "open_model":
                step["arguments"]["path"] = str(
                    self.settings.input_path(step["arguments"]["path"], base=source.parent)
                )
        directory, manifest = self.jobs.create(
            "import_command_recording", dict(source=str(source), units=units)
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
        """Save a declarative sequence of typed tools with $param/$artifact/$result bindings. Does not execute code or commands."""
        validate_steps(steps)
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

    def run_workflow(self, path: str, parameters: dict | None = None, session_id: str | None = None) -> dict:
        """Run a saved typed workflow, stopping at the first failed step. Native GUI actions can reuse a supplied persistent session; file workflows bind explicit prior artifacts."""
        source = self.settings.input_path(path)
        workflow = json.loads(source.read_text(encoding="utf8"))
        if workflow.get("schema_version") != 1 or workflow.get("unrecognized_commands"):
            raise ValueError("Workflow requires review or has unsupported schema")
        steps = workflow["steps"]
        validate_steps(steps)
        if workflow.get("requires_gui_session") and not session_id:
            raise ValueError("This recording requires a persistent GUI session")
        params = {**workflow.get("defaults", {}), **(parameters or {})}
        directory, manifest = self.jobs.create(
            "run_workflow", dict(path=str(source), parameters=params, session_id=session_id)
        )
        results = {}
        atomic_json(directory / "definition.json", workflow)
        try:
            initial = workflow.get("initial_model")
            if initial and session_id:
                opened = self.open_in_gui_session(
                    session_id, initial, workflow.get("initial_file_type", "keyword")
                )
                if opened["status"] != "succeeded":
                    raise RuntimeError("Cannot restore recording initial model")
            for step in steps:
                action = step["action"]
                arguments = resolve(step.get("arguments", {}), params, results)
                if action == "new_model":
                    if not session_id:
                        raise ValueError("new_model requires a persistent GUI session")
                    result = self.reset_gui_session(session_id, **arguments)
                elif action == "open_model":
                    if not session_id:
                        raise ValueError("open_model requires a persistent session")
                    result = self.open_in_gui_session(session_id, **arguments)
                elif action == "checkpoint":
                    if not session_id:
                        raise ValueError("checkpoint requires a persistent session")
                    result = self.checkpoint_gui_session(session_id)
                elif action in GUI_ACTIONS:
                    if not session_id:
                        raise ValueError("GUI controls require a persistent session")
                    result = getattr(self, action)(session_id=session_id, **arguments)
                elif session_id and action in NATIVE_ACTIONS:
                    result = self.gui_session_action(session_id, action, arguments)
                else:
                    result = getattr(self, action)(**arguments)
                results[step["id"]] = result
                atomic_json(directory / "steps.json", results)
                if isinstance(result, dict) and result.get("status") in (
                    "failed",
                    "partial",
                    "uncertain",
                    "needs_review",
                    "completed_unverified",
                ):
                    raise RuntimeError("Workflow stopped at step " + step["id"])
            manifest.update(status="succeeded", data={"steps": results, "completed_steps": len(results)})
            manifest["artifacts"] = [check_artifact(directory / "steps.json", "json")]
        except Exception as exc:
            manifest.update(
                status="failed",
                data={"steps": results, "completed_steps": len(results)},
                error={"type": type(exc).__name__, "message": str(exc)},
            )
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
        """Finish a recording. Managed operations become a typed replay recipe; raw GUI commands remain separately preserved for review, not silently executed."""
        manager = self._session_manager()
        with manager.lock(session_id):
            meta = manager.read(session_id)
            record = meta.get("recording")
            if not record:
                raise ValueError("No active recording")
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
            for entry in entries:
                if entry["result"]["status"] != "succeeded":
                    raise ValueError(
                        "Recording contains a failed managed operation; review it before compiling"
                    )
                action = "open_model" if entry["action"] == "open" else entry["action"]
                if action not in WORKFLOW_ACTIONS:
                    raise ValueError("Recording contains unsupported operation")
                steps.append(
                    dict(id="step" + str(len(steps) + 1), action=action, arguments=entry["parameters"])
                )
            workflow = dict(
                schema_version=1,
                name="Session recording",
                defaults={},
                steps=steps,
                initial_model=record["initial_model"],
                initial_file_type=record.get("initial_file_type", "keyword"),
                requires_gui_session=True,
                recording_scope="managed_operations_only; manual GUI edits are retained only in raw cfile",
            )
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
                session_id=session_id,
                recording_id=record["id"],
                managed_steps=len(steps),
                native_bytes=len(raw),
                workflow=str(directory / "workflow.json"),
                raw_commands=str(directory / "native.cfile"),
                raw_replay_status="Requires command import/review; managed recipe does not claim capture of arbitrary GUI semantics",
            )
            atomic_json(directory / "recording.json", report)
            return report

    def parameterize_workflow(self, path: str, bindings: list[dict]) -> dict:
        """Replace explicit JSON paths in step arguments with named parameters, retaining original values as defaults. No string/code substitution."""
        source = self.settings.input_path(path)
        workflow = json.loads(source.read_text(encoding="utf8"))
        validate_steps(workflow["steps"])
        if not bindings or len(bindings) > 100:
            raise ValueError("Provide 1..100 explicit bindings")
        defaults = dict(workflow.get("defaults", {}))
        for binding in bindings:
            if set(binding) != {"step_id", "path", "parameter"}:
                raise ValueError("Invalid binding fields")
            found = [s for s in workflow["steps"] if s["id"] == binding["step_id"]]
            if len(found) != 1:
                raise ValueError("Unknown step ID")
            default = set_parameter_binding(found[0]["arguments"], binding["path"], binding["parameter"])
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
        ):
            if key in workflow:
                updated[key] = workflow[key]
        atomic_json(target, updated)
        result["artifacts"] = [check_artifact(target, "json")]
        atomic_json(Path(result["job_directory"]) / "job.json", result)
        return result
