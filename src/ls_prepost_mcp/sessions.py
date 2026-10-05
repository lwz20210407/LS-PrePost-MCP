"""Persistent native GUI sessions with process identity, serialized requests and checkpoints."""

import contextlib
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from .checkpoint_context import (
    checkpoint_expected_empty,
    reset_baseline,
    restart_source,
    save_checkpoint_context,
)
from .engine import SessionEngine, SessionJob
from .engine.environment import native_environment
from .engine.queue_transport import QueueTransport
from .jobs import atomic_json, check_artifact, fingerprint, now
from .model_context import verify_load_reply
from .native import commands as nc
from .native.bundle import stage_bridge
from .native.versions import require_capability
from .native_connectivity import beam_connectivity_prelude
from .outcomes import normalize_outcome
from .windows_transport import WindowsCommandTransport

NATIVE_ACTIONS = {
    "extract_native_fields",
    "extract_native_stress",
    "create_solid_sphere",
    "rotate_mesh_nodes",
    "inspect_model",
    "list_nodes",
    "list_parts",
    "get_element_connectivity",
    "render_snapshot",
    "create_shell_plate",
    "create_solid_box",
    "translate_mesh_nodes",
    "move_elements_to_part",
    "extrude_shell_part",
    "export_keyword",
    "extract_nodal_results",
    "extract_node_history",
    "measure_parts",
}
MUTATIONS = {
    "create_solid_sphere",
    "rotate_mesh_nodes",
    "create_shell_plate",
    "create_solid_box",
    "translate_mesh_nodes",
    "move_elements_to_part",
    "extrude_shell_part",
}

# Batch-native validation does not certify the persistent GUI execution path.
GUI_BATCH_ACTIONS = {"rotate_mesh_nodes", "translate_mesh_nodes"}

# These kernels validate their own result before publishing the correlated
# completion. Native-command + readback requests still need their host-side
# transaction checks and cannot become ready merely because readback finished.
RECOVERABLE_KERNEL_MUTATIONS = {"create_plate", "create_box", "create_sphere", "rotate_nodes",
                                "translate_nodes", "move_elements_to_part", "extrude_shell"}
RECOVERABLE_READS = {"inspect_model", "list_nodes", "list_parts", "connectivity", "gui_mesh_digest",
                     "gui_mesh_state", "gui_mesh_page", "gui_measure", "measure_parts", "probe",
                     "scl_probe", "extract_nodal", "extract_node_history", "render_snapshot", "export_keyword"}


def recovery_mode(request):
    if request.get("native_commands"):
        return "requires_host_validation"
    if request.get("model") or request["action"] == "gui_new":
        return "model_replaced"
    if request["action"] in RECOVERABLE_KERNEL_MUTATIONS:
        return "validated_native_kernel"
    if request["action"] in RECOVERABLE_READS:
        return "native_read"
    return "requires_host_validation"


def process_identity(pid):
    import psutil

    process = psutil.Process(pid)
    return {"pid": pid, "create_time": process.create_time(), "exe": str(Path(process.exe()).resolve())}


def alive(identity):
    try:
        current = process_identity(identity["pid"])
        return current == identity
    except Exception:
        return False


