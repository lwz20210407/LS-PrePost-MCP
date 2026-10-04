import copy
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.gui_field_movie import encode_frames
from ls_prepost_mcp.service import Service


@pytest.mark.parametrize("changes", [dict(states=[2,1]), dict(states=[1,1]), dict(states=[True]),
                                     dict(color_range=None), dict(color_range=[0.,0.]),
                                     dict(width=641), dict(fps=0)])
def test_bad_field_movie_request_fails_before_native_contact(tmp_path, changes):
    args = dict(states=[1,2], color_range=[0.,1.], fps=5, width=640, height=480)
    args.update(changes)
    with pytest.raises(ValueError):
        Service(Settings(tmp_path)).export_gui_field_animation("absent", **args)
    assert not list(tmp_path.iterdir())


def test_encoder_failure_is_not_reported_as_native_video(tmp_path, monkeypatch):
    monkeypatch.setattr("ls_prepost_mcp.gui_field_movie.subprocess.run",
                        lambda *a, **kw: SimpleNamespace(returncode=1, stderr="codec unavailable"))
    with pytest.raises(ValueError, match="encoding failed"):
        encode_frames(tmp_path, 2, 5, 640, 480, dict(ffmpeg="ffmpeg", ffprobe="ffprobe"), 10)


def test_failed_frame_restores_original_state_flags_and_fringe(tmp_path, monkeypatch):
    from ls_prepost_mcp import gui_field_movie as module

    original = {("solid",10): False, ("solid",20): True}
    data = dict(counts=dict(nodes=2, elements=2, states=2), part_ids=[7], current_state=2,
                state_times=[0.,1.], part_visibility={"7":True}, selection_ids=[],
                digest_contract="native_registry_order_sha256_v1", digest_node_ids=[],
                mesh_digest={k:"a"*64 for k in ("node_ids","coordinates","connectivity","part_membership","unselected_coordinates")})
    definition = dict(domain="solid", field="von_mises", units="Pa", parts=[7], averaging="minmax",
                      validity_policy="alive", sampling=dict(kind="native_default", value="solid_default"))
    meta = dict(state="ready", model_kind="d3plot", process={}, managed_fringe=dict(
        status="verified", definition=definition, color_range=[0.,1.], frames={"2":"original-job"}))

    class Manager:
        def __init__(self):
            self.data = copy.deepcopy(data)
            self.flags = dict(original)
            self.entries = []

        def lock(self, sid):
            return nullcontext()

        def read(self, sid):
            return meta

        def dispatch(self, sid, action, parameters, native_commands=()):
            for command in native_commands:
                if command.startswith("state "):
                    self.data["current_state"] = int(command.split()[1])
                if command.startswith("unblank all"):
                    self.flags = {key:True for key in original}
                if command == "restore_exact_flags":
                    self.flags = dict(original)
            return dict(status="succeeded", data=copy.deepcopy(self.data), job_directory=str(tmp_path))

        def journal(self, sid, entry):
            self.entries.append(entry)

    manager = Manager()
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "_session_manager", lambda: manager)
    monkeypatch.setattr(service, "_visible_mesh_session", lambda *a, **kw: meta)
    monkeypatch.setattr(module, "movie_validators", lambda: dict(ffmpeg="encoder", ffprobe="probe"))
    monkeypatch.setattr(module, "flags", lambda *a: dict(manager.flags))
    monkeypatch.setattr(module, "transitions", lambda *a: ["restore_exact_flags"])
    monkeypatch.setattr(module, "wait_for_gui_state", lambda m,s,state,timeout,native_commands:
                        (m.dispatch(s,"inspect_model",{},native_commands), []))
    restored = []

    def render(*args, **kwargs):
        assert kwargs["_locked"] and not kwargs["_journal"]
        if args[4] == 1:
            raise ValueError("missing physical variable")
        assert manager.flags == original
        restored.append(args[4])
        return dict(status="succeeded", job_directory=str(tmp_path))

    monkeypatch.setattr(module, "render_field", render)
    monkeypatch.setattr(module, "encode_frames", lambda *a: pytest.fail("Failed frames must not be encoded"))
    result = service.export_gui_field_animation("s", [1,2], [0.,2.], 5, 640, 480)
    assert result["status"] == "failed" and "missing physical variable" in result["error"]["message"]
    assert result["restoration"]["verified"] and manager.data["current_state"] == 2
    assert manager.flags == original and restored == [2]
    assert len(manager.entries) == 1 and not result["artifacts"]
