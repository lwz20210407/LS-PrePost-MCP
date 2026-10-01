import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.media_validation import parse_movie_log, validate_mp4
from ls_prepost_mcp.service import Service

LOG = (
    "Creating Movie...\nwriting state #0, frame #1\nwriting state #1, frame #2\nFinished Creating Movie...\n"
)


def test_native_movie_requires_exact_ordered_state_frame_evidence():
    assert parse_movie_log(LOG, [1, 2])["frame_count"] == 2
    for text, states in [
        (LOG, [2, 3]),
        (LOG, [1, 2, 3]),
        (LOG + LOG, [1, 2]),
        (LOG.replace("Finished Creating Movie...", ""), [1, 2]),
        (LOG.replace("state #1", "state #0"), [1, 2]),
        (LOG.replace("frame #2", "frame #1"), [1, 2]),
    ]:
        with pytest.raises(ValueError, match="evidence"):
            parse_movie_log(text, states)


@pytest.mark.parametrize(
    "changed",
    [
        dict(nb_read_frames="1"),
        dict(width=642),
        dict(r_frame_rate="10/1"),
        dict(codec_name="mpeg4"),
        dict(duration="nan"),
        dict(duration="1"),
    ],
)
def test_video_metadata_mismatch_is_not_a_valid_artifact(tmp_path, monkeypatch, changed):
    path = tmp_path / "native.mp4"
    path.write_bytes(b"fake for mocked probe")
    stream = dict(
        codec_name="h264", width=640, height=480, r_frame_rate="12/1", nb_read_frames="2", duration="0.166667"
    )
    stream.update(changed)
    monkeypatch.setattr(
        "ls_prepost_mcp.media_validation.subprocess.run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stderr="", stdout=json.dumps(dict(streams=[stream]))),
    )
    with pytest.raises(ValueError):
        validate_mp4(path, 640, 480, 12, 2, dict(ffprobe="probe", ffmpeg="decode"), 10)


def test_valid_metadata_still_requires_full_decoder_success(tmp_path, monkeypatch):
    path = tmp_path / "native.mp4"
    path.write_bytes(b"fake for mocked decoder")
    calls = []

    def run(command, **options):
        calls.append(command)
        if command[0] == "probe":
            return SimpleNamespace(
                returncode=0,
                stderr="",
                stdout=json.dumps(
                    dict(
                        streams=[
                            dict(
                                codec_name="h264",
                                width=640,
                                height=480,
                                r_frame_rate="12/1",
                                nb_read_frames="2",
                                duration="0.166667",
                            )
                        ]
                    )
                ),
            )
        return SimpleNamespace(returncode=1, stderr="corrupt frame", stdout="")

    monkeypatch.setattr("ls_prepost_mcp.media_validation.subprocess.run", run)
    with pytest.raises(ValueError, match="decoding"):
        validate_mp4(path, 640, 480, 12, 2, dict(ffprobe="probe", ffmpeg="decode"), 10)
    assert calls[1][-3:] == ["-f", "null", "-"]


@pytest.mark.parametrize(
    "params", [dict(last=True), dict(fps=True), dict(width=641), dict(height=63), dict(last=1801)]
)
def test_movie_bad_parameters_fail_before_native_or_job_access(tmp_path, params):
    with pytest.raises(ValueError):
        Service(Settings(tmp_path)).export_gui_animation("missing", **params)
    assert not list(tmp_path.iterdir())


def test_movie_validator_dependency_is_required_before_native_access(tmp_path, monkeypatch):
    monkeypatch.setattr("ls_prepost_mcp.media_validation.shutil.which", lambda _: None)
    with pytest.raises(ValueError, match="ffprobe"):
        Service(Settings(tmp_path)).export_gui_animation("missing")
    assert not list(tmp_path.iterdir())


def test_failed_state_restoration_never_publishes_movie_as_success(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))
    inventory = dict(
        counts=dict(nodes=1, elements=1, states=2), part_ids=[1], current_state=2, state_times=[0, 1]
    )
    manager = SimpleNamespace(
        lock=lambda _: nullcontext(), directory=lambda _: tmp_path, journal=lambda *a: None
    )

    def dispatch(sid, action, parameters, **options):
        if options.get("native_commands"):
            (tmp_path / "lspost.msg").write_text(LOG)
        return dict(status="succeeded", data=inventory.copy())

    manager.dispatch = dispatch
    monkeypatch.setattr(service, "_session_manager", lambda: manager)
    monkeypatch.setattr(
        service, "_visible_mesh_session", lambda *a, **kw: dict(model_kind="d3plot", process={})
    )
    monkeypatch.setattr("ls_prepost_mcp.gui_media.movie_validators", lambda: {})
    monkeypatch.setattr("ls_prepost_mcp.gui_media.validate_mp4", lambda *a: {})

    def restore(manager, sid, state, timeout, **kw):
        return dict(status="succeeded" if state == 1 else "failed", data=inventory.copy()), []

    monkeypatch.setattr("ls_prepost_mcp.gui_media.wait_for_gui_state", restore)
    result = service.export_gui_animation("s", last=2)
    assert result["status"] == "failed" and not result["artifacts"]
    assert "restoration_error" in result
