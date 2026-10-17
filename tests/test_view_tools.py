import contextlib
import hashlib
import inspect
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.jobs import check_artifact
from ls_prepost_mcp.operation_registry import bind_alias, resolve_operation
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.sessions import Sessions

SESSION = "a" * 32


class FakeSessions:
    def __init__(self, directory, status="succeeded"):
        self.directory, self.status = directory, status
        self.meta = dict(model_generation="g1", model_kind="keyword", executable=dict(sha256="e" * 64))
        self.calls, self.journals = [], []

    @contextlib.contextmanager
    def lock(self, ident):
        assert ident == SESSION
        yield

    def read(self, ident):
        return dict(self.meta)

    def dispatch(self, ident, action, parameters, **options):
        self.calls.append((action, parameters, options))
        artifacts = []
        if self.status == "succeeded" and parameters["capture"]:
            pixels = np.zeros((40, 40, 3), dtype=np.uint8)
            pixels[5:15, 5:15] = 200
            path = self.directory / ("snapshot%d.png" % len(self.calls))
            Image.fromarray(pixels).save(path)
            artifacts.append(check_artifact(path, "png"))
        return dict(status=self.status, request_id="r%d" % len(self.calls), job_directory=str(self.directory),
                    data=dict(applied_commands=parameters["commands"]), artifacts=artifacts,
                    error=None if self.status == "succeeded" else dict(message="native refused"))

    def journal(self, ident, entry):
        self.journals.append(entry)


@pytest.fixture
def session_service(tmp_path):
    service = Service(Settings(tmp_path / "workspace"))
    sessions = FakeSessions(tmp_path)
    service._session_manager = lambda: sessions
    return service, sessions


def test_set_view_is_a_registered_target_tool_with_typed_signature(tmp_path):
    record = resolve_operation("set_view")
    assert (record.target, record.task_id, record.legacy_until) == ("set_view", "G01", None)
    service = Service(Settings(tmp_path))
    parameters = inspect.signature(service.set_view).parameters
    assert parameters["context"].default == "batch"
    assert inspect.signature(bind_alias(service.set_view, "set_view")) == inspect.signature(service.set_view)
    assert resolve_operation("set_gui_display").target == "set_view"


@pytest.mark.parametrize("arguments", [
    dict(context="session", view="front"),
    dict(context="session", session_id=SESSION, model="m.k", view="front"),
    dict(context="batch", session_id=SESSION, view="front"),
    dict(context="batch", model="m.k", view="front", capture=False),
    dict(context="gui", session_id=SESSION, view="front"),
    dict(context="session", session_id=SESSION),
    dict(context="session", session_id=SESSION, zoom_scale=0),
    dict(context="session", session_id=SESSION, pan_xy=[0, float("inf")]),
    dict(context="session", session_id=SESSION, rotation_xyz_degrees=[0, 400, 0]),
    dict(context="session", session_id=SESSION, view="front", save_preset_name="x"),
    dict(context="session", session_id=SESSION, view="front", projection="parallel", save_preset_name="../x"),
    dict(context="session", session_id=SESSION, restore_preset_name="x", view="front"),
    dict(context="session", session_id=SESSION, restore_preset_name="x", fit=True),
    dict(context="session", session_id=SESSION, view="front", execute=True),
    dict(context="batch", model="m.k", view="front", execute=1),
])
def test_invalid_requests_have_no_side_effects(tmp_path, monkeypatch, arguments):
    monkeypatch.setattr(Sessions, "start", lambda *a, **k: pytest.fail("A session must never be started"))
    service = Service(Settings(tmp_path))
    with pytest.raises(ValueError):
        service.set_view(**arguments)
    assert not list(tmp_path.iterdir())


def test_missing_session_is_rejected_without_starting_one(tmp_path, monkeypatch):
    monkeypatch.setattr(Sessions, "start", lambda *a, **k: pytest.fail("A session must never be started"))
    with pytest.raises(OSError):
        Service(Settings(tmp_path)).set_view("session", session_id=SESSION, view="front")


