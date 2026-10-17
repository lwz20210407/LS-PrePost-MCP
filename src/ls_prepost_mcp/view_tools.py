"""G01 set_view target tool over the existing gui_display session route and prepared batch programs."""

from typing import Literal

from pydantic import StrictFloat

from .core.contracts import Artifact, CheckResult, JobResult
from .jobs import fingerprint, now
from .native import commands as nc
from .view_state import VIEW_FRAME, PresetBinding, ViewRequest, load_preset, preset_path, save_preset

BACKEND = "lsprepost"
SELECTOR_CENTERING_GAP = ("Selector centering is unsupported: no verified native command maps a resolved Selector "
                          "to a camera target or selected-only fit without changing selection or visibility")


def _result(status, data, **fields):
    return JobResult(operation="set_view", status=status, backend=BACKEND, data=data, **fields).model_dump(mode="json")


def _artifact(item):
    return Artifact(path=item["path"], kind=item["kind"], sha256=item["sha256"], size_bytes=item["size"],
                    verification="verified")


class ViewTools:
    def _view_presets(self):
        return self.settings.workspace / "view_presets"

    def set_view(
        self,
        context: Literal["batch", "session"] = "batch",
        session_id: str | None = None,
        model: str | None = None,
        file_type: Literal["keyword", "d3plot"] = "keyword",
        view: Literal["isometric", "top", "bottom", "front", "back", "left", "right"] | None = None,
        projection: Literal["parallel", "perspective"] | None = None,
        rotation_xyz_degrees: list[StrictFloat] | None = None,
        zoom_scale: StrictFloat | None = None,
        pan_xy: list[StrictFloat] | None = None,
        fit: bool = False,
        center_on: dict | None = None,
        save_preset_name: str | None = None,
        restore_preset_name: str | None = None,
        capture: bool = True,
    ) -> dict:
        """G01: standard view, projection, incremental global X/Y/Z rotation, fit, then ABSOLUTE native zoom_scale and pan_xy (pan is a native view offset, not a model length; "zoom 2x" needs the absolute value). context=session uses the given existing GUI session (never starts one); context=batch only prepares a reviewed cfile/PNG program for the given model because headless rendering is unverified. Named presets store the replayable request (explicit view+projection), bound to the session model generation or batch input bytes, never a captured native camera. center_on (Selector) is validated and rejected as unsupported. Returns JobResult/v1."""
        if context not in ("batch", "session") or type(capture) is not bool:
            raise ValueError("context must be batch or session and capture must be Boolean")
        if context == "session" and (not session_id or model is not None):
            raise ValueError("Session context requires an existing session_id and no batch model")
        if context == "batch" and (session_id is not None or not model):
            raise ValueError("Batch context requires model and no session_id")
        if context == "batch" and not capture:
            raise ValueError("A batch view only has an effect through a captured PNG")
        if file_type not in ("keyword", "d3plot"):
            raise ValueError("file_type must be keyword or d3plot")
        camera = dict(view=view, projection=projection, rotation_xyz_degrees=rotation_xyz_degrees,
                      zoom_scale=zoom_scale, pan_xy=pan_xy, center_on=center_on)
        if restore_preset_name is not None:
            if fit or save_preset_name is not None or any(v is not None for v in camera.values()):
                raise ValueError("Restoring a preset cannot be combined with other view changes or a save")
            preset_path(self._view_presets(), restore_preset_name)
            request = None
        else:
            request = ViewRequest(fit=fit, **{k: v for k, v in camera.items() if v is not None})
            if request.center_on is not None:
                return _result("failed", dict(request=request.model_dump(mode="json"), context=context),
                               error=dict(type="unsupported", message=SELECTOR_CENTERING_GAP),
                               checks=[CheckResult(name="selector_centering", status="missing")])
            if save_preset_name is not None:
                if preset_path(self._view_presets(), save_preset_name).exists():
                    raise ValueError("A preset with this name already exists; choose another name")
                if not request.replayable:
                    raise ValueError("Saving a preset requires an explicit standard view and projection")
        if context == "session":
            manager = self._session_manager()
            with manager.lock(session_id):
                meta = manager.read(session_id)
                binding = PresetBinding(context="session", session_id=session_id,
                                        model_generation=meta.get("model_generation"),
                                        model_kind=meta["model_kind"],
                                        executable_sha256=(meta.get("executable") or {}).get("sha256"))
                preset = None
                if request is None:
                    request, preset = load_preset(self._view_presets(), restore_preset_name, binding)
                commands = request.commands()
                reply = manager.dispatch(session_id, "gui_display", dict(commands=commands, state=None, capture=capture),
                                         artifacts=(("snapshot.png", "png"),) if capture else ())
                manager.journal(session_id, dict(action="set_view", parameters=dict(
                    request=request.model_dump(mode="json"), restore_preset=restore_preset_name,
                    save_preset=save_preset_name, capture=capture), result=reply))
            if reply["status"] != "succeeded":
                return _result("failed", dict(request=request.model_dump(mode="json"), commands=commands),
                               job_id=reply.get("request_id"),
                               error=dict(reply.get("error") or {"message": "Native view request failed"}))
            artifacts = [_artifact(item) for item in reply.get("artifacts", [])]
            job_id, stage, status = reply.get("request_id"), "execution", "succeeded"
            execution = dict(native_applied_commands=(reply.get("data") or {}).get("applied_commands"),
                             session_id=session_id, job_directory=reply.get("job_directory"))
        else:
            source = self.settings.input_path(model)
            identity = fingerprint(source)
            if identity["sha256"] is None:
                raise ValueError("Batch view presets and programs need a hashable input (64 MiB or less)")
            try:
                executable = fingerprint(self.settings.native_executable())["sha256"]
            except ValueError:
                executable = None
            binding = PresetBinding(context="batch", model_kind=file_type, model_sha256=identity["sha256"],
                                    executable_sha256=executable)
            preset = None
            if request is None:
                request, preset = load_preset(self._view_presets(), restore_preset_name, binding)
            commands = request.commands()
            prepared = self.prepare_native_program("cfile", code="\n".join([*commands, nc.print_png("view.png")]),
                                                   outputs=[dict(name="view.png", kind="png")])
            artifacts, job_id, stage, status = [], prepared["job_id"], "preparation", "unverified"
            execution = dict(prepared_job_id=prepared["job_id"], prepared_sha256=prepared["data"]["sha256"],
                             model=identity, file_type=file_type, native_started=False,
                             next_step="execute_native_program with this job and SHA256 after an authorized "
                                       "graphics mode; headless PNG rendering is not verified")
        saved = None
        if save_preset_name is not None:
            path, body = save_preset(self._view_presets(), save_preset_name, request, binding, now())
            saved = dict(name=save_preset_name, path=str(path), payload_sha256=body["payload_sha256"])
        data = dict(context=context, request=request.model_dump(mode="json"), commands=commands, frame=VIEW_FRAME,
                    replayable=request.replayable, content_dependent=request.content_dependent,
                    camera_state="applied_unverified" if stage == "execution" else "not_applied",
                    native_camera_readback=False, execution=execution, saved_preset=saved,
                    restored_preset=None if preset is None else dict(
                        name=restore_preset_name, kind=preset["kind"], payload_sha256=preset["payload_sha256"]))
        warnings = ["Native camera state is not read back; the request is applied, not verified"]
        if stage == "preparation":
            warnings.append("Batch rendering was prepared only; no native process was started")
        return _result(status, data, job_id=job_id, stage=stage, artifacts=artifacts, warnings=warnings,
                       scope="native view request; camera matrix, named native views and Selector centering are gaps")
