"""Native GUI presentation output with independently checked artifacts."""

import math

from pydantic import StrictInt

from .config import scl_command_path
from .gui_controls import wait_for_gui_state
from .jobs import atomic_json, check_artifact, now
from .media_validation import movie_validators, parse_movie_log, validate_mp4
from .programs import native_errors


class GuiMediaTools:
    def export_gui_animation(
        self,
        session_id: str,
        last: StrictInt | None = None,
        fps: StrictInt = 10,
        width: StrictInt = 1280,
        height: StrictInt = 720,
    ) -> dict:
        """Export native H264 MP4 of the current display, from state1 through last inclusive, step1 only. Requires ffprobe/ffmpeg for validation (no transcoding). Restore current state; leave animation stopped with exported bounds. Native log sequence, decoded frames, dimensions, rate and duration must agree. Current fringe/layer/view are used without inferring their physical meaning. Non-unit steps or later starts are intentionally unsupported after failed native probes."""
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
            before = manager.dispatch(session_id, "inspect_model", {})
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
            original = inventory["current_state"]
            if type(original) is not int or not 1 <= original <= inventory["counts"]["states"]:
                raise ValueError("Cannot establish the original result state")
            times = inventory.get("state_times", [])
            if len(times) < final_state or any(
                type(t) not in (int, float) or not math.isfinite(t) for t in times[:final_state]
            ):
                raise ValueError("Native movie timeline has missing or nonfinite state times")
            parameters = dict(last=final_state, fps=fps, width=width, height=height)
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
