"""Typed controls for common menu/right/bottom toolbar operations."""

import math
import time
from pathlib import Path

from pydantic import StrictFloat

from .fringe_presentation import averaging_command
from .jobs import atomic_json
from .native import commands as nc


def camera_commands(zoom_scale=None, pan_xy=None, rotation_xyz_degrees=None):
    """Validate all camera inputs before dispatch; native zoom/pan setters are absolute."""
    def values(value, length, name, bound):
        if not isinstance(value, list) or len(value) != length or any(
            type(v) not in (int, float) or not math.isfinite(v) or abs(v) > bound for v in value
        ):
            raise ValueError(name+" requires "+str(length)+" finite numbers within +/-"+str(bound))
        return [float(v) for v in value]
    rotations, after_fit = [], []
    if zoom_scale is not None:
        if type(zoom_scale) not in (int, float) or not math.isfinite(zoom_scale) or not 0.01 <= zoom_scale <= 100:
            raise ValueError("zoom_scale must be a finite native absolute scale in 0.01..100")
        after_fit.append("zoom "+format(zoom_scale, ".17g"))
    if pan_xy is not None:
        pan = values(pan_xy, 2, "pan_xy", 100)
        after_fit.append("pan "+" ".join(format(v, ".17g") for v in pan))
    if rotation_xyz_degrees is not None:
        angles = values(rotation_xyz_degrees, 3, "rotation_xyz_degrees", 360)
        for axis, angle in zip("xyz", angles, strict=True):
            if angle:
                rotations.extend(["rotang "+format(angle, ".17g"), "r"+axis])
    return rotations, after_fit


def wait_for_gui_state(manager, session_id, requested, timeout, native_commands=()):
    """Observe queued state changes after the embedded callback returns; never replay them."""
    deadline = time.monotonic() + min(timeout, 10.0)
    observations = []
    while True:
        options = dict(native_commands=native_commands) if native_commands else {}
        observed = manager.dispatch(session_id, "inspect_model", {}, **options)
        native_commands = ()
        observations.append(
            dict(
                job_directory=observed.get("job_directory"),
                current_state=(observed.get("data") or {}).get("current_state"),
                status=observed["status"],
            )
        )
        if observed["status"] != "succeeded" or observations[-1]["current_state"] == requested:
            return observed, observations
        if time.monotonic() >= deadline:
            observed.update(
                status="failed",
                error=dict(
                    message="Native result state did not settle to the requested state; no automatic replay"
                ),
            )
            return observed, observations
        time.sleep(0.05)


