"""Persistent native GUI sessions with process identity, serialized requests and checkpoints."""

import contextlib
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from .config import command_path
from .jobs import atomic_json, check_artifact, fingerprint, now
from .native_config import isolate_preferences
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

    def start(self):
        WindowsCommandTransport(0).require_interactive_desktop()
        if os.name != "nt":
            raise RuntimeError("Persistent GUI sessions currently support Windows")
        exe = self.settings.native_executable()
        ident = uuid.uuid4().hex
        directory = self.directory(ident)
        directory.mkdir(parents=True)
        (directory / "tmp").mkdir()
        shutil.copyfile(Path(__file__).with_name("embedded.py"), directory / "bridge.py")
        bootstrap = directory / "initialize.py"
        ready = directory / "ready.json"
        (directory / "initial.k").write_text("*KEYWORD\n*TITLE\nMCP session model\n*END\n", encoding="ascii")
        bootstrap.write_text(
            "import os,json,builtins,LsPrePost as lp\nos.chdir(" + repr(str(directory)) + ")\n"
            "lp.execute_command(" + repr("open keyword " + command_path(directory / "initial.k")) + ")\n"
            "builtins._lspp_mcp_session=" + repr(ident) + "\n"
            'json.dump({"session_id":'
            + repr(ident)
            + ',"pid":os.getpid()},open('
            + repr(str(ready))
            + ',"w"))\n',
            encoding="utf8",
        )
        cfile = directory / "initialize.cfile"
        # A fresh process needs no `new`: some GUI builds treat it as Restart
        # and block the startup command file behind a confirmation dialog.
        cfile.write_text("runpython " + command_path(bootstrap) + "\n", encoding="utf8")
        env, configuration = isolate_preferences(exe, directory)
        env.update(TEMP=str(directory / "tmp"), TMP=str(directory / "tmp"))
        with (directory / "process.log").open("wb") as log:
            process = subprocess.Popen(
                [str(exe), "c=" + str(cfile), "w=1200x800"],
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
            transport="owned-process Windows command entry + finite embedded Python",
            bridge_protocol=3,
            recording=None,
            configuration=configuration,
        )
        self.save(ident, data)
        deadline = time.monotonic() + min(60, self.settings.timeout)
        while time.monotonic() < deadline:
            if ready.exists():
                response = json.loads(ready.read_text())
                if response != {"session_id": ident, "pid": process.pid}:
                    raise RuntimeError("Native bootstrap identity mismatch")
                WindowsCommandTransport(process.pid).command_window()
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
        )
        atomic_json(directory / "request.json", request)
        atomic_json(
            directory / "contract.json",
            dict(artifacts=list(artifacts), export=export, was_uncertain=was_uncertain),
        )
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
                "    lp.execute_command('save keyword \"model.k\"')\n"
            )
        code += "os.replace(" + repr(str(response)) + "," + repr(str(directory / "complete.json")) + ")\n"
        bootstrap = directory / "dispatch.py"
        bootstrap.write_text(code, encoding="utf8")
        command_file = directory / "dispatch.cfile"
        # Let LS-PrePost itself interpret selection/edit commands outside the
        # embedded Python callback, then use Python only for readback.
        command_file.write_text(
            "\n".join(list(native_commands) + ["runpython " + command_path(bootstrap)]) + "\n",
            encoding="utf8",
        )
        data.update(state="busy", active_request=directory.name)
        self.save(ident, data)
        try:
            WindowsCommandTransport(data["process"]["pid"]).submit(
                "openc command " + command_path(command_file) + " nodialog"
            )
        except Exception as exc:
            data.update(state="uncertain", last_error=str(exc))
            self.save(ident, data)
            raise
        deadline = time.monotonic() + self.settings.timeout
        while time.monotonic() < deadline:
            if (directory / "complete.json").exists():
                reply = json.loads((directory / "complete.json").read_text(encoding="utf8"))
                if reply.get("job_id") != directory.name:
                    raise RuntimeError("Native response correlation mismatch")
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
                        result["artifacts"] = [
                            check_artifact(directory / name, kind) for name, kind in artifacts
                        ]
                    except Exception as exc:
                        result.update(status="failed", error={"message": str(exc)})
                data.update(
                    state="ready"
                    if result["status"] == "succeeded" and (not was_uncertain or model or action == "gui_new")
                    else "uncertain",
                    active_request=None,
                )
                self.save(ident, data)
                atomic_json(directory / "operation.json", result)
                return result
            if not alive(data["process"]):
                break
            time.sleep(0.05)
        data.update(state="uncertain", last_error="No completion received; do not blindly replay mutation")
        self.save(ident, data)
        raise TimeoutError("Native operation outcome uncertain; inspect session or restore checkpoint")

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
        """Reconcile a late completed request after a timeout/server restart without replaying it. Pending native work remains uncertain."""
        manager = self._session_manager()
        with manager.lock(session_id):
            meta = manager.read(session_id)
            request_id = meta.get("active_request")
            if not request_id:
                return meta
            directory = manager.directory(session_id) / "requests" / request_id
            complete = directory / "complete.json"
            if not complete.exists():
                return dict(**meta, recovery="No correlated completion yet; nothing replayed")
            reply = json.loads(complete.read_text(encoding="utf8"))
            if reply.get("job_id") != request_id:
                raise RuntimeError("Late response identity mismatch")
            contract = json.loads((directory / "contract.json").read_text(encoding="utf8"))
            if not reply.get("ok"):
                meta.update(state="uncertain", active_request=None)
                manager.save(session_id, meta)
                return dict(
                    **meta,
                    recovery="Native action failed; restore a checkpoint",
                    native_error=reply.get("error"),
                )
            artifacts = [check_artifact(directory / name, kind) for name, kind in contract["artifacts"]]
            request = json.loads((directory / "request.json").read_text(encoding="utf8"))
            state = (
                "uncertain"
                if contract.get("was_uncertain")
                and not request.get("model")
                and request["action"] != "gui_new"
                else "ready"
            )
            meta.update(state=state, active_request=None)
            if contract["export"]:
                meta.update(last_checkpoint=str(directory / "model.k"), dirty=False)
            if request.get("model"):
                meta.update(model_kind=request["file_type"], staged_model=request["model"], dirty=False)
            manager.save(session_id, meta)
            return dict(**meta, recovery="Late completion reconciled; no replay", artifacts=artifacts)

    def reset_gui_session(self, session_id: str, save_checkpoint: bool = True) -> dict:
        """Start a new empty model in the same GUI, preserving a checkpoint of the prior keyword model by default."""
        manager = self._session_manager()
        with manager.lock(session_id):
            meta = manager.read(session_id)
            info = manager.dispatch(session_id, "inspect_model", {})
            if info["status"] != "succeeded":
                return info
            if (
                save_checkpoint
                and meta["model_kind"] == "keyword"
                and info["data"].get("counts", {}).get("nodes", 0) > 0
            ):
                saved = manager.dispatch(
                    session_id, "export_keyword", {}, artifacts=(("model.k", "keyword"),), export=True
                )
                if saved["status"] != "succeeded":
                    return saved
                meta["last_checkpoint"] = saved["artifacts"][0]["path"]
            result = manager.dispatch(session_id, "gui_new", {})
            if result["status"] == "succeeded":
                updated = manager.read(session_id)
                updated.update(
                    model_kind="keyword",
                    dirty=False,
                    last_checkpoint=meta.get("last_checkpoint"),
                    source=None,
                    staged_model=None,
                    selection_buffers={},
                )
                manager.save(session_id, updated)
            manager.journal(session_id, dict(action="new_model", parameters={}, result=result))
            return result

    def _session_manager(self):
        return Sessions(self.settings)

    def start_gui_session(self) -> dict:
        """Start an owned persistent native GUI process; subsequent tools reuse its model and normal event loop. Windows only; configured embedded Python required."""
        return self._session_manager().start()

    def inspect_gui_session(self, session_id: str) -> dict:
        """Read process identity, health, dirty/checkpoint state and the last correlated request."""
        return self._session_manager().read(session_id)

    def restart_gui_session(self, session_id: str) -> dict:
        """Recover an exited owned session into a new visible process using its last checkpoint or staged result source; never replay uncertain commands or terminate a live process."""
        old = self._session_manager().read(session_id)
        if old["process_alive"]:
            raise ValueError(
                "The original GUI process is still alive; inspect/recover it instead of duplicating it"
            )
        source = (
            (old.get("last_checkpoint") or old.get("staged_model"))
            if old["model_kind"] == "keyword"
            else old.get("staged_model")
        )
        new = self.start_gui_session()
        if source:
            opened = self.open_in_gui_session(new["session_id"], source, old["model_kind"])
            if opened["status"] != "succeeded":
                return dict(
                    status="failed",
                    previous_session_id=session_id,
                    session_id=new["session_id"],
                    restoration=opened,
                )
        else:
            opened = None
        self.show_gui_session(new["session_id"], maximize=True)
        return dict(
            status="succeeded",
            previous_session_id=session_id,
            session_id=new["session_id"],
            restoration=opened,
            recovery_scope="Saved model/source only; unsaved manual changes and uncertain commands are not replayed",
        )

    def open_in_gui_session(
        self, session_id: str, path: str, file_type: str = "keyword", discard: bool = False
    ) -> dict:
        """Open a staged copy in the existing GUI. Dirty managed models require an explicit discard or prior checkpoint."""
        manager = self._session_manager()
        with manager.lock(session_id):
            data = manager.read(session_id)
            if data["dirty"] and not discard:
                raise ValueError(
                    "Checkpoint the current model before replacement, or explicitly set discard=true"
                )
            staged = manager.stage_input(session_id, path, file_type)
            result = manager.dispatch(session_id, "inspect_model", {}, model=staged, file_type=file_type)
            if result["status"] == "succeeded":
                data = manager.read(session_id)
                data.update(
                    model_kind=file_type,
                    dirty=False,
                    source=str(self.settings.input_path(path)),
                    staged_model=str(staged),
                    selection_buffers={},
                    last_checkpoint=str(staged) if file_type == "keyword" else None,
                )
                manager.save(session_id, data)
            manager.journal(
                session_id,
                dict(action="open", parameters=dict(path=path, file_type=file_type), result=result),
            )
            return result

    def gui_session_action(self, session_id: str, action: str, parameters: dict) -> dict:
        """Execute an existing typed native operation against the same in-memory model; no unrestricted script or shell. Failed mutations mark state uncertain."""
        import inspect

        from .service import Service

        if action not in NATIVE_ACTIONS:
            raise ValueError("Unsupported persistent action")
        if not isinstance(parameters, dict) or "model" in parameters or "d3plot" in parameters:
            raise ValueError("Use open_in_gui_session to change the input model")
        if action in ("extract_native_fields", "extract_native_stress"):
            from .gui_fields import run_fields

            return run_fields(self, session_id, action, parameters)
        manager = self._session_manager()
        if action in GUI_BATCH_ACTIONS and manager.read(session_id).get("bridge_protocol", 1) >= 3:
            routed = {"translate_mesh_nodes": "translate_gui_nodes", "rotate_mesh_nodes": "rotate_gui_nodes"}[
                action
            ]
            return getattr(self, routed)(session_id=session_id, **parameters)
        with manager.lock(session_id):
            meta = manager.read(session_id)
            if meta["state"] == "uncertain" and action in MUTATIONS:
                raise ValueError("Restore/reopen a checkpoint before more mutations")
            if meta["model_kind"] != "keyword" and action in MUTATIONS:
                raise ValueError("Mesh edits require a keyword session")
            service = Service(self.settings)
            captured = {}

            def capture(
                native_action, p, model=None, file_type="keyword", graphics=False, artifacts=(), export=False
            ):
                captured.update(
                    action=native_action,
                    parameters=p,
                    file_type=file_type,
                    artifacts=artifacts,
                    export=export,
                )
                return captured

            service._native = capture
            supplied = dict(parameters)
            sig = inspect.signature(getattr(service, action))
            if "model" in sig.parameters:
                supplied["model"] = None
            if "d3plot" in sig.parameters:
                supplied["d3plot"] = None
            if "file_type" in sig.parameters:
                supplied["file_type"] = meta["model_kind"]
            getattr(service, action)(**supplied)
            if not captured:
                raise RuntimeError("Action did not produce a native request")
            if action in GUI_BATCH_ACTIONS:
                # Some GUI builds record selection/transform commands but do not
                # change coordinates. Use the independently checked native route;
                # preserve the same visible GUI and disclose the extra process.
                saved = manager.dispatch(
                    session_id, "export_keyword", {}, artifacts=(("model.k", "keyword"),), export=True
                )
                if saved["status"] != "succeeded":
                    return saved
                checkpoint = saved["artifacts"][0]["path"]
                meta = manager.read(session_id)
                meta.update(last_checkpoint=checkpoint, dirty=False)
                manager.save(session_id, meta)
                batch = getattr(Service(self.settings), action)(model=checkpoint, **parameters)
                if batch["status"] != "succeeded":
                    result = dict(
                        batch,
                        session_id=session_id,
                        execution_mode="native_checkpoint_batch_reopen",
                        gui_model_replaced=False,
                    )
                else:
                    output = batch["artifacts"][0]["path"]
                    staged = manager.stage_input(session_id, output, "keyword")
                    result = manager.dispatch(session_id, "inspect_model", {}, model=staged)
                    result.update(
                        execution_mode="native_checkpoint_batch_reopen",
                        native_job_id=batch["job_id"],
                        native_verification=batch.get("data"),
                        artifacts=batch["artifacts"],
                        gui_model_replaced=result["status"] == "succeeded",
                    )
                    if result["status"] == "succeeded":
                        meta = manager.read(session_id)
                        meta.update(
                            last_checkpoint=output,
                            staged_model=str(staged),
                            source=output,
                            dirty=False,
                            selection_buffers={},
                        )
                        manager.save(session_id, meta)
                manager.journal(session_id, dict(action=action, parameters=parameters, result=result))
                return result
            result = manager.dispatch(session_id, **captured)
            if captured["action"] in ("extract_nodal", "node_history") and result["status"] == "succeeded":
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
                        native_commands=["anim stop", "state %d" % requested],
                    )
                    result["data"]["state_restored"] = observed["status"] == "succeeded"
                    result["state_restoration"] = dict(requested_state=requested, observations=evidence)
                    if observed["status"] != "succeeded":
                        result.update(status="failed", error=observed.get("error"))
                atomic_json(Path(result["job_directory"]) / "operation.json", result)
            data = manager.read(session_id)
            if action in MUTATIONS:
                data["dirty"] = True
            if captured["export"] and result["status"] == "succeeded":
                data.update(last_checkpoint=result["artifacts"][0]["path"], dirty=False)
            manager.save(session_id, data)
            manager.journal(session_id, dict(action=action, parameters=parameters, result=result))
            return result

    def checkpoint_gui_session(self, session_id: str) -> dict:
        """Save current keyword model to a fresh owned checkpoint and return the file identity."""
        if self._session_manager().read(session_id)["model_kind"] != "keyword":
            raise ValueError("Keyword checkpoint requires a keyword session")
        return self.gui_session_action(session_id, "export_keyword", {})

    def restore_gui_checkpoint(self, session_id: str, path: str | None = None) -> dict:
        """Explicitly replace current in-memory state with a saved checkpoint, leaving the failed operation evidence intact."""
        path = path or self._session_manager().read(session_id).get("last_checkpoint")
        if not path:
            raise ValueError("No checkpoint available")
        return self.open_in_gui_session(session_id, path, discard=True)

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
            close_script.write_text("exit\n", encoding="ascii")
            WindowsCommandTransport(data["process"]["pid"]).submit(
                "openc command " + command_path(close_script) + " nodialog"
            )
            deadline = time.monotonic() + min(30, self.settings.timeout)
            while time.monotonic() < deadline and alive(data["process"]):
                time.sleep(0.1)
            data["state"] = "closed" if not alive(data["process"]) else "close_pending"
            data["closed_at"] = now()
            manager.save(session_id, data)
            return self.inspect_gui_session(session_id)
