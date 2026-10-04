"""Opt-in native physical-field frame sequence, explicit encoder and parameter replay."""

import argparse
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json, fingerprint
from ls_prepost_mcp.result_validity import load_physical_validity
from ls_prepost_mcp.service import Service


def accept(workspace, executable, source, states, bounds):
    source = Path(source).resolve()
    root = Path(workspace).resolve() / ("native-physical-movie-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    service = Service(Settings(root, Path(executable), allowed_roots=(source.parent,), timeout=180))
    family = service._result_family(str(source))
    original = [fingerprint(p) for p in family]
    physical = load_physical_validity(source, states, "solid")
    expected = {s:int(physical.mask[physical.state_rows[s]].sum()) for s in states}
    keep = int(physical.user_ids[physical.mask[-1]][0])
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session.json", session)
    checks = []

    def checked(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error") or result.get("restoration_error")
        checks.append(name)
        print(name, flush=True)
        return result

    def verify(movie, requested):
        assert [(f["state"], f["count"]) for f in movie["data"]["frames"]] == [(s,expected[s]) for s in requested]
        assert all(f["color_range"] == bounds for f in movie["data"]["frames"])
        video = movie["data"]["video"]
        assert video["encoded_by"] == "ffmpeg_libx264" and not video["native_movie_command"]
        assert video["decoded_frames"] == len(requested) and video["full_decode_passed"]
        assert movie["restoration"]["verified"] and movie["restoration"]["state"] == states[-1]
        restoration = service.read_job(Path(movie["restoration"]["job_directory"]).name)
        assert restoration["data"]["rendered_entity_count"] == expected[states[-1]] - 1

    try:
        service.show_gui_session(sid, maximize=True)
        checked("open", service.open_in_gui_session(sid, str(source), "d3plot"))
        service.start_session_recording(sid)
        checked("view", service.set_gui_display(sid, state=states[-1], view="isometric", center=True, zoom_scale=0.7, capture=False))
        checked("initial-field", service.render_gui_field(sid, "solid", "von_mises", states[-1], "source_units",
                                                          color_range=bounds, validity_policy="alive"))
        checked("manual-hide", service.set_gui_entity_visibility(sid, "solid", "hide", entity_ids=[keep]))
        movie = checked("movie", service.export_gui_field_animation(sid, states, bounds, fps=5, width=640, height=480))
        verify(movie, states)
        record = checked("recording", service.stop_session_recording(sid))
        assert record["managed_steps"] == 4
        template = checked("template", service.parameterize_workflow(record["workflow"],
            [dict(step_id="step4", path=["states"], parameter="movie_states")]))
        requested = states[1:]
        replay = checked("replay", service.run_workflow(template["artifacts"][0]["path"], dict(movie_states=requested), sid))
        verify(replay["data"]["steps"]["step4"], requested)
        assert [fingerprint(p) for p in family] == original
        atomic_json(root / "acceptance.json", dict(status="succeeded", checks=checks, states=states,
                    replay_states=requested, expected_counts=expected, source_unchanged=True,
                    scope="4.13.4 visible solid per-state physical PNGs + FFmpeg H264; fixed bounds, exact saved states, manual Blank restored, parameterized recorded replay. Other domains/builds and native Movie encoding not certified."))
    finally:
        atomic_json(root / "closed.json", service.close_gui_session(sid, save_checkpoint=False))
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--states", nargs="+", type=int, required=True)
    parser.add_argument("--bounds", nargs=2, type=float, required=True)
    args = parser.parse_args()
    print(accept(args.workspace, args.executable, args.source, args.states, args.bounds))