class Sessions:
    def __init__(self, settings):
        self.settings = settings
        self.root = settings.workspace / "sessions"

    def directory(self, ident):
        if not re.fullmatch(r"[a-f0-9]{32}", ident):
            raise ValueError("Invalid session ID")
        path = (self.root / ident).resolve()
        if path.parent != self.root.resolve():
            raise ValueError("Session directory escapes configured workspace")
        return path

    def read(self, ident):
        directory = self.directory(ident)
        data = json.loads((directory / "session.json").read_text(encoding="utf8"))
        data["process_alive"] = alive(data["process"])
        if not data["process_alive"] and data["state"] != "closed":
            data["state"] = "closed" if data.get("closed_at") else "exited"
        return data

    def save(self, ident, data):
        atomic_json(self.directory(ident) / "session.json", data)

    @contextlib.contextmanager
    def lock(self, ident):
        path = self.directory(ident) / "request.lock"
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            owner = json.loads(path.read_text(encoding="utf8"))
            if alive(owner):
                raise RuntimeError("Session has an outstanding request; inspect it before retrying") from None
            path.unlink()
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf8") as f:
            json.dump(process_identity(os.getpid()), f)
        try:
            yield
        finally:
            path.unlink()

    def start(self, *, transport="win32"):
        if transport not in ("win32", "queue"):
            raise ValueError("Session transport must be win32 or queue")
        exe = self.settings.native_executable()
        if transport == "queue":
            require_capability(exe, "queue_model_identity")
        if transport == "win32":
            WindowsCommandTransport(0).require_interactive_desktop()
        if os.name != "nt":
            raise RuntimeError("Persistent GUI sessions currently support Windows")
        ident = uuid.uuid4().hex
        directory = self.directory(ident)
        directory.mkdir(parents=True)
        stage_bridge(directory)
        bootstrap = directory / "initialize.py"
        ready = directory / "ready.json"
        (directory / "initial.k").write_text("*KEYWORD\n*TITLE\nMCP session model\n*END\n", encoding="ascii")
        bootstrap.write_text(
            "import os,json,builtins,LsPrePost as lp\nos.chdir(" + repr(str(directory)) + ")\n"
            "lp.execute_command(" + repr(nc.open_model(directory / "initial.k")) + ")\n"
            "builtins._lspp_mcp_session=" + repr(ident) + "\n"
            'json.dump({"session_id":'
            + repr(ident)
            + ',"pid":os.getpid()},open('
            + repr(str(ready))
            + ',"w"))\n',
            encoding="utf8",
        )
        if transport == "queue":
            shutil.copyfile(Path(__file__).parent / "engine" / "embedded_queue.py", directory / "queue-bridge.py")
            code = bootstrap.read_text(encoding="utf8")
            code = code[:code.index('json.dump(')]
            code += "import runpy\nrunpy.run_path(" + repr(str(directory / "queue-bridge.py")) + ")[\"run\"](" + repr(str(directory)) + "," + repr(ident) + "," + repr(secrets.token_hex(32)) + ")\n"
            bootstrap.write_text(code, encoding="utf8")
        cfile = directory / "initialize.cfile"
        # A fresh process needs no `new`: some GUI builds treat it as Restart
        # and block the startup command file behind a confirmation dialog.
        nc.write_cfile(cfile, [nc.run_script(bootstrap)] + (["exit"] if transport == "queue" else []))
        env, configuration = native_environment(exe, directory)
        with (directory / "process.log").open("wb") as log:
            process = subprocess.Popen(
                [str(exe), "c=" + str(cfile), "-nographics" if transport == "queue" else "w=1200x800"],
                cwd=directory,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        identity = process_identity(process.pid)
        data = dict(
            session_id=ident,
            state="starting",
            created_at=now(),
            process=identity,
            executable=fingerprint(exe),
            directory=str(directory),
            dirty=False,
            model_kind="keyword",
            last_checkpoint=None,
            transport=("loopback receiver + native main-thread queue" if transport == "queue"
                       else "owned-process Windows command entry + finite embedded Python"),
            engine_transport=transport,
            bridge_protocol=4,
            model_generation=uuid.uuid4().hex,
            recording=None,
            configuration=configuration,
        )
        self.save(ident, data)
        deadline = time.monotonic() + min(60, self.settings.timeout)
        while time.monotonic() < deadline:
            if ready.exists():
                response = json.loads(ready.read_text())
                if response.get("session_id") != ident or response.get("pid") != process.pid:
                    raise RuntimeError("Native bootstrap identity mismatch")
                try:
                    if transport == "queue":
                        QueueTransport(response, self.settings.timeout).preflight()
                    else:
                        WindowsCommandTransport(process.pid).command_window()
                except RuntimeError as exc:
                    data["last_error"] = str(exc)
                else:
                    data["state"] = "ready"
                    self.save(ident, data)
                    return self.read(ident)
            if process.poll() is not None:
                break
            time.sleep(0.1)
        data["state"] = "startup_failed"
        self.save(ident, data)
        if process.poll() is None:
            process.terminate()
        raise RuntimeError("Native GUI session did not initialize; see " + str(directory / "process.log"))

    def dispatch(
        self,
        ident,
        action,
        parameters,
        *,
        model=None,
        file_type="keyword",
        artifacts=(),
        export=False,
        native_commands=(),
        expected_empty=False,
    ):
        if native_commands and model is not None:
            raise ValueError("Open the model before submitting in-memory native commands")
        if any(
            not isinstance(c, str) or not c.strip() or any(x in c for x in "\r\n\x00")
            for c in native_commands
        ):
            raise ValueError("Native command sequence requires nonempty single lines")
        data = self.read(ident)
        if not data["process_alive"] or data["state"] not in ("ready", "uncertain"):
            raise RuntimeError("Session is not available")
        if data.get("active_request"):
            raise RuntimeError("Reconcile the outstanding request before dispatching another operation")
        safe_beams = action in ("gui_mesh_digest", "gui_mesh_state", "gui_mesh_page", "connectivity")
        if action == "gui_mesh_page" and parameters.get("entity_type") != "beam":
            safe_beams = False
        if action == "connectivity" and parameters.get("element_type") != "beam":
            safe_beams = False
        if safe_beams and model is not None:
            raise ValueError("Open the model before requesting native beam-aware structural readback")
        if safe_beams and data.get("bridge_protocol", 1) < 4:
            raise RuntimeError("Start a new GUI session for the native-keyword beam connectivity bridge")
        queued = data.get("engine_transport") == "queue"
        if queued:
            ready = json.loads((self.directory(ident) / "ready.json").read_text(encoding="utf8"))
            if ready.get("session_id") != ident or ready.get("pid") != data["process"]["pid"]:
                raise RuntimeError("Session listener identity mismatch")
            transport = QueueTransport(ready, self.settings.timeout)
        else:
            transport = WindowsCommandTransport(data["process"]["pid"])
        transport.preflight()
        was_uncertain = data["state"] == "uncertain"
        directory = self.directory(ident) / "requests" / uuid.uuid4().hex
        directory.mkdir(parents=True)
        request = dict(
            job_id=directory.name,
            action=action,
            parameters=parameters,
            job_directory=str(directory),
            model=str(model) if model else None,
            file_type=file_type,
            absolute_keyword_path=True,
            native_commands=list(native_commands),
            safe_beam_connectivity=safe_beams,
            expected_empty=expected_empty,
        )
        atomic_json(directory / "request.json", request)
        contract = dict(artifacts=list(artifacts), export=export, was_uncertain=was_uncertain)
        if model is not None or action == "gui_new":
            log = self.directory(ident) / "lspost.msg"
            contract["model_load_log"] = dict(existed=log.exists(), offset=log.stat().st_size if log.exists() else 0)
        atomic_json(directory / "contract.json", contract)
        response = directory / "response.json"
        bridge = self.directory(ident) / "bridge.py"
        code = (
            "import os,runpy,builtins\n"
            'assert getattr(builtins,"_lspp_mcp_session",None)==' + repr(ident) + ', "Wrong native session"\n'
            "os.chdir(" + repr(str(directory)) + ")\n"
            "runpy.run_path("
            + repr(str(bridge))
            + ')["run"]('
            + repr(str(directory / "request.json"))
            + ","
            + repr(str(response))
            + ")\n"
        )
        # Response is published by a finalizer after optional native save completes.
        if export:
            code += (
                "import json,LsPrePost as lp\n"
                "if json.load(open(" + repr(str(response)) + ")) .get('ok'):\n"
                "    lp.execute_command(" + repr(nc.save_keyword(directory / "model.k", style="native")) + ")\n"
            )
        code += "os.replace(" + repr(str(response)) + "," + repr(str(directory / "complete.json")) + ")\n"
        bootstrap = directory / "dispatch.py"
        bootstrap.write_text(code, encoding="utf8")
        command_file = directory / "dispatch.cfile"
        # Let LS-PrePost itself interpret selection/edit commands outside the
        # embedded Python callback, then use Python only for readback.
        commands = list(native_commands)
        if safe_beams:
            script = directory/"beam-connectivity.py"
            script.write_text(beam_connectivity_prelude(directory), encoding="utf8")
            commands.append(nc.run_script(script))
        nc.write_cfile(command_file, commands + [nc.run_script(bootstrap)])
        if queued:
            atomic_json(directory / "queue-job.json", dict(job_id=directory.name,
                commands=list(native_commands), python=([str(script)] if safe_beams else []) + [str(bootstrap)]))
        data.update(state="busy", active_request=directory.name)
        self.save(ident, data)
        def verify(reply):
            result = dict(
                session_id=ident,
                request_id=directory.name,
                job_directory=str(directory),
                status="succeeded" if reply.get("ok") else "failed",
                data=reply.get("data"),
                error=reply.get("error"),
                artifacts=[],
            )
            if reply.get("ok"):
                try:
                    context = verify_load_reply(request, reply, directory, contract)
                    if context is not None:
                        result["model_context"] = context
                    result["artifacts"] = [
                        check_artifact(directory / name, kind) for name, kind in artifacts
                    ]
                    target = directory / "model.k" if export else model if file_type == "keyword" else None
                    if action == "gui_new":
                        target = directory / "initial.k"
                    if target is not None:
                        save_checkpoint_context(target, ident, reply.get("data"), self.directory(ident))
                    if model is None and action != 'gui_new' and (export or safe_beams):
                        from .resident_models import remember_exports

                        identities = {}
                        before_export = directory/'beam-export-before.json'
                        if safe_beams and before_export.is_file():
                            identities['beam'] = remember_exports(data, [directory/'beam-connectivity.k'],
                                json.loads(before_export.read_text(encoding='utf8')), ident, self.directory(ident))
                        if export:
                            identities['keyword'] = remember_exports(data, [directory/'model.k'],
                                reply.get('data'), ident, self.directory(ident))
                        result['native_export_identity'] = identities
                except Exception as exc:
                    result.update(status="failed", error={"message": str(exc)})
            outcome = normalize_outcome(action, result)
            return outcome.model_copy(update={"job_id": directory.name, "backend": "lsprepost",
                                              "comparison_data": result})

        outcome = SessionEngine().run(SessionJob(
            operation=action, directory=directory, timeout=self.settings.timeout,
            submit=lambda: transport.submit(directory.name if queued else nc.run_script(command_file, "cfile")),
            is_alive=lambda: alive(data["process"]), verify=verify,
            log=self.directory(ident) / "lspost.msg"))
        atomic_json(directory / "engine-result.json", outcome.model_dump(mode="json"))
        if outcome.comparison_data is None:
            message = (outcome.error or {}).get("message", "Session execution unverified")
            data.update(state="uncertain", last_error=message)
            self.save(ident, data)
            if (outcome.error or {}).get("type") == "TimeoutError":
                raise TimeoutError(message)
            raise RuntimeError(message)
        result = outcome.comparison_data
        result["status"] = outcome.status
        if outcome.error is not None:
            result["error"] = outcome.error
        data.update(
            state="ready" if result["status"] == "succeeded" and (not was_uncertain or model or action == "gui_new") else "uncertain",
            active_request=None,
        )
        self.save(ident, data)
        atomic_json(directory / "operation.json", result)
        return result

    def stage_input(self, ident, path, file_type):
        source = self.settings.input_path(path)
        if file_type not in ("keyword", "d3plot"):
            raise ValueError("Unsupported session file type")
        if file_type == "keyword":
            self.settings.check_keyword_includes(source)
            if any(
                s.strip().upper().startswith("*INCLUDE")
                for s in source.read_text(errors="replace").splitlines()
            ):
                raise ValueError("Use a flattened/staged standalone deck for session loading")
        family = [source]
        if file_type == "d3plot":
            family += sorted(
                p for p in source.parent.iterdir() if re.fullmatch(re.escape(source.name) + r"\d+", p.name)
            )
        family = [self.settings.input_path(str(p)) for p in family]
        if sum(p.stat().st_size for p in family) > 4 * 1024**3:
            raise ValueError("Session input staging exceeds 4 GiB")
        directory = self.directory(ident) / "inputs" / uuid.uuid4().hex
        directory.mkdir(parents=True)
        identities = [fingerprint(p) for p in family]
        for p in family:
            target = "model.k" if file_type == "keyword" else "d3plot" + p.name[len(source.name) :]
            shutil.copyfile(p, directory / target)
        if identities != [fingerprint(p) for p in family]:
            raise RuntimeError("Input changed while staging")
        atomic_json(directory / "inputs.json", identities)
        return directory / ("model.k" if file_type == "keyword" else "d3plot")

    def journal(self, ident, entry):
        with (self.directory(ident) / "journal.jsonl").open("a", encoding="utf8") as f:
            f.write(json.dumps(dict(time=now(), **entry), ensure_ascii=False, allow_nan=False) + "\n")


class SessionTools:
    def show_gui_session(self, session_id: str, maximize: bool = True, keep_on_top: bool = False) -> dict:
        """Restore and foreground only the verified owned GUI process, for interactive inspection."""
        meta = self._session_manager().read(session_id)
        if not meta["process_alive"]:
            raise RuntimeError("Owned process is no longer alive")
        if type(maximize) is not bool or type(keep_on_top) is not bool:
            raise ValueError("Window options require booleans")
        return WindowsCommandTransport(meta["process"]["pid"]).show(
            maximize=maximize, keep_on_top=keep_on_top
        )

    def list_gui_sessions(self) -> list[dict]:
        """List only this workspace's managed GUI sessions, including exited sessions and saved checkpoints."""
        manager = self._session_manager()
        return [manager.read(p.parent.name) for p in sorted(manager.root.glob("*/session.json"))]

    def recover_gui_session(self, session_id: str) -> dict:
        """Reconcile correlated late completion without replay. Only self-validated kernels/reads or explicit reopen can restore readiness; native-command transactions retain uncertainty until restored/revalidated. Parent workflow gates are never implicitly passed."""
        manager = self._session_manager()
        with manager.lock(session_id):
            meta = manager.read(session_id)
            request_id = meta.get("active_request")
            if not request_id:
                return meta
            if not re.fullmatch(r"[a-f0-9]{32}", request_id):
                raise ValueError("Invalid pending request identity")
            directory = manager.directory(session_id) / "requests" / request_id
            complete = directory / "complete.json"
            if not complete.exists():
                return dict(**meta, recovery="No correlated completion yet; nothing replayed")
            try:
                reply = json.loads(complete.read_text(encoding="utf8"))
                if reply.get("job_id") != request_id:
                    raise RuntimeError("Late response identity mismatch")
                if type(reply.get("ok")) is not bool:
                    raise ValueError("Late response success flag is not Boolean")
                contract = json.loads((directory / "contract.json").read_text(encoding="utf8"))
                request = json.loads((directory / "request.json").read_text(encoding="utf8"))
                if request.get("job_id") != request_id:
                    raise RuntimeError("Saved request identity mismatch")
                mode = recovery_mode(request)
                artifacts = []
                context = None
                if reply.get("ok"):
                    try:
                        context = verify_load_reply(request, reply, directory, contract)
                    except ValueError as exc:
                        reply = dict(reply, ok=False, error=dict(type="NativeModelContextError", message=str(exc)))
                if reply.get("ok"):
                    for name, kind in contract["artifacts"]:
                        path = (directory / name).resolve()
                        if not path.is_relative_to(directory.resolve()):
                            raise ValueError("Recovery artifact escapes the owned request")
                        artifacts.append(check_artifact(path, kind))
                    if contract["export"] and mode != "requires_host_validation" and not contract.get("was_uncertain"):
                        if not any(Path(a["path"]).name == "model.k" and a.get("validated") for a in artifacts):
                            raise ValueError("Checkpoint recovery lacks a validated model.k artifact")
                        save_checkpoint_context(directory / "model.k", session_id, reply.get("data"), manager.directory(session_id))
                    elif request.get("model") and request.get("file_type") == "keyword" and mode == "model_replaced":
                        save_checkpoint_context(request["model"], session_id, reply.get("data"), manager.directory(session_id))
                    elif request["action"] == "gui_new" and mode == "model_replaced":
                        save_checkpoint_context(directory / "initial.k", session_id, reply.get("data"), manager.directory(session_id))
            except Exception as exc:
                meta.update(state="uncertain" if meta["process_alive"] else "exited", last_error=str(exc))
                manager.save(session_id, meta)
                raise
            if not reply.get("ok"):
                meta.update(state="uncertain" if meta["process_alive"] else "exited", active_request=None)
                if meta["model_kind"] == "keyword" and mode != "native_read":
                    meta["dirty"] = True
                manager.save(session_id, meta)
                atomic_json(directory / "recovery.json", dict(
                    session_id=session_id, request_id=request_id, status="failed",
                    error=reply.get("error"), replayed=False,
                    scope="Correlated completion rejected; managed model identity was not advanced"))
                return dict(
                    **meta,
                    recovery="Native action failed; restore a checkpoint",
                    native_error=reply.get("error"),
                )
            opened_model = request.get("model")
            state = (
                "uncertain"
                if mode == "requires_host_validation" or (contract.get("was_uncertain") and mode != "model_replaced")
                else "ready"
            )
            if not meta["process_alive"]:
                state = "closed" if meta.get("closed_at") else "exited"
            meta.update(state=state, active_request=None)
            if meta["model_kind"] == "keyword" and (mode in ("validated_native_kernel", "requires_host_validation")
                    or (contract.get("was_uncertain") and mode != "model_replaced")):
                meta["dirty"] = True
            if contract["export"] and mode != "requires_host_validation" and not contract.get("was_uncertain"):
                meta.update(last_checkpoint=str(directory / "model.k"), dirty=False)
            if opened_model:
                meta.update(model_kind=request["file_type"], staged_model=opened_model, dirty=False,
                            source=opened_model,
                            last_checkpoint=opened_model if request["file_type"] == "keyword" else None,
                            model_generation=uuid.uuid4().hex,
                            reset_recovery_source=None, reset_rollback_checkpoint=None,
                            selection_buffers={}, entity_visibility_last=None, managed_fringe=None, fringe_storage={})
                inputs = Path(opened_model).parent / "inputs.json"
                if inputs.is_file():
                    identities = json.loads(inputs.read_text(encoding="utf8"))
                    if identities:
                        meta["source"] = identities[0]["path"]
            elif request["action"] == "gui_new" and mode == "model_replaced":
                meta.update(model_kind="keyword", dirty=False,
                            **reset_baseline(directory, meta.get("last_checkpoint")),
                            model_generation=uuid.uuid4().hex, selection_buffers={}, entity_visibility_last=None,
                            managed_fringe=None, fringe_storage={})
            recovered = dict(session_id=session_id, request_id=request_id, status=("completed_unverified"
                             if mode == "requires_host_validation" else "succeeded"), data=reply.get("data"),
                             artifacts=artifacts, recovery_mode=mode, replayed=False,
                             scope="Native request/artifact reconciliation only; parent workflow/postcondition checks are not replayed")
            if context is not None:
                recovered["model_context"] = context
            atomic_json(directory / "recovery.json", recovered)
            meta["last_recovery"] = str(directory / "recovery.json")
            manager.save(session_id, meta)
            return dict(**meta, recovery="Late completion reconciled; no replay", artifacts=artifacts,
                        recovery_mode=mode, requires_host_validation=mode == "requires_host_validation")

    def reset_gui_session(self, session_id: str, save_checkpoint: bool = True) -> dict:
        """Start a new active empty model; save prior keyword cards even with no mesh. Keep last_checkpoint for explicit undo, and a separate empty baseline for process restart until a newer model/checkpoint is established. Does not certify unloading other resident models."""
        if type(save_checkpoint) is not bool:
            raise ValueError("save_checkpoint must be a boolean")
        manager = self._session_manager()
        with manager.lock(session_id):
            meta = manager.read(session_id)
            if save_checkpoint and (meta["state"] != "ready" or meta.get("active_request")):
                raise ValueError("Reconcile/restore the uncertain operation before replacing the trusted checkpoint")
            info = manager.dispatch(session_id, "inspect_model", {})
            if info["status"] != "succeeded":
                return info
            if (
                save_checkpoint
                and meta["model_kind"] == "keyword"
            ):
                saved = manager.dispatch(
                    session_id, "export_keyword", {}, artifacts=(("model.k", "keyword"),), export=True
                )
                if saved["status"] != "succeeded":
                    return saved
                meta["last_checkpoint"] = saved["artifacts"][0]["path"]
                current = manager.read(session_id)
                current.update(last_checkpoint=meta["last_checkpoint"], dirty=False)
                manager.save(session_id, current)  # Retain rollback even if reset times out.
            result = manager.dispatch(session_id, "gui_new", {})
            if result["status"] == "succeeded":
                updated = manager.read(session_id)
                updated.update(
                    model_kind="keyword",
                    dirty=False,
                    last_checkpoint=meta.get("last_checkpoint"),
                    **reset_baseline(result["job_directory"], meta.get("last_checkpoint")),
                    model_generation=uuid.uuid4().hex,
                    selection_buffers={},
                    entity_visibility_last=None,
                    managed_fringe=None,
                    fringe_storage={},
                )
                manager.save(session_id, updated)
                result["rollback_checkpoint"] = meta.get("last_checkpoint")
                result["restart_baseline"] = updated["reset_recovery_source"]
                atomic_json(Path(result["job_directory"]) / "operation.json", result)
            manager.journal(session_id, dict(action="new_model", parameters=dict(save_checkpoint=save_checkpoint), result=result))
            return result

    def _session_manager(self):
        return Sessions(self.settings)

    def start_gui_session(self) -> dict:
        """Start an owned persistent native GUI process; subsequent tools reuse its model and normal event loop. Windows only; configured embedded Python required."""
        return self._session_manager().start()

    def inspect_gui_session(self, session_id: str, include_models: bool = False) -> dict:
        """Read session metadata. include_models=True opens the owned Model Selection panel and reads current row indexes/display labels/paths (Windows x64, up to256). Display-number prefixes can differ from command positions after removal. Unique source match yields an active-row candidate, never a stable model ID or genselect suffix. Checks inventory/source/state unchanged and leaves panel open. Pending/locked/unavailable native inspections reject; metadata-only remains available."""
        if type(include_models) is not bool:
            raise ValueError("include_models must be a boolean")
        manager = self._session_manager()
        if not include_models:
            return manager.read(session_id)
        from .windows_model_list import active_model_candidate, inspect_models

        with manager.lock(session_id):
            meta = manager.read(session_id)
            before = manager.dispatch(session_id, "inspect_model", {})
            if before["status"] != "succeeded":
                raise RuntimeError("Cannot establish model-inventory baseline")
            inventory = inspect_models(WindowsCommandTransport(meta["process"]["pid"]))
            after = manager.dispatch(session_id, "inspect_model", {})
            if after["status"] != "succeeded":
                raise RuntimeError("Cannot verify model-inventory readback")
            keys = ("counts","part_ids","current_state","model_directory")
            if any(k not in before["data"] or k not in after["data"] or before["data"][k] != after["data"][k] for k in keys):
                meta = manager.read(session_id)
                meta.update(state="uncertain", dirty=True)
                manager.save(session_id, meta)
                raise RuntimeError("Active model inventory/source/state changed during inspection")
            inventory.update(active_row_index_candidate=active_model_candidate(inventory['models'], after['data'].get('model_directory')),
                             observed_model_directory=after['data'].get('model_directory'),
                             id_scope="row_index is current 1-based visible position; display_number is label text. Recorded select/remove use different numbering in the 4.13.4 fixture; neither is a universal command ID or inferred genselect suffix",
                             active_candidate_basis="Unique native source-path match only; null when ambiguous/unavailable")
            path = Path(after['job_directory'])/'model-list.json'
            atomic_json(path, inventory)
            return dict(manager.read(session_id), native_models=inventory, model_inventory_evidence=str(path))

    def restart_gui_session(self, session_id: str) -> dict:
        """Recover an exited owned session into a new visible process using its last checkpoint or staged result source; never replay uncertain commands or terminate a live process."""
        manager = self._session_manager()
        with manager.lock(session_id):
            old = manager.read(session_id)
            if old["process_alive"]:
                raise ValueError("The original GUI process is still alive; inspect/recover it instead of duplicating it")
            replacement = old.get("restarted_as")
            if replacement:
                child = manager.read(replacement)
                if not child["process_alive"]:
                    raise ValueError("Replacement session already exists but has exited; restart that session to retain its latest checkpoint: " + replacement)
                return dict(status="succeeded" if old.get("restart_status") == "succeeded" and child["state"] == "ready" else "uncertain",
                            previous_session_id=session_id, session_id=replacement, reused=True,
                            recovery_scope="Existing replacement returned without reopening, duplicating or replaying anything; inspect/recover it if uncertain")
            source = restart_source(old)
            validated_source = self.settings.input_path(source) if source else None
            expected_empty = (checkpoint_expected_empty(validated_source, session_id)
                              if source and old["model_kind"] == "keyword" else False)
            new = self.start_gui_session()
            old.update(restarted_as=new["session_id"], restart_status="restoring")
            manager.save(session_id, old)
            try:
                opened = self.open_in_gui_session(new["session_id"], source, old["model_kind"],
                    **({"expected_empty": True} if expected_empty else {})) if source else None
                if opened and opened["status"] != "succeeded":
                    old["restart_status"] = "failed"
                    manager.save(session_id, old)
                    return dict(status="failed", previous_session_id=session_id, session_id=new["session_id"], restoration=opened)
                self.show_gui_session(new["session_id"], maximize=True)
            except Exception as exc:
                old.update(restart_status="failed", restart_error=str(exc))
                manager.save(session_id, old)
                return dict(status="failed", previous_session_id=session_id, session_id=new["session_id"],
                            error=dict(type=type(exc).__name__, message=str(exc)))
            old["restart_status"] = "succeeded"
            manager.save(session_id, old)
            return dict(status="succeeded", previous_session_id=session_id, session_id=new["session_id"],
                        restoration=opened, reused=False,
                        recovery_scope="Saved model/source only; unsaved manual changes and uncertain commands are not replayed")

    def open_in_gui_session(
        self, session_id: str, path: str, file_type: str = "keyword", discard: bool = False,
        expected_empty: bool = False,
    ) -> dict:
        """Open a staged copy and verify active source. Dirty models require discard or checkpoint. expected_empty=True explicitly requires a keyword source yielding zero nodes AND elements, e.g. a saved material-only/empty recording baseline; it does not disable identity/log checks or prove other models unloaded."""
        if type(expected_empty) is not bool or expected_empty and file_type != "keyword":
            raise ValueError("expected_empty must be boolean and applies only to keyword models")
        manager = self._session_manager()
        with manager.lock(session_id):
            data = manager.read(session_id)
            if data["dirty"] and not discard:
                raise ValueError(
                    "Checkpoint the current model before replacement, or explicitly set discard=true"
                )
            staged = manager.stage_input(session_id, path, file_type)
            result = manager.dispatch(session_id, "inspect_model", {}, model=staged, file_type=file_type,
                                      **({"expected_empty": True} if expected_empty else {}))
            if result["status"] == "succeeded":
                from .resident_models import remember_model

                data = manager.read(session_id)
                remember_model(data)
                data.update(
                    model_kind=file_type,
                    dirty=False,
                    source=str(self.settings.input_path(path)),
                    staged_model=str(staged),
                    model_generation=uuid.uuid4().hex,
                    reset_recovery_source=None, reset_rollback_checkpoint=None,
                    last_verified_source=None,
                    last_list_source=None,
                    native_export_aliases=[],
                    selection_buffers={},
                    entity_visibility_last=None,
                    managed_fringe=None,
                    fringe_storage={},
                    last_checkpoint=str(staged) if file_type == "keyword" else None,
                )
                remember_model(data)
                manager.save(session_id, data)
            manager.journal(
                session_id,
                dict(action="open", parameters=dict(path=path, file_type=file_type,
                     **({"expected_empty": True} if expected_empty else {})), result=result),
            )
            return result

    def activate_gui_model(self, session_id: str, source_path: str) -> dict:
        """Activate an existing successfully opened resident source by its exact native path from inspect_gui_session(include_models=True). Saves outgoing/incoming keyword checkpoints, verifies source and unchanged model list, invalidates managed selection/field caches. No reopen/unload or desktop fallback. Rejects ambiguous/unmanaged sources, uncertain sessions and active recordings; full multi-model scene/crash recovery remains separate."""
        from .resident_models import activate

        return activate(self, session_id, source_path)

    def unload_gui_model(self, session_id: str, source_path: str, activate_source_path: str) -> dict:
        """Unload one managed resident source, explicitly choosing a different managed survivor. Saves keyword memory before removal, uses uniquely verified native display number, checks exactly one entry removed, and reselects the survivor by refreshed row. Result-to-result removal requires a verified resident keyword intermediary. Retains removed keyword checkpoint; never deletes source files. Rejects uncertainty/recording/unmanaged or ambiguous models. Does not restore arbitrary viewport/selection or all models after a crash."""
        from .resident_models import unload

        return unload(self, session_id, source_path, activate_source_path)

    def replace_gui_model(self, session_id: str, path: str, file_type: str = 'keyword', expected_empty: bool = False) -> dict:
        """Explicitly replace the current managed model in the same GUI. Preserve keyword memory; when leaving result mode create/save a native empty staging model. Verify the new load before unloading old and temporary models, retaining other entries. Accept keyword/d3plot, with expected_empty only for intentional zero-entity keyword. Reject pending/uncertain/recording states. Failures retain phase evidence/checkpoints and require reconciliation; old_model_unloaded=null is unknown, not false. No automatic retry or association semantics."""
        from .model_replacement import replace

        return replace(self, session_id, path, file_type, expected_empty)

    def gui_session_action(self, session_id: str, action: str, parameters: dict) -> dict:
        """Execute an existing typed native operation against the same in-memory model; no unrestricted script or shell. Failed mutations mark state uncertain."""
        import inspect

        if action not in NATIVE_ACTIONS:
            raise ValueError("Unsupported persistent action")
        if not isinstance(parameters, dict) or "model" in parameters or "d3plot" in parameters:
            raise ValueError("Use open_in_gui_session to change the input model")
        if action in ("extract_native_fields", "extract_native_stress"):
            from .gui_fields import run_fields

            return run_fields(self, session_id, action, parameters)
        manager = self._session_manager()
        if action in GUI_BATCH_ACTIONS:
            if manager.read(session_id).get("bridge_protocol", 1) < 3:
                raise ValueError("Start a new GUI session for in-process mesh transforms")
            routed = {"translate_mesh_nodes": "translate_gui_nodes", "rotate_mesh_nodes": "rotate_gui_nodes"}[action]
            return getattr(self, routed)(session_id=session_id, **parameters)
        with manager.lock(session_id):
            meta = manager.read(session_id)
            if meta["state"] == "uncertain" and action in MUTATIONS:
                raise ValueError("Restore/reopen a checkpoint before more mutations")
            if meta["state"] != "ready" and action == "export_keyword":
                raise ValueError("Reconcile/restore the uncertain operation before replacing the trusted checkpoint")
            if meta["model_kind"] != "keyword" and action in MUTATIONS:
                raise ValueError("Mesh edits require a keyword session")
            operation = {}

            def execute_in_session(**request):
                if operation:
                    raise RuntimeError("A typed session action must produce exactly one request")
                operation.update(request)
                return manager.dispatch(session_id, **request)

            supplied = dict(parameters)
            sig = inspect.signature(getattr(self, action))
            if "model" in sig.parameters:
                supplied["model"] = None
            if "d3plot" in sig.parameters:
                supplied["d3plot"] = None
            if "file_type" in sig.parameters:
                supplied["file_type"] = meta["model_kind"]
            with self._native_context.using(execute_in_session):
                result = getattr(self, action)(**supplied)
            if not operation:
                raise RuntimeError("Action did not produce a native request")
            if operation["action"] in ("extract_nodal", "node_history") and result["status"] == "succeeded":
                from .gui_controls import wait_for_gui_state

                requested = result["data"].get("original_state")
                if requested is None:
                    result.update(
                        status="failed", error=dict(message="Nodal state-restoration evidence is missing")
                    )
                else:
                    observed, evidence = wait_for_gui_state(
                        manager,
                        session_id,
                        requested,
                        self.settings.timeout,
                        native_commands=[nc.animation('stop'), nc.state(requested)],
                    )
                    result["data"]["state_restored"] = observed["status"] == "succeeded"
                    result["state_restoration"] = dict(requested_state=requested, observations=evidence)
                    if observed["status"] != "succeeded":
                        result.update(status="failed", error=observed.get("error"))
                atomic_json(Path(result["job_directory"]) / "operation.json", result)
            data = manager.read(session_id)
            if action in MUTATIONS:
                data["dirty"] = True
            if operation["export"] and result["status"] == "succeeded":
                data.update(last_checkpoint=result["artifacts"][0]["path"], dirty=False)
            manager.save(session_id, data)
            manager.journal(session_id, dict(action=action, parameters=parameters, result=result))
            return result

    def checkpoint_gui_session(self, session_id: str) -> dict:
        """Save current keyword model to a fresh owned checkpoint and return the file identity."""
        meta = self._session_manager().read(session_id)
        if meta["model_kind"] != "keyword":
            raise ValueError("Keyword checkpoint requires a keyword session")
        if meta["state"] != "ready" or meta.get("active_request"):
            raise ValueError("Reconcile/restore the uncertain operation before replacing the trusted checkpoint")
        return self.gui_session_action(session_id, "export_keyword", {})

    def restore_gui_checkpoint(self, session_id: str, path: str | None = None, expected_empty: bool | None = None) -> dict:
        """Reopen a checkpoint, preserving failure evidence. None auto-detects empty expectation only for this session's trusted checkpoint with matching file context. For an explicit other zero-entity source pass True. False enforces nonempty. Source/log checks apply; not all-model unloading."""
        trusted = self._session_manager().read(session_id).get("last_checkpoint")
        path = path or trusted
        if not path:
            raise ValueError("No checkpoint available")
        if expected_empty is None:
            source = self.settings.input_path(path)
            trusted_path = Path(trusted).expanduser() if trusted else None
            if trusted_path is not None and not trusted_path.is_absolute():
                trusted_path = self.settings.workspace / trusted_path
            same_checkpoint = trusted_path is not None and source == trusted_path.resolve()
            expected_empty = checkpoint_expected_empty(source, session_id) if same_checkpoint else False
        return self.open_in_gui_session(session_id, path, discard=True, expected_empty=expected_empty)

    def close_gui_session(self, session_id: str, save_checkpoint: bool = True) -> dict:
        """Close only the owned process. Save a final keyword checkpoint by default; never terminate unrelated GUI instances."""
        manager = self._session_manager()
        data = manager.read(session_id)
        if not data["process_alive"]:
            return data
        if save_checkpoint and data["model_kind"] == "keyword":
            result = self.checkpoint_gui_session(session_id)
            if result["status"] != "succeeded":
                return result
        with manager.lock(session_id):
            data = manager.read(session_id)
            if not alive(data["process"]):
                raise RuntimeError("Owned process changed")
            close_script = manager.directory(session_id) / ("close-" + uuid.uuid4().hex + ".cfile")
            nc.write_cfile(close_script, ["exit"])
            if data.get("engine_transport") == "queue":
                (manager.directory(session_id) / "STOP").write_text("close\n", encoding="ascii")
            else:
                WindowsCommandTransport(data["process"]["pid"]).submit(
                    nc.run_script(close_script, "cfile")
                )
            deadline = time.monotonic() + min(30, self.settings.timeout)
            while time.monotonic() < deadline and alive(data["process"]):
                time.sleep(0.1)
            data["state"] = "closed" if not alive(data["process"]) else "close_pending"
            data["closed_at"] = now()
            manager.save(session_id, data)
            return self.inspect_gui_session(session_id)
