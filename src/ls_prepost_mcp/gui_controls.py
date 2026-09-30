"""Typed controls for common menu/right/bottom toolbar operations."""


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
    ) -> dict:
        """Set the current persistent GUI's view, display mode, RGB background, projection, overlays or result state/fringe. Optionally capture the unchanged current camera."""
        from .service import VIEWS, integer, numbers

        commands = []
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
            commands += ["fringe " + str(fringe_code), "pfringe"]
        if center:
            commands.append("ac")
        p = dict(commands=commands, state=state, capture=capture)
        with manager.lock(session_id):
            result = manager.dispatch(
                session_id, "gui_display", p, artifacts=(("snapshot.png", "png"),) if capture else ()
            )
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
            )
            manager.journal(session_id, dict(action="set_gui_display", parameters=arguments, result=result))
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