def test_session_view_dispatches_existing_gui_display_route(session_service):
    service, sessions = session_service
    result = service.set_view("session", session_id=SESSION, view="front", projection="parallel",
                              zoom_scale=2.0, fit=True)
    JobResult.model_validate(result)
    assert result["status"] == "succeeded" and result["stage"] == "execution"
    [(action, parameters, options)] = sessions.calls
    assert action == "gui_display"
    assert parameters == dict(commands=["front", "parallel", "ac", "zoom 2"], state=None, capture=True)
    assert options["artifacts"] == (("snapshot.png", "png"),)
    assert result["artifacts"][0]["verification"] == "verified"
    assert result["data"]["camera_state"] == "applied_unverified"
    assert result["data"]["native_camera_readback"] is False
    assert result["data"]["content_dependent"] is True
    assert sessions.journals[0]["action"] == "set_view"


def test_selector_centering_fails_closed_without_dispatch(session_service, tmp_path):
    service, sessions = session_service
    selector = dict(entity_type="part", predicate=dict(kind="parts", ids=[3]))
    result = service.set_view("session", session_id=SESSION, view="front", center_on=selector)
    JobResult.model_validate(result)
    assert result["status"] == "failed" and result["error"]["type"] == "unsupported"
    assert result["checks"] == [dict(name="selector_centering", status="missing", source_path=[])]
    assert sessions.calls == [] and sessions.journals == []
    assert not (tmp_path / "workspace").exists()
    with pytest.raises(ValueError):
        service.set_view("session", session_id=SESSION, center_on=dict(selector, configuration="deformed"))


def test_save_then_restore_replays_the_same_request(session_service):
    service, sessions = session_service
    saved = service.set_view("session", session_id=SESSION, view="front", projection="parallel",
                             zoom_scale=2.0, save_preset_name="front2x")
    assert saved["data"]["saved_preset"]["name"] == "front2x"
    service.set_view("session", session_id=SESSION, rotation_xyz_degrees=[0, 45, 0])
    restored = service.set_view("session", session_id=SESSION, restore_preset_name="front2x")
    assert restored["status"] == "succeeded"
    assert restored["data"]["restored_preset"]["kind"] == "request_preset"
    assert sessions.calls[2][1]["commands"] == sessions.calls[0][1]["commands"]
    with pytest.raises(ValueError, match="already exists"):
        service.set_view("session", session_id=SESSION, view="top", projection="parallel",
                         save_preset_name="FRONT2X")
    assert len(sessions.calls) == 3


def test_restore_rejects_a_changed_model_generation_before_dispatch(session_service):
    service, sessions = session_service
    service.set_view("session", session_id=SESSION, view="front", projection="parallel", save_preset_name="p")
    sessions.meta["model_generation"] = "g2"
    with pytest.raises(ValueError, match="different model"):
        service.set_view("session", session_id=SESSION, restore_preset_name="p")
    assert len(sessions.calls) == 1


def test_failed_native_request_saves_nothing(tmp_path):
    service = Service(Settings(tmp_path / "workspace"))
    sessions = FakeSessions(tmp_path, status="failed")
    service._session_manager = lambda: sessions
    result = service.set_view("session", session_id=SESSION, view="front", projection="parallel",
                              save_preset_name="p")
    JobResult.model_validate(result)
    assert result["status"] == "failed" and result["error"]["message"] == "native refused"
    assert not (tmp_path / "workspace" / "view_presets").exists()


def test_batch_prepares_a_reviewed_program_without_starting_native(tmp_path, monkeypatch):
    monkeypatch.setattr(Service, "execute_native_program", lambda *a, **k: pytest.fail("No native execution"))
    model = tmp_path / "model.k"
    model.write_text("*KEYWORD\n*END\n", encoding="ascii")
    service = Service(Settings(tmp_path))
    result = service.set_view(model=str(model), view="isometric", projection="perspective",
                              rotation_xyz_degrees=[0, 0, 30], save_preset_name="iso")
    JobResult.model_validate(result)
    assert result["status"] == "unverified" and result["stage"] == "preparation"
    execution = result["data"]["execution"]
    assert execution["native_started"] is False
    program = Path(service.read_job(execution["prepared_job_id"])["job_directory"]) / "program.cfile"
    lines = program.read_text(encoding="utf-8").splitlines()
    assert lines[:4] == ["isometric x", "perspective", "rotang 30", "rz"]
    assert lines[4].startswith('print png "view.png"')
    restored = service.set_view(model=str(model), restore_preset_name="iso")
    assert restored["data"]["commands"] == result["data"]["commands"]
    model.write_text("*KEYWORD\n*TITLE\nchanged\n*END\n", encoding="ascii")
    with pytest.raises(ValueError, match="different model"):
        service.set_view(model=str(model), restore_preset_name="iso")


