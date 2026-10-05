import copy
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from ls_prepost_mcp import model_replacement
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


@pytest.mark.parametrize("failure_phase", ["load", "remove", "survivor_export"])
def test_failed_replacement_keeps_checkpoint_and_reports_removal_uncertainty(
    tmp_path, monkeypatch, failure_phase
):
    original = tmp_path / "original.k"
    original.write_text("*KEYWORD\n*NODE\n301,1,2,3\n*END\n")
    incoming = tmp_path / "incoming.k"
    incoming.write_text("*KEYWORD\n*END\n")
    session = tmp_path / "session"
    session.mkdir()
    meta = dict(
        state="ready",
        process=dict(pid=123),
        model_kind="keyword",
        staged_model=str(original),
        source=str(original),
        last_checkpoint=str(original),
        dirty=True,
    )
    rows = [dict(row_index=1, display_number=1, display_label="1-Original", path=str(original))]
    calls = []

    class Manager:
        def read(self, sid):
            return copy.deepcopy(meta)

        def save(self, sid, data):
            meta.update(copy.deepcopy(data))

        def lock(self, sid):
            return nullcontext()

        def directory(self, sid):
            return session

        def stage_input(self, sid, path, kind):
            return incoming

        def journal(self, *args):
            pass

        def dispatch(self, sid, action, parameters, **kwargs):
            calls.append((action, kwargs))
            if kwargs.get("model"):
                if failure_phase == "load":
                    return dict(status="failed", error=dict(message="Native input rejected"), data=None)
                rows.append(
                    dict(row_index=2, display_number=2, display_label="2-Incoming", path=str(incoming))
                )
                return dict(
                    status="succeeded",
                    data=dict(model_directory=str(incoming), counts=dict(nodes=0, elements=0, states=1)),
                )
            native = dict(model_directory=str(original), counts=dict(nodes=1, elements=0, states=1))
            if kwargs.get("export"):
                checkpoint = session / "checkpoint.k"
                checkpoint.write_bytes(original.read_bytes())
                return dict(status="succeeded", data=native, artifacts=[dict(path=str(checkpoint))])
            return dict(status="succeeded", data=native)

    service = Service(Settings(tmp_path))
    manager = Manager()
    monkeypatch.setattr(service, "_session_manager", lambda: manager)
    monkeypatch.setattr(model_replacement, "WindowsCommandTransport", lambda pid: SimpleNamespace())
    monkeypatch.setattr(
        model_replacement, "inspect_models", lambda transport, **kwargs: dict(models=copy.deepcopy(rows))
    )

    def forbidden_unload(*args, **kwargs):
        if failure_phase == "survivor_export":
            return dict(
                status="failed",
                unload_submitted=True,
                model_removed=True,
                error=dict(message="Post-removal export failed"),
            )
        if failure_phase == "remove":
            raise TimeoutError("Native removal outcome unknown")
        raise AssertionError("No unload may run after failed input")

    monkeypatch.setattr(model_replacement, "unload", forbidden_unload)
    result = service.replace_gui_model("s", str(incoming))
    assert result["status"] == "failed"
    assert (
        result["old_model_unloaded"]
        is {"load": False, "remove": None, "survivor_export": True}[failure_phase]
    )
    assert meta["state"] == "uncertain" and meta["dirty"]
    assert result["old_checkpoint"] == str(session / "checkpoint.k")
    assert (session / "checkpoint.k").read_bytes() == original.read_bytes()
    assert [phase["name"] for phase in result["phases"]] == ["save-old", "load-replacement"] + (
        ["unload-old-model"] if failure_phase == "survivor_export" else []
    )
    assert len(calls) == 3


@pytest.mark.parametrize(
    "changes",
    [
        dict(state="uncertain"),
        dict(state="busy"),
        dict(recording={"id": "r"}),
        dict(active_request="pending"),
    ],
)
def test_replacement_refuses_unresolved_or_recording_state_before_native_io(tmp_path, monkeypatch, changes):
    meta = dict(state="ready", active_request=None, recording=None, **{})
    meta.update(changes)
    manager = SimpleNamespace(lock=lambda sid: nullcontext(), read=lambda sid: meta)
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "_session_manager", lambda: manager)
    with pytest.raises(ValueError, match="ready session"):
        service.replace_gui_model("s", "not-opened.k")


@pytest.mark.parametrize("kind,value", [("d3plot", True), ("keyword", "true"), ("keyword", 1)])
def test_expected_empty_is_explicit_keyword_boolean_before_session_access(tmp_path, kind, value):
    service = Service(Settings(tmp_path))
    with pytest.raises(ValueError, match="expected_empty"):
        service.replace_gui_model("missing", "none.k", kind, expected_empty=value)
