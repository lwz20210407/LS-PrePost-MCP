"""Execute an explicitly prepared program bundle in the current owned GUI."""

import json
import uuid
from pathlib import Path

from .config import command_path, scl_command_path
from .jobs import atomic_json, check_artifact, now
from .model_context import LOAD_ERROR, verify_loaded_model
from .native.commands import bind_output_paths
from .program_bundle import checked_dependencies, identity, python_wrapper, write_dependencies


def context_directory(value):
    if not value:
        return None
    path = Path(value).resolve()
    # Keyword inventory may change from a filename to its parent after native
    # meshing/save; d3plot normally reports the directory already.
    return path.parent if path.is_file() else path


def execute_prepared(service, sid, prepared_id, expected_hash, contract, content, dependencies,
                     *, journal_action="execute_native_program", journal_parameters=None, allow_owned_output_context=False):
    from .core.native_log import native_errors, read_delta

    manager = service._session_manager()
    if identity(content, contract) != expected_hash:
        raise ValueError("Prepared program execution identity changed")
    if allow_owned_output_context and contract["language"] != "cfile":
        raise ValueError("Owned output context applies only to cfile")
    parameters = dict(prepared_job_id=prepared_id, expected_sha256=expected_hash)
    with manager.lock(sid):
        meta = service._visible_mesh_session(sid, manager, allow_results=True)
        before = manager.dispatch(sid, "inspect_model", {})
        if before["status"] != "succeeded":
            return before
        if meta["model_kind"] == "keyword" and before["data"]["counts"].get("nodes", 0):
            checkpoint = manager.dispatch(sid, "export_keyword", {}, artifacts=(("model.k", "keyword"),), export=True)
            if checkpoint["status"] != "succeeded":
                return checkpoint
            meta = manager.read(sid)
            meta.update(last_checkpoint=checkpoint["artifacts"][0]["path"], dirty=False)
            manager.save(sid, meta)
            # Native keyword saving can replace a filename-style model_directory
            # with the session directory. Establish the context after our own save.
            before = manager.dispatch(sid, "inspect_model", {})
            if before["status"] != "succeeded":
                return before
        directory, result = service.jobs.create("execute_native_program", dict(session_id=sid, **parameters))
        result.update(status="running", started_at=now(), job_directory=str(directory), session_id=sid,
                      backend="lsprepost", native_channel=contract["language"], execution_mode="visible_gui_program",
                      baseline_checkpoint=meta.get("last_checkpoint"), process=meta["process"])
        (directory / contract["program"]).write_bytes(content)
        write_dependencies(directory, dependencies)
        atomic_json(directory / "contract.json", contract)
        atomic_json(directory / "before.json", before["data"])
        cwd = directory / "cwd.py"
        cwd.write_text("import os\nos.chdir(" + repr(str(directory)) + ")\n", encoding="utf8")
        commands = ["runpython " + command_path(cwd)]
        if contract["language"] in ("command", "cfile"):
            execution_source = "\n".join(bind_output_paths(line, [o["name"] for o in contract["outputs"]], str(directory))
                                         for line in content.decode("utf8").splitlines()) + "\n"
            executed = directory / "execution.cfile"
            executed.write_text(execution_source, encoding="utf8")
            result["executed_source"] = execution_source
            commands.append("openc command " + command_path(executed) + " nodialog")
        elif contract["language"] == "scl":
            commands.append("runscript " + scl_command_path(directory / contract["program"]))
        else:
            wrapper = directory / "gui-python.py"
            wrapper.write_text(python_wrapper(directory, [item["name"] for item, _ in dependencies]), encoding="utf8")
            commands.append("runpython " + command_path(wrapper))
        atomic_json(directory / "commands.json", commands)
        log = manager.directory(sid) / "lspost.msg"
        offset = log.stat().st_size if log.exists() else 0
        adopted_output = None
        try:
            native = manager.dispatch(sid, "inspect_model", {}, native_commands=commands)
            result["native_request"] = {k:v for k,v in native.items() if k != "data"}
            if native["status"] != "succeeded":
                raise ValueError("Native program did not finish correlated GUI readback")
            after = native["data"]
            atomic_json(directory / "after.json", after)
            if context_directory(after.get("model_directory")) != context_directory(before["data"].get("model_directory")):
                candidates = [directory / item["name"] for item in contract["outputs"] if item["kind"] == "keyword"]
                if not allow_owned_output_context or len(candidates) != 1 or meta["model_kind"] != "keyword":
                    raise ValueError("Program replaced the current model context; use dedicated open/reset tools")
                adopted_output = candidates[0]
                check_artifact(adopted_output, "keyword")
                verify_loaded_model(dict(model=str(adopted_output), file_type="keyword"), after)
            diagnostics = []
            if log.exists():
                text = read_delta(log, offset, existed=True)
                (directory / "native.log").write_text(text, encoding="utf8")
                diagnostics = native_errors(text)
                diagnostics.extend(line.strip() for line in text.splitlines() if LOAD_ERROR.search(line))
            if diagnostics:
                raise ValueError("Native program diagnostics: " + "; ".join(diagnostics))
            if contract["language"] == "python":
                reply = json.loads((directory / "python-result.json").read_text(encoding="utf8"))
                if not reply.get("ok"):
                    raise ValueError("Embedded Python failed: " + str(reply.get("error")))
            if any(after["counts"].get(k) != v for k,v in contract["expected_counts"].items()):
                raise ValueError("Native counts differ from the declared program contract")
            checked_dependencies(directory, contract)
            if identity((directory / contract["program"]).read_bytes(), contract) != expected_hash:
                raise ValueError("Program changed its staged source")
            artifacts = [check_artifact(directory / item["name"], item["kind"]) for item in contract["outputs"]]
            verified = bool(contract["outputs"] or contract["expected_counts"])
            result.update(status="succeeded" if verified else "completed_unverified", artifacts=artifacts,
                          data=dict(counts=after["counts"], declared_contract_verified=verified,
                                    dependency_count=len(dependencies), bundle_sha256=expected_hash,
                                    scope="Declared file/count checks only; arbitrary program semantics and physical validity are not inferred"))
        except Exception as exc:
            result.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)), artifacts=[])
            active = manager.read(sid).get("active_request")
            if active and "native_request" not in result:
                result["native_request"] = dict(job_directory=str(manager.directory(sid) / "requests" / active))
        current = manager.read(sid)
        if result["status"] != "failed" and adopted_output:
            from .resident_models import remember_model
            remember_model(current)
            current.update(source=str(adopted_output), staged_model=str(adopted_output),
                           last_checkpoint=str(adopted_output), last_verified_source=None,
                           last_list_source=None, native_export_aliases=[], managed_fringe=None,
                           fringe_storage={}, reset_recovery_source=None, reset_rollback_checkpoint=None)
            remember_model(current)
        current.update(dirty=current["model_kind"] == "keyword" or current.get("dirty", False),
                       model_generation=uuid.uuid4().hex, selection_buffers={}, entity_visibility_last=None)
        if current.get("managed_fringe") is not None:
            current["managed_fringe"]["status"] = "changed_by_native_program"
        if result["status"] == "failed":
            current["state"] = "uncertain" if current["process_alive"] else "exited"
        manager.save(sid, current)
        result["finished_at"] = now()
        atomic_json(directory / "job.json", result)
        manager.journal(sid, dict(action=journal_action, parameters=journal_parameters or parameters, result=result))
        return result
