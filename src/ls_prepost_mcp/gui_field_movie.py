"""Per-state native field rendering with explicit FFmpeg PNG-sequence encoding."""

import math
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from .gui_controls import wait_for_gui_state
from .gui_fringe import field_range, render_field
from .gui_mesh import verify_mesh_digest
from .gui_selection import part_visibility
from .gui_visibility import CODES, flags, transitions
from .jobs import atomic_json, check_artifact, now
from .media_validation import movie_validators, validate_mp4
from .post_backend import ids


def validate_request(states, color_range, fps, width, height):
    ids(states, "states", 1800)
    if states != sorted(states):
        raise ValueError("Movie states must be strictly increasing")
    field_range([0], color_range)
    if color_range is None:
        raise ValueError("Per-state field movies require explicit fixed color_range")
    for name, value, low, high in (("fps", fps, 1, 60), ("width", width, 64, 3840), ("height", height, 64, 2160)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError(name + " is outside the supported integer range")
    if width % 2 or height % 2 or len(states) * width * height > 600_000_000:
        raise ValueError("Require even dimensions and at most600 million pixel-frames")


def encode_frames(directory, count, fps, width, height, validators, timeout):
    output = directory / "animation.mp4"
    command = [validators["ffmpeg"], "-v", "error", "-xerror", "-nostdin", "-y",
               "-framerate", str(fps), "-start_number", "0", "-i", "frame-%06d.png",
               "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=white",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps), "-frames:v", str(count), str(output)]
    result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=timeout)
    atomic_json(directory / "encoder.json", dict(command=command, returncode=result.returncode, stderr=result.stderr))
    if result.returncode or result.stderr.strip():
        raise ValueError("FFmpeg image-sequence encoding failed: " + result.stderr[:1000])
    video = validate_mp4(output, width, height, fps, count, validators, timeout)
    video.update(encoded_by="ffmpeg_libx264", rendering="native_lsprepost_png_per_state",
                 native_movie_command=False, scaling="aspect-preserving resize and white letterbox")
    return output, video


