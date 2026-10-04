"""Execute the shared validated SCL field exporter in an owned visible result session."""

import inspect
import math
from pathlib import Path

from .config import scl_command_path
from .gui_mesh import check_same_nodes, check_same_parts, mesh_index, verify_mesh_digest
from .gui_selection import available_ids, part_visibility
from .jobs import atomic_json, now
from .native_results import STRESS_KEYS, native_fields
from .programs import native_errors
from .result_validity import reject_adaptive_family


def verify_context(before, after):
    if "mesh_digest" in before or "mesh_digest" in after:
        verify_mesh_digest(before, after)
    old_nodes, old_elements = mesh_index(before)
    new_nodes, new_elements = mesh_index(after)
    check_same_nodes(old_nodes, new_nodes)
    check_same_parts(before, after)
    if old_elements != new_elements:
        raise ValueError("Field export changed native connectivity")
    if before.get("current_state") != after.get("current_state"):
        raise ValueError("Field export did not restore the original state")
    if before.get("selection_ids") is None or before.get("selection_ids") != after.get("selection_ids"):
        raise ValueError("Field export changed or could not verify the selection")
    if part_visibility(before) != part_visibility(after):
        raise ValueError("Field export changed part visibility")
    if before.get("visibility_binary") is not None and before["visibility_binary"] != after.get("visibility_binary"):
        raise ValueError("Field export changed entity display-active flags")


def run_fields(service, session_id, action, parameters):
    if "path" in parameters:
        raise ValueError("GUI fields use the current staged model; open it first instead of supplying path")
    # Reuse public argument names/defaults; unknown/missing fields fail before dispatch.
    bound = inspect.signature(getattr(service, action)).bind(path=None, **parameters)
    bound.apply_defaults()
    args = bound.arguments
    derived = action == "extract_native_stress"
    domain = args["element_type" if derived else "entity_type"]
    if derived and domain == "node":
        raise ValueError("Stress requires element results")
    entity_ids = args["element_ids" if derived else "entity_ids"]
    fields = STRESS_KEYS + ["von_mises"] if derived else args["fields"]

    def execute(action_name, params, build, parse):
        manager = service._session_manager()
        with manager.lock(session_id):
            meta = manager.read(session_id)
            if not meta["process_alive"] or meta["state"] != "ready" or meta["model_kind"] != "d3plot":
                raise ValueError("A ready owned d3plot GUI session is required")
            directory, manifest = service.jobs.create(action_name, dict(session_id=session_id, **params))
            manifest.update(
                backend="lsprepost",
                native_channel="scl",
                execution_mode="visible_gui_native_scl",
                session_id=session_id,
                process=meta["process"],
                started_at=now(),
                status="running",
            )
            atomic_json(directory / "job.json", manifest)
            try:
                snapshot = dict(entity_type=params["domain"], entity_ids=params["entity_ids"], visibility_readback=True)
                baseline = manager.dispatch(session_id, "gui_mesh_digest", snapshot)
                if baseline["status"] != "succeeded":
                    raise RuntimeError("Cannot establish the native field-export baseline")
                before = baseline["data"]
                manifest["baseline_request_directory"] = baseline.get("job_directory")
                atomic_json(directory / "before.json", before)
                part_visibility(before)
                if not set(params["entity_ids"]) <= available_ids(before, params["domain"]):
                    raise ValueError("Requested field IDs are absent from the current entity domain")
                if max(params["states"]) > before["counts"]["states"]:
                    raise ValueError("Requested field state exceeds the current result database")
                original_state = before["current_state"]
                if type(original_state) is not int or not 1 <= original_state <= before["counts"]["states"]:
                    raise ValueError("No verified native current state")
                source = meta.get("staged_model")
                if args["validity_policy"] == "alive":
                    if meta.get("source"):
                        reject_adaptive_family(meta["source"])
                    native_directory = before.get("model_directory")
                    if not source or not native_directory or Path(native_directory).resolve() != Path(source).resolve().parent:
                        raise ValueError("Native model directory does not match the staged mask source; reopen the owned result model")
                validity = build(directory, in_memory=True, validity_source=source)
                if validity:
                    for row in validity["states"]:
                        if (len(before["state_times"]) < row["state"] or
                                not math.isclose(before["state_times"][row["state"]-1], row["time"], rel_tol=2e-7, abs_tol=0)):
                            raise ValueError("Native and mask state inventories disagree")
                log = manager.directory(session_id) / "lspost.msg"
                offset = log.stat().st_size if log.exists() else 0
                result = manager.dispatch(
                    session_id,
                    "gui_mesh_digest",
                    snapshot,
                    native_commands=[
                        "anim stop",
                        "runscript " + scl_command_path(directory / "extract.scl"),
                        "state %d" % original_state,
                    ],
                )
                manifest["native_request"] = {k: v for k, v in result.items() if k != "data"}
                if result["status"] != "succeeded":
                    raise RuntimeError("Native GUI SCL execution did not complete successfully")
                after = result["data"]
                atomic_json(directory / "after.json", after)
                if log.exists():
                    with log.open("rb") as stream:
                        stream.seek(offset)
                        diagnostics = native_errors(stream.read().decode("utf8", errors="replace"))
                    if diagnostics:
                        raise RuntimeError("Native SCL diagnostics: " + "; ".join(diagnostics))
                try:
                    verify_context(before, after)
                except ValueError:
                    changed = manager.read(session_id)
                    changed.update(state="uncertain", dirty=True)
                    manager.save(session_id, changed)
                    raise
                data, artifacts = parse(directory)
                data.update(
                    requires_python=True,
                    verification_uses_embedded_python=True,
                    read_only="Current owned GUI with staged result input; no reopen or extra LS-PrePost process",
                    original_state=original_state,
                    state_restored=True,
                    session_context_preserved=True,
                    animation_policy="stopped; not automatically resumed",
                )
                manifest.update(status="succeeded", data=data, artifacts=artifacts)
                # Large private snapshots are files, not repeated in the response.
                manifest["native_request"] = {k: v for k, v in result.items() if k != "data"}
            except Exception as exc:
                manifest.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
            manifest.update(finished_at=now(), job_directory=str(directory))
            atomic_json(directory / "job.json", manifest)
            manager.journal(session_id, dict(action=action, parameters=parameters, result=manifest))
            return manifest

    return native_fields(
        service.settings,
        service.jobs,
        None,
        domain,
        entity_ids,
        args["states"],
        fields,
        args["integration_point"],
        args["units"],
        derived=derived,
        executor=execute,
        validity_policy=args["validity_policy"],
    )
