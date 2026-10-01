import copy
from contextlib import nullcontext
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


def fixture(tmp_path, monkeypatch):
    source = tmp_path / "model.dat"
    source.write_text("synthetic fixture")
    meta = dict(
        dirty=False,
        model_kind="keyword",
        last_checkpoint="previous.k",
        selection_buffers={"1": dict(entity_type="node", entity_ids=[1], model_signature="same-geometry")},
        managed_fringe={"status": "verified", "frames": {"1": "old-job"}},
        fringe_storage={"solid": [1]},
    )

    class Manager:
        def read(self, sid):
            return copy.deepcopy(meta)

        def save(self, sid, value):
            meta.update(value)

        def lock(self, sid):
            return nullcontext()

        def stage_input(self, sid, path, kind):
            return Path(path)

        def dispatch(self, *args, **kwargs):
            return dict(status="succeeded", data=dict(counts=dict(nodes=1)))

        def journal(self, *args):
            pass

    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "_session_manager", Manager)
    return service, meta, source


@pytest.mark.parametrize("kind", ["keyword", "d3plot"])
def test_reopening_a_model_invalidates_old_selection_identities(tmp_path, monkeypatch, kind):
    service, meta, source = fixture(tmp_path, monkeypatch)
    assert service.open_in_gui_session("s", str(source), kind)["status"] == "succeeded"
    assert meta["selection_buffers"] == {}
    assert meta["managed_fringe"] is None and meta["fringe_storage"] == {}
    assert meta["last_checkpoint"] == (str(source) if kind == "keyword" else None)


def test_new_model_invalidates_buffers_but_keeps_explicit_recovery_checkpoint(tmp_path, monkeypatch):
    service, meta, source = fixture(tmp_path, monkeypatch)
    assert service.reset_gui_session("s", save_checkpoint=False)["status"] == "succeeded"
    assert meta["selection_buffers"] == {} and meta["last_checkpoint"] == "previous.k"
    assert meta["managed_fringe"] is None and meta["fringe_storage"] == {}
