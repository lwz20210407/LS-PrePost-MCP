import copy
from contextlib import nullcontext

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


def fixture_service(tmp_path, monkeypatch, dirty):
    checkpoint = tmp_path / "saved-before.k"
    checkpoint.write_text("*KEYWORD\n*END\n")
    meta = dict(
        state="ready",
        process_alive=True,
        model_kind="keyword",
        bridge_protocol=3,
        last_checkpoint=str(checkpoint),
        dirty=dirty,
    )
    mesh = dict(
        nodes=[[1, 0, 0, 0], [2, 1, 0, 0], [3, 0, 1, 0]],
        elements=[dict(type="shell", id=10, nodes=[1, 2, 3, 3])],
        part_ids=[1],
        part_elements={"1": [10]},
        selection_ids=[],
        counts={"nodes": 3, "elements": 1},
    )
    calls = []

    class Manager:
        def lock(self, sid):
            return nullcontext()

        def read(self, sid):
            return copy.deepcopy(meta)

        def save(self, sid, value):
            meta.update(value)

        def journal(self, sid, value):
            pass

        def dispatch(self, sid, action, params, **options):
            calls.append(options)
            directory = tmp_path / ("operation-" + str(len(calls)))
            directory.mkdir()
            artifacts = []
            if options.get("export"):
                path = directory / "model.k"
                path.write_text("*KEYWORD\n*END\n")
                artifacts.append(dict(path=str(path), kind="keyword"))
            snapshot = copy.deepcopy(mesh)
            if options.get("native_commands"):
                snapshot["selection_ids"] = [1]
            return dict(status="succeeded", job_directory=str(directory), artifacts=artifacts, data=snapshot)

    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "_session_manager", Manager)
    return service, meta, calls, checkpoint


@pytest.mark.parametrize("dirty", [False, True])
def test_selection_does_not_export_or_clear_existing_dirty_state(tmp_path, monkeypatch, dirty):
    service, meta, calls, checkpoint = fixture_service(tmp_path, monkeypatch, dirty)
    result = service.select_gui_entities("session", "node", [1])
    assert result["status"] == "succeeded", result
    assert result["transaction_kind"] == "selection" and not result["checkpoint_created"]
    assert all(call["export"] is False and call["artifacts"] == () for call in calls)
    assert meta["last_checkpoint"] == str(checkpoint) and meta["dirty"] is dirty
    assert not list(tmp_path.glob("operation-*/model.k"))


def test_inspection_with_failed_quality_is_nonmutating_and_keeps_checkpoint(tmp_path, monkeypatch):
    service, meta, calls, checkpoint = fixture_service(tmp_path, monkeypatch, True)
    result = service._gui_mesh_edit(
        "session", "check", {}, [], lambda a, b: dict(passed_checks=False), transaction_kind="inspection"
    )
    assert result["status"] == "succeeded" and not result["verification"]["passed_checks"]
    assert not any(call["export"] for call in calls)
    assert meta["last_checkpoint"] == str(checkpoint) and meta["dirty"] is True


def test_edit_still_creates_pre_and_post_checkpoints(tmp_path, monkeypatch):
    service, meta, calls, checkpoint = fixture_service(tmp_path, monkeypatch, True)
    result = service._gui_mesh_edit("session", "edit", {}, [], lambda a, b: dict(verified=True))
    assert result["status"] == "succeeded" and result["checkpoint_created"]
    assert all(call["export"] is True for call in calls)
    assert len(list(tmp_path.glob("operation-*/model.k"))) == 2
    assert meta["last_checkpoint"] != str(checkpoint) and meta["dirty"] is False


def test_inspection_verification_failure_marks_uncertainty_without_losing_saved_baseline(
    tmp_path, monkeypatch
):
    service, meta, calls, checkpoint = fixture_service(tmp_path, monkeypatch, False)

    def fail(before, after):
        raise ValueError("Unexpected model change")

    result = service._gui_mesh_edit("session", "check", {}, [], fail, transaction_kind="inspection")
    assert result["status"] == "failed" and meta["state"] == "uncertain" and meta["dirty"]
    assert meta["last_checkpoint"] == str(checkpoint)
    assert not any(call["export"] for call in calls)