class FakeBatch:
    """Stands in for execute_native_program; proves orchestration only, never native rendering."""

    def __init__(self, tmp_path, status="succeeded", png=True, input_sha256=None):
        self.directory, self.status, self.png, self.input_sha256 = tmp_path / "executed", status, png, input_sha256
        self.calls = []

    def __call__(self, service, prepared_job_id, expected_sha256, **options):
        self.calls.append((prepared_job_id, expected_sha256, options))
        self.directory.mkdir(exist_ok=True)
        artifacts = []
        if self.png:
            pixels = np.zeros((40, 40, 3), dtype=np.uint8)
            pixels[5:15, 5:15] = 200
            Image.fromarray(pixels).save(self.directory / "view.png")
            artifacts.append(check_artifact(self.directory / "view.png", "png"))
        source = service.settings.input_path(options["model"])
        sha = self.input_sha256 or hashlib.sha256(source.read_bytes()).hexdigest()
        return dict(job_id="x" * 32, status=self.status, artifacts=artifacts, inputs=[dict(sha256=sha)],
                    executable=dict(sha256=None), process=dict(pid=7, returncode=0, elapsed_seconds=1.5),
                    error=None if self.status == "succeeded" else dict(type="RuntimeError", message="native refused"))


@pytest.fixture
def batch_model(tmp_path, monkeypatch):
    monkeypatch.setattr(Sessions, "start", lambda *a, **k: pytest.fail("A session must never be started"))
    model = tmp_path / "model.k"
    model.write_text("*KEYWORD\n*END\n", encoding="ascii")
    return Service(Settings(tmp_path)), str(model)


def test_batch_execute_runs_the_prepared_program_headless(batch_model, monkeypatch, tmp_path):
    service, model = batch_model
    fake = FakeBatch(tmp_path)
    monkeypatch.setattr(Service, "execute_native_program", lambda self, *a, **k: fake(self, *a, **k))
    result = service.set_view(model=model, view="front", projection="parallel", zoom_scale=2.0, execute=True,
                              save_preset_name="front2x")
    JobResult.model_validate(result)
    assert result["status"] == "succeeded" and result["stage"] == "execution" and result["job_id"] == "x" * 32
    [(prepared_job_id, sha256, options)] = fake.calls
    execution = result["data"]["execution"]
    assert (prepared_job_id, sha256) == (execution["prepared_job_id"], execution["prepared_sha256"])
    assert options == dict(model=model, file_type="keyword", graphics=False, launch_mode="c")
    assert execution["native_started"] is True and execution["graphics"] is False
    assert result["artifacts"][0]["kind"] == "png" and result["artifacts"][0]["verification"] == "verified"
    assert result["data"]["camera_state"] == "applied_unverified"
    assert result["data"]["native_camera_readback"] is False
    assert result["data"]["saved_preset"]["name"] == "front2x"


@pytest.mark.parametrize(("options", "message"), [
    (dict(status="failed"), "native refused"),
    (dict(png=False), "no verified PNG"),
    (dict(input_sha256="0" * 64), "differs from the prepared model"),
])
def test_batch_execute_failure_is_reported_and_saves_nothing(batch_model, monkeypatch, tmp_path, options, message):
    service, model = batch_model
    fake = FakeBatch(tmp_path, **options)
    monkeypatch.setattr(Service, "execute_native_program", lambda self, *a, **k: fake(self, *a, **k))
    result = service.set_view(model=model, view="front", projection="parallel", execute=True,
                              save_preset_name="p")
    JobResult.model_validate(result)
    assert result["status"] == "failed" and result["stage"] == "execution"
    assert message in result["error"]["message"]
    assert result["artifacts"] == []
    assert not (tmp_path / "view_presets").exists()
