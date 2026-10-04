import json
from contextlib import nullcontext

import pytest

from ls_prepost_mcp.checkpoint_context import checkpoint_expected_empty, context_path, save_checkpoint_context
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


@pytest.mark.parametrize("nodes,elements,expected", [(0, 0, True), (1, 0, False), (8, 1, False)])
def test_checkpoint_expectation_is_bound_to_exact_file_and_owner(tmp_path, nodes, elements, expected):
    path = tmp_path / "model.k"
    path.write_text("*KEYWORD\n*END\n")
    save_checkpoint_context(path, "owner", dict(counts=dict(nodes=nodes, elements=elements)), tmp_path)
    assert checkpoint_expected_empty(path, "owner") is expected
    with pytest.raises(ValueError, match="foreign"):
        checkpoint_expected_empty(path, "other")
    path.write_text("*KEYWORD\n*NODE\n1,0,0,0\n*END\n")
    with pytest.raises(ValueError, match="changed"):
        checkpoint_expected_empty(path, "owner")


def test_legacy_missing_counts_and_proof_do_not_guess_empty_from_text(tmp_path):
    path = tmp_path / "model.k"
    path.write_text("*KEYWORD\n*END\n")
    assert save_checkpoint_context(path, "owner", dict(counts={}), tmp_path) is None
    assert not context_path(path).exists()
    assert checkpoint_expected_empty(path, "owner") is False
    with pytest.raises(ValueError, match="owned session"):
        save_checkpoint_context(path, "owner", dict(counts=dict(nodes=0, elements=0)), tmp_path / "another")


@pytest.mark.parametrize(
    "bad", [dict(nodes=True, elements=0), dict(nodes=-1, elements=0), dict(nodes=0, elements=2)]
)
def test_bad_or_inconsistent_counts_cannot_authorize_empty_load(tmp_path, bad):
    path = tmp_path / "model.k"
    path.write_text("*KEYWORD\n*END\n")
    record = save_checkpoint_context(path, "owner", dict(counts=dict(nodes=0, elements=0)), tmp_path)
    record["counts"] = bad
    context_path(path).write_text(json.dumps(record))
    with pytest.raises(ValueError):
        checkpoint_expected_empty(path, "owner")


def test_restart_uses_empty_file_context_and_blocks_changed_file_before_launch(tmp_path, monkeypatch):
    path = tmp_path / "model.k"
    path.write_text("*KEYWORD\n*END\n")
    save_checkpoint_context(path, "old", dict(counts=dict(nodes=0, elements=0)), tmp_path)
    service = Service(Settings(tmp_path))
    old = dict(process_alive=False, model_kind="keyword", last_checkpoint=str(path))

    class Manager:
        def lock(self, sid):
            return nullcontext()

        def read(self, sid):
            return dict(old)

        def save(self, sid, data):
            old.update(data)

    calls = []
    monkeypatch.setattr(service, "_session_manager", Manager)
    monkeypatch.setattr(service, "start_gui_session", lambda: calls.append("start") or dict(session_id="new"))
    monkeypatch.setattr(service, "show_gui_session", lambda *a, **kw: None)

    def opened(sid, source, kind, **kwargs):
        assert kwargs == {"expected_empty": True}
        calls.append("open")
        return dict(status="succeeded")

    monkeypatch.setattr(service, "open_in_gui_session", opened)
    assert service.restart_gui_session("old")["status"] == "succeeded"
    assert calls == ["start", "open"]
    old.pop("restarted_as")
    path.write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        service.restart_gui_session("old")
    assert calls == ["start", "open"]
