"""Native GUI presentation output with independently checked artifacts."""

import math

from pydantic import StrictFloat, StrictInt

from .config import scl_command_path
from .fringe_presentation import averaging_command
from .gui_controls import wait_for_gui_state
from .jobs import atomic_json, check_artifact, now
from .media_validation import movie_validators, parse_movie_log, validate_mp4
from .programs import native_errors
from .scene_state import require_movie_field_coverage


class GuiMediaTools:
    def export_gui_field_animation(self, session_id: str, states: list[StrictInt], color_range: list[StrictFloat],
                                   fps: StrictInt = 10, width: StrictInt = 1280, height: StrictInt = 720) -> dict:
        """Render every requested state in LS-PrePost from the current verified alive solid/shell fringe, then explicitly encode native PNGs with FFmpeg H264. Fixed color bounds required; unchanged camera/field/averaging. Frame scope is ALL alive entities in selected parts, ignoring manual Blank during export; original Blank/state/fringe restored afterwards. Not the native Movie command. Uniform FPS; saved physical times retained without resampling. Record a render_gui_field step before this context-dependent operation for replay."""
        from .gui_field_movie import export_field_movie

        return export_field_movie(self, session_id, states, color_range, fps, width, height)

    def render_gui_field(
        self,
        session_id: str,
        entity_type: str,
        field: str,
        state: StrictInt,
        units: str,
        integration_point: str = "mid",
        part_ids: list[StrictInt] | None = None,
        color_range: list[StrictFloat] | None = None,
        averaging: str = "minmax",
        validity_policy: str = "raw",
    ) -> dict:
        """Render native field CSV/PNG with default MinMax averaging; preserve model/title captions. CSV is raw entity values, not averaged pixels. validity_policy=alive explicitly adds a LASSO MDLOPT2 mask for solid/shell, verifies native deleted-element hiding and exact CSV population; missing masks fail. Default raw retains legacy display scope. Scene/physical Blank retained; use export_gui_field_animation for explicit native PNG/FFmpeg per-state movies. No inferred units/frame/history meaning."""
        from .gui_fringe import render_field

        return render_field(
            self, session_id, entity_type, field, state, units, integration_point, part_ids, color_range, averaging,
            validity_policy
        )

    def export_gui_curve_plot(
        self,
        session_id: str,
        path: str,
        x_column: str,
        y_column: str,
        title: str,
        x_label: str,
        y_label: str,
        x_unit: str,
        y_unit: str,
    ) -> dict:
        """Render two explicit CSV columns as one new native XYPlot and export PNG plus verified XY data. Preserve row order (including hysteresis), model inventory/current state and existing plot windows. Units are declared, not converted or inferred; short ASCII labels only. Numeric native round-trip and nonblank PNG are required. No implicit solver extraction or existing-plot overwrite."""
        from .gui_curves import export_curve_plot

        return export_curve_plot(
            self, session_id, path, x_column, y_column, title, x_label, y_label, x_unit, y_unit
        )

    def export_gui_animation(
        self,
        session_id: str,
        last: StrictInt | None = None,
        fps: StrictInt = 10,
        width: StrictInt = 1280,
        height: StrictInt = 720,
        averaging: str = "minmax",
    ) -> dict:
        """Export native H264 MP4 of the current display with default MinMax averaging (explicit nodal/none supported), preserving model/result titles. State1..last step1 only; ffprobe/ffmpeg validate native sequence, frames, size/rate/duration. Restore current state; animation stopped with exported bounds. Current fringe/layer/view are used without inferring physical meaning."""
        average_command = averaging_command(averaging)
        for name, value, low, high in (
            ("fps", fps, 1, 60),
            ("width", width, 64, 3840),
            ("height", height, 64, 2160),
        ):
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in {low}..{high}")
        if width % 2 or height % 2:
            raise ValueError("H264 output requires even width and height")
        if last is not None and (type(last) is not int or not 1 <= last <= 1800):
            raise ValueError("last must be a state in 1..1800")
        validators = movie_validators()
        manager = self._session_manager()
        with manager.lock(session_id):
            meta = self._visible_mesh_session(session_id, manager, allow_results=True)
            if meta["model_kind"] != "d3plot":
                raise ValueError("Movie export requires a result GUI session")
            before = manager.dispatch(
                session_id,
                "inspect_model",
                {"include_display_scope": True} if meta.get("managed_fringe") else {},
            )
            if before["status"] != "succeeded":
                return before
            inventory = before["data"]
            final_state = inventory["counts"]["states"] if last is None else last
            if not 1 <= final_state <= min(inventory["counts"]["states"], 1800):
                raise ValueError("Movie state range exceeds the result database or 1800-frame budget")
            if final_state * width * height > 600_000_000:
                raise ValueError(
                    "Movie exceeds the 600 million pixel-frame budget; reduce resolution or states"
                )
            managed_field = require_movie_field_coverage(meta, final_state)
            if managed_field:
                if "part_visibility" not in inventory or "selection_count" not in inventory:
                    raise ValueError("Start a new GUI session for verified custom-fringe movies")
                if {int(pid) for pid, visible in inventory["part_visibility"].items() if visible} != set(
                    managed_field["definition"]["parts"]
                ) or inventory["selection_count"]:
                    raise ValueError(
                        "Custom-fringe movie display scope changed; re-render the field before exporting"
                    )
            original = inventory["current_state"]
            if type(original) is not int or not 1 <= original <= inventory["counts"]["states"]:
                raise ValueError("Cannot establish the original result state")
            times = inventory.get("state_times", [])
            if len(times) < final_state or any(
                type(t) not in (int, float) or not math.isfinite(t) for t in times[:final_state]
            ):
                raise ValueError("Native movie timeline has missing or nonfinite state times")
            parameters = dict(last=final_state, fps=fps, width=width, height=height, averaging=averaging)
            directory, manifest = self.jobs.create(
                "export_gui_animation", dict(session_id=session_id, **parameters)
            )
            manifest.update(
                status="running",
                started_at=now(),
                session_id=session_id,
                job_directory=str(directory),
                backend="lsprepost",
                execution_mode="visible_gui_native_movie",
                process=meta["process"],
            )
            atomic_json(directory / "before.json", inventory)
            atomic_json(directory / "validators.json", validators)
            movie = directory / "animation.mp4"
            log = manager.directory(session_id) / "lspost.msg"
            try:
                ready, evidence = wait_for_gui_state(
                    manager, session_id, 1, self.settings.timeout, native_commands=["anim stop", "state 1"]
                )
                manifest["initial_state_observations"] = evidence
                if ready["status"] != "succeeded":
                    raise ValueError("Cannot verify the initial movie state")
                commands = [
                    "anim stop",
                    average_command,
                    "anim first 1",
                    f"anim last {final_state}",
                    "anim incr 1",
                    f"movie MP4/H264 {width}x{height} {scl_command_path(movie.with_suffix(''))} {fps}",
                ]
                atomic_json(directory / "commands.json", commands)
                offset = log.stat().st_size if log.exists() else 0
                native = manager.dispatch(session_id, "inspect_model", {}, native_commands=commands)
                manifest["native_request"] = {k: v for k, v in native.items() if k != "data"}
                if native["status"] != "succeeded":
                    raise ValueError("Native movie request did not complete")
                with log.open("rb") as stream:
                    stream.seek(offset)
                    text = stream.read().decode("utf8", errors="replace")
                (directory / "native-movie.log").write_text(text, encoding="utf8")
                if native_errors(text):
                    raise ValueError("Native movie diagnostics reported errors")
                sequence = parse_movie_log(text, list(range(1, final_state + 1)))
                video = validate_mp4(
                    movie, width, height, fps, final_state, validators, self.settings.timeout
                )
                manifest.update(
                    status="succeeded",
                    data=dict(
                        video=video,
                        sequence=sequence,
                        state_times=inventory["state_times"][:final_state],
                        time_unit="model_time_unspecified",
                        rendering="current_native_display",
                        field_semantics_verified=False,
                        managed_field=managed_field,
                        display_averaging=averaging,
                        title_policy="Preserve existing model/result titles; no title commands or suffixes",
                        animation_controls_after=dict(first=1, last=final_state, increment=1, playing=False),
                    ),
                )
            except Exception as exc:
                manifest.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
            finally:
                try:
                    restored, evidence = wait_for_gui_state(
                        manager,
                        session_id,
                        original,
                        self.settings.timeout,
                        native_commands=["anim stop", f"state {original}"],
                    )
                    manifest["state_restoration"] = dict(
                        original=original,
                        observed=restored.get("data", {}).get("current_state"),
                        observations=evidence,
                    )
                    if restored["status"] != "succeeded":
                        raise ValueError("Original result state could not be restored")
                    if (
                        restored["data"]["counts"] != inventory["counts"]
                        or restored["data"]["part_ids"] != inventory["part_ids"]
                    ):
                        raise ValueError("Native model inventory changed during movie export")
                except Exception as exc:
                    manifest.update(status="failed", restoration_error=str(exc))
            if manifest["status"] == "succeeded":
                manifest["artifacts"] = [check_artifact(movie, "validated_native_mp4")]
            manifest["finished_at"] = now()
            atomic_json(directory / "job.json", manifest)
            manager.journal(
                session_id, dict(action="export_gui_animation", parameters=parameters, result=manifest)
            )
            return manifest