def export_field_movie(service, sid, states, color_range, fps, width, height):
    validate_request(states, color_range, fps, width, height)
    states, color_range = list(states), list(color_range)
    validators = movie_validators()
    manager = service._session_manager()
    parameters = dict(states=states, color_range=color_range, fps=fps, width=width, height=height)
    with manager.lock(sid):
        meta = service._visible_mesh_session(sid, manager, allow_results=True)
        managed = meta.get("managed_fringe")
        if meta["model_kind"] != "d3plot" or not managed or managed.get("status") != "verified":
            raise ValueError("Render a verified native field before exporting a per-state field movie")
        definition = managed["definition"]
        domain = definition["domain"]
        if domain not in ("solid", "shell") or definition.get("validity_policy") != "alive":
            raise ValueError("Per-state field movies require a verified physical solid/shell fringe")
        baseline = manager.dispatch(sid, "gui_mesh_digest", {}, native_commands=["anim stop"])
        if baseline["status"] != "succeeded":
            return baseline
        before = baseline["data"]
        original = before["current_state"]
        if type(original) is not int or str(original) not in managed.get("frames", {}):
            raise ValueError("Render the current state first so its original fringe can be restored")
        if managed.get("color_range") is None:
            raise ValueError("Original fringe has no verified color bounds")
        field_range([0], managed["color_range"])
        visible_parts = part_visibility(before)
        if ({int(pid) for pid, visible in visible_parts.items() if visible} != set(definition["parts"])
                or before.get("selection_ids")):
            raise ValueError("Fringe part/selection scope changed; render the field again")
        if max(states) > before["counts"]["states"] or any(not math.isfinite(before["state_times"][s-1]) for s in states):
            raise ValueError("Requested movie states exceed the native timeline")
        sampling = definition["sampling"]
        point = str(sampling["value"]) if sampling["kind"] == "native_integration_point" else (
            sampling["value"] if sampling["kind"] == "native_shell_layer" else "mid")
        directory, manifest = service.jobs.create("export_gui_field_animation", dict(session_id=sid, **parameters))
        manifest.update(status="running", started_at=now(), job_directory=str(directory), backend="lsprepost",
                        execution_mode="visible_gui_native_png_ffmpeg_movie", session_id=sid, process=meta["process"])
        reveal = ["+m " + pid for pid, active in visible_parts.items() if not active]
        restore_parts = ["-m " + pid for pid, active in visible_parts.items() if not active]
        old_flags, frames = None, []

        def checked(result):
            if result["status"] != "succeeded":
                raise ValueError("Native field movie step failed: " + str(result.get("error")))
            return result

        def render(state, bounds):
            return checked(render_field(service, sid, domain, definition["field"], state, definition["units"],
                point, definition["parts"], bounds, definition["averaging"], "alive", _locked=True, _journal=False))

        try:
            readback = checked(manager.dispatch(sid, "gui_mesh_digest", dict(visibility_readback=True), native_commands=reveal))
            old_flags = flags(readback["data"], readback["job_directory"])
            checked(manager.dispatch(sid, "inspect_model", {}, native_commands=restore_parts))
            image_size = None
            for index, state in enumerate(states):
                # This explicitly named workflow renders all alive entities in
                # selected parts, not the current static Blank subset. Reset on
                # every frame so late-state deletion never leaks to earlier frames.
                ready, _ = wait_for_gui_state(manager, sid, state, service.settings.timeout,
                    native_commands=["anim stop", "state %d" % state, "unblank all %d" % CODES[domain], "genselect clear"])
                checked(ready)
                rendered = render(state, color_range)
                png = Path(rendered["job_directory"]) / "fringe.png"
                with Image.open(png) as picture:
                    if image_size is not None and picture.size != image_size:
                        raise ValueError("Native viewport dimensions changed during the sequence")
                    image_size = picture.size
                    if len(states) * image_size[0] * image_size[1] > 600_000_000:
                        raise ValueError("Native PNG sequence exceeds600 million source pixel-frames")
                frame = directory / ("frame-%06d.png" % index)
                shutil.copyfile(png, frame)
                frames.append(dict(frame=index, state=state, time=before["state_times"][state-1],
                                   job_directory=rendered["job_directory"], image=check_artifact(frame, "png"),
                                   count=rendered["data"]["rendered_entity_count"],
                                   physical_deleted_count=rendered["data"]["validity"]["states"][0]["domain_deleted_count"],
                                   mask_backend=rendered["data"]["validity"]["backend"],
                                   color_range=rendered["data"]["color_range"]))
                atomic_json(directory / "frames.json", frames)
            movie, video = encode_frames(directory, len(states), fps, width, height, validators, service.settings.timeout)
            manifest.update(status="succeeded", data=dict(video=video, frames=frames, field=definition,
                color_range=color_range, scope="All physically present entities in selected parts; current manual Blank ignored for frames and restored afterwards",
                playback="Uniform FPS per saved state; physical time values retained separately, not time-resampled",
                title_policy="Native model/result names preserved"), artifacts=[check_artifact(movie, "validated_mp4_from_native_pngs")])
        except Exception as exc:
            manifest.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
        finally:
            try:
                checked(wait_for_gui_state(manager, sid, original, service.settings.timeout,
                    native_commands=["anim stop", "state %d" % original])[0])
                if old_flags is not None:
                    visible = checked(manager.dispatch(sid, "gui_mesh_digest", dict(visibility_readback=True), native_commands=reveal))
                    current_flags = flags(visible["data"], visible["job_directory"])
                    restored = checked(manager.dispatch(sid, "gui_mesh_digest", dict(visibility_readback=True),
                        native_commands=transitions(domain, current_flags, old_flags)))
                    if flags(restored["data"], restored["job_directory"]) != old_flags:
                        raise ValueError("Original native Blank flags could not be restored")
                checked(manager.dispatch(sid, "inspect_model", {}, native_commands=restore_parts + ["genselect clear"]))
                restoration = render(original, managed["color_range"])
                after = checked(manager.dispatch(sid, "gui_mesh_digest", {}))["data"]
                verify_mesh_digest(before, after)
                if after["current_state"] != original or part_visibility(after) != visible_parts:
                    raise ValueError("Original scene state or parts changed during export")
                manifest["restoration"] = dict(state=original, verified=True, job_directory=restoration["job_directory"])
            except Exception as exc:
                manifest.update(status="failed", restoration_error=str(exc), artifacts=[])
                current = manager.read(sid)
                current.update(state="uncertain", last_error=str(exc))
                manager.save(sid, current)
        manifest["finished_at"] = now()
        atomic_json(directory / "job.json", manifest)
        manager.journal(sid, dict(action="export_gui_field_animation", parameters=parameters, result=manifest))
        return manifest