class GuiControls:
    def set_gui_display(
        self,
        session_id: str,
        view: str | None = None,
        display_mode: str | None = None,
        background: list[float] | None = None,
        projection: str | None = None,
        legend: bool | None = None,
        triad: bool | None = None,
        timestamp: bool | None = None,
        title: bool | None = None,
        state: int | None = None,
        fringe_code: int | None = None,
        center: bool = False,
        capture: bool = True,
        averaging: str | None = None,
        zoom_scale: StrictFloat | None = None,
        pan_xy: list[StrictFloat] | None = None,
        rotation_xyz_degrees: list[StrictFloat] | None = None,
    ) -> dict:
        """Set native GUI view/display/projection/overlays/state/fringe; optionally capture PNG. zoom_scale and pan_xy are ABSOLUTE native view settings, not multipliers/deltas or model-coordinate edits. Incremental global X/Y/Z view rotations run in that order, before optional center-fit; zoom/pan follow fit. Last nonzero rotation step remains in native toolbar settings. Preserve model/result titles unless explicitly toggled. Defaults retain the current camera."""
        from .service import VIEWS, integer, numbers

        rotations, after_fit = camera_commands(zoom_scale, pan_xy, rotation_xyz_degrees)
        commands = []
        if averaging is not None:
            commands.append(averaging_command(averaging))
        if view is not None:
            if view not in VIEWS and view != "home":
                raise ValueError("Unknown view")
            commands.append("home" if view == "home" else VIEWS[view])
        modes = {
            "shaded": "shad",
            "wireframe": "wire",
            "hidden": "hide",
            "edge": "edge",
            "feature": "feat",
            "grid": "grid",
            "flat": "view",
        }
        if display_mode is not None:
            if display_mode not in modes:
                raise ValueError("Unknown display mode")
            commands.append(modes[display_mode])
        if background is not None:
            rgb = numbers(background, 3, "background")
            if any(v < 0 or v > 1 for v in rgb):
                raise ValueError("RGB values must be in [0,1]")
            commands.append("background " + " ".join(map(str, rgb)))
        if projection is not None:
            if projection not in ("parallel", "perspective"):
                raise ValueError("Invalid projection")
            commands.append(projection)
        for value, command in [
            (legend, "showlegend"),
            (triad, "showtriad"),
            (timestamp, "timestamp"),
            (title, "title toggle"),
        ]:
            if value is not None:
                if type(value) is not bool:
                    raise ValueError("Display toggles require booleans")
                commands.append(command + " " + str(int(value)))
        if state is not None:
            integer(state, "state")
        manager = self._session_manager()
        if fringe_code is not None:
            integer(fringe_code, "fringe_code", 1, 9999)
            if manager.read(session_id)["model_kind"] != "d3plot":
                raise ValueError("Fringe requires a result session")
            commands += [nc.fringe(fringe_code), nc.plot_fringe()]
        commands.extend(rotations)
        if center:
            commands.append("ac")
        commands.extend(after_fit)
        p = dict(commands=commands, state=None, capture=capture if state is None else False)
        with manager.lock(session_id):
            if state is not None:
                baseline = manager.dispatch(session_id, "inspect_model", {})
                if baseline["status"] != "succeeded":
                    return baseline
                if state > baseline["data"].get("counts", {}).get("states", 0):
                    raise ValueError("Requested GUI state is outside the loaded result database")
            result = manager.dispatch(
                session_id,
                "gui_display",
                p,
                artifacts=(("snapshot.png", "png"),) if p["capture"] else (),
                native_commands=[nc.animation('stop'), nc.state(state)] if state is not None else (),
            )
            if state is not None and result["status"] == "succeeded":
                initial_request = result["job_directory"]
                observed, observations = wait_for_gui_state(manager, session_id, state, self.settings.timeout)
                if observed["status"] != "succeeded":
                    result = observed
                elif capture:
                    result = manager.dispatch(
                        session_id,
                        "gui_display",
                        dict(commands=[], state=None, capture=True),
                        artifacts=(("snapshot.png", "png"),),
                    )
                else:
                    result["data"]["current_state"] = observed["data"]["current_state"]
                if result["status"] == "succeeded" and result["data"].get("current_state") != state:
                    result.update(
                        status="failed",
                        error=dict(message="Result state changed before display capture completed"),
                    )
                result["state_transition"] = dict(
                    requested_state=state,
                    command_job_directory=initial_request,
                    observations=observations,
                    verified=result["status"] == "succeeded",
                )
                atomic_json(Path(result["job_directory"]) / "operation.json", result)
            arguments = dict(
                view=view,
                display_mode=display_mode,
                background=background,
                projection=projection,
                legend=legend,
                triad=triad,
                timestamp=timestamp,
                title=title,
                state=state,
                fringe_code=fringe_code,
                center=center,
                capture=capture,
                averaging=averaging,
                zoom_scale=zoom_scale,
                pan_xy=pan_xy,
                rotation_xyz_degrees=rotation_xyz_degrees,
            )
            manager.journal(session_id, dict(action="set_gui_display", parameters=arguments, result=result))
            if fringe_code is not None:
                meta = manager.read(session_id)
                if meta.get("managed_fringe") is not None:
                    meta["managed_fringe"]["status"] = "changed_by_numeric_fringe_code"
                    manager.save(session_id,meta)
            return result

    def set_gui_part_visibility(self, session_id: str, mode: str, part_ids: list[int] | None = None) -> dict:
        """Show, hide, isolate or restore all parts in the same GUI; verifies every part's native visibility flag."""
        from .post_backend import ids

        if mode not in ("show", "hide", "isolate", "all"):
            raise ValueError("Invalid visibility mode")
        if mode != "all":
            ids(part_ids, "part_ids", 1000)
        manager = self._session_manager()
        p = dict(mode=mode, part_ids=part_ids or [])
        with manager.lock(session_id):
            result = manager.dispatch(session_id, "gui_parts", p)
            manager.journal(session_id, dict(action="set_gui_part_visibility", parameters=p, result=result))
            return result

    def control_gui_animation(
        self,
        session_id: str,
        operation: str,
        first: int = 1,
        last: int = 1,
        increment: int = 1,
        direction: str = "forward",
    ) -> dict:
        """Start/stop native animation with explicit bounds and direction in a persistent result session."""
        from .service import integer

        if operation not in ("start", "stop") or direction not in ("forward", "backward", "cycle"):
            raise ValueError("Invalid animation operation/direction")
        integer(first, "first")
        integer(last, "last")
        integer(increment, "increment")
        if first > last:
            raise ValueError("Animation first must not exceed last")
        manager = self._session_manager()
        if manager.read(session_id)["model_kind"] != "d3plot":
            raise ValueError("Animation requires a result session")
        p = dict(operation=operation, first=first, last=last, increment=increment, direction=direction)
        with manager.lock(session_id):
            result = manager.dispatch(session_id, "gui_animation", p)
            manager.journal(session_id, dict(action="control_gui_animation", parameters=p, result=result))
            return result
