from ls_prepost_mcp.checkpoint_context import checkpoint_expected_empty, reset_baseline, restart_source
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.sessions import Sessions


def test_restart_chooses_current_reset_baseline_without_losing_explicit_undo(tmp_path):
    rollback = str(tmp_path / "old.k")
    meta = dict(
        model_kind="keyword", last_checkpoint=rollback, **reset_baseline(tmp_path / "reset", rollback)
    )
    assert restart_source(meta) == str(tmp_path / "reset" / "initial.k")
    assert meta["last_checkpoint"] == rollback
    # Raw unsaved edits may change dirty and generation; saved reset still wins.
    meta.update(dirty=True, model_generation="changed-by-raw-program")
    assert restart_source(meta) == meta["reset_recovery_source"]
    meta["last_checkpoint"] = str(tmp_path / "newly-saved.k")
    assert restart_source(meta) == meta["last_checkpoint"]
    meta.update(staged_model="different-source.k", last_checkpoint=None)
    assert restart_source(meta) == "different-source.k"
    meta.update(model_kind="d3plot", staged_model="d3plot", last_checkpoint=rollback)
    assert restart_source(meta) == "d3plot"


def test_late_reset_retains_rollback_and_establishes_new_empty_restart_source(tmp_path, monkeypatch):
    import ls_prepost_mcp.sessions as module

    manager = Sessions(Settings(tmp_path))
    sid = "a" * 32
    rid = "b" * 32
    directory = manager.directory(sid) / "requests" / rid
    directory.mkdir(parents=True)
    rollback = tmp_path / "rollback.k"
    rollback.write_text("*KEYWORD\n*NODE\n1,0,0,0\n*END\n")
    (directory / "initial.k").write_text("*KEYWORD\n*END\n")
    manager.save(
        sid,
        dict(
            session_id=sid,
            process={},
            state="uncertain",
            dirty=False,
            model_kind="keyword",
            active_request=rid,
            last_checkpoint=str(rollback),
        ),
    )
    atomic_json(
        directory / "request.json",
        dict(job_id=rid, action="gui_new", job_directory=str(directory), parameters={}, native_commands=[]),
    )
    atomic_json(directory / "contract.json", dict(export=False, artifacts=[], was_uncertain=False))
    atomic_json(
        directory / "complete.json",
        dict(
            job_id=rid,
            ok=True,
            data=dict(
                model_directory=str(directory / "initial.k"), counts=dict(nodes=0, elements=0, states=1)
            ),
        ),
    )
    monkeypatch.setattr(module, "alive", lambda identity: True)
    result = Service(manager.settings).recover_gui_session(sid)
    assert result["state"] == "ready" and result["last_checkpoint"] == str(rollback)
    assert restart_source(result) == str(directory / "initial.k")
    assert checkpoint_expected_empty(directory / "initial.k", sid)


def test_reset_saves_zero_node_cards_before_attempting_new_model(tmp_path, monkeypatch):
    from contextlib import nullcontext

    meta = dict(state="ready", model_kind="keyword", dirty=True, last_checkpoint="old.k")
    seen = []

    class Manager:
        def read(self, sid):
            return dict(meta)

        def lock(self, sid):
            return nullcontext()

        def save(self, sid, value):
            meta.update(value)

        def dispatch(self, sid, action, params, **kw):
            seen.append(action)
            if action == "inspect_model":
                return dict(status="succeeded", data=dict(counts=dict(nodes=0, elements=0)))
            if action == "export_keyword":
                return dict(status="succeeded", artifacts=[dict(path=str(tmp_path / "material-only.k"))])
            assert meta["last_checkpoint"] == str(tmp_path / "material-only.k") and meta["dirty"] is False
            raise TimeoutError("simulated pending reset")

    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "_session_manager", Manager)
    import pytest

    with pytest.raises(TimeoutError):
        service.reset_gui_session("test")
    assert seen == ["inspect_model", "export_keyword", "gui_new"]
    assert meta["last_checkpoint"] == str(tmp_path / "material-only.k")


def test_explicit_spelling_of_trusted_checkpoint_still_auto_detects_empty(tmp_path, monkeypatch):
    from ls_prepost_mcp.checkpoint_context import save_checkpoint_context

    path = tmp_path / "checkpoint.k"
    path.write_text("*KEYWORD\n*END\n")
    save_checkpoint_context(path, "owner", dict(counts=dict(nodes=0, elements=0)), tmp_path)

    class Manager:
        def read(self, sid):
            return dict(last_checkpoint=str(path))

    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "_session_manager", Manager)
    calls = []

    def opened(*args, **kwargs):
        calls.append(kwargs)
        return dict(status="succeeded")

    monkeypatch.setattr(service, "open_in_gui_session", opened)
    service.restore_gui_checkpoint("owner", str(tmp_path) + "/./checkpoint.k")
    assert calls == [dict(discard=True, expected_empty=True)]
