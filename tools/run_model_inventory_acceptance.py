"""Opt-in native model inventory with sparse IDs after removing a test model."""

import argparse
import uuid
from pathlib import Path

from run_element_set_acceptance import fixture

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("mi-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    a = root / "first.k"
    b = root / "second.k"
    fixture(a)
    fixture(b)
    b.write_text(b.read_text().replace("Element set acceptance fixture", "Second inventory model"))
    original = {p: p.read_bytes() for p in (a, b)}
    s = Service(Settings(root, Path(executable), timeout=60))
    meta = s.start_gui_session()
    sid = meta["session_id"]
    atomic_json(root / "session.json", meta)
    s.show_gui_session(sid, maximize=True)
    cases = []
    print(root, flush=True)

    def inventory(name):
        result = s.inspect_gui_session(sid, include_models=True)
        atomic_json(root / (name + ".json"), result)
        cases.append(name)
        print(name, flush=True)
        return result["native_models"]

    try:
        first = inventory("initial")
        assert len(first["models"]) == 1
        initial_id = first["models"][0]["display_number"]
        initial_path = first["models"][0]["path"]
        for name, path in [("a", a), ("b", b)]:
            opened = s.open_in_gui_session(sid, str(path))
            atomic_json(root / (name + "-open.json"), opened)
            assert opened["status"] == "succeeded", opened.get("error")
        before = inventory("three-models")
        assert len(before["models"]) == 3
        current = before["active_row_index_candidate"]
        current_path = before["models"][current - 1]["path"]
        assert current is not None and current != initial_id
        # This command was recorded from Model Selection/Remove. Remove only the
        # initial empty model created by this test, not arbitrary user models.
        m = s._session_manager()
        with m.lock(sid):
            removed = m.dispatch(
                sid, "inspect_model", {}, native_commands=["model remove " + str(initial_id)]
            )
            atomic_json(root / "remove-initial.json", removed)
            assert removed["status"] == "succeeded"
        after = inventory("two-sparse-models")
        assert {r["path"] for r in after["models"]} == {r["path"] for r in before["models"]} - {initial_path}
        assert after["active_row_index_candidate"] in (1, 2)
        active_after_remove = after["active_row_index_candidate"]
        refreshed = next(r["row_index"] for r in after["models"] if r["path"] == current_path)
        with m.lock(sid):
            selected = m.dispatch(
                sid, "inspect_model", {}, native_commands=["model select " + str(refreshed)]
            )
            atomic_json(root / "reselect-current.json", selected)
            assert selected["status"] == "succeeded"
        restored = inventory("reselected-model")
        assert restored["active_row_index_candidate"] == refreshed
        # The same second row is selected with `model select 2`, but its
        # recorded Remove command is `model remove 3` after the initial hole.
        # These namespaces must not be collapsed into one inferred model ID.
        target = next(r for r in restored["models"] if r["path"] == current_path)
        assert target["display_number"] == 3 and target["row_index"] == 2
        with m.lock(sid):
            removed = m.dispatch(
                sid, "inspect_model", {},
                native_commands=["model remove " + str(target["display_number"])],
            )
            atomic_json(root / "remove-sparse-display-number.json", removed)
            assert removed["status"] == "succeeded"
        final = inventory("remaining-first-model")
        assert len(final["models"]) == 1
        assert final["models"][0]["path"] != current_path
        assert final["models"][0]["display_number"] == 2
        assert final["active_row_index_candidate"] == 1
        assert all(p.read_bytes() == raw for p, raw in original.items())
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                cases=cases,
                source_unchanged=True,
                model_counts=[1, 3, 2, 1],
                remaining_display_numbers=[r["display_number"] for r in after["models"]],
                active_before_remove=current,
                active_after_remove=active_after_remove,
                active_reselected=restored["active_row_index_candidate"],
                sparse_remove_display_number=target["display_number"],
                remaining_source=final["models"][0]["path"],
                scope="4.13.4 visible native Model Selection list inventory; recorded select uses current row position, while remove uses display number in this fixture. Unique source-path active candidate only, not a general mutation interface or genselect suffix.",
            ),
        )
    finally:
        atomic_json(root / "closed.json", s.close_gui_session(sid, save_checkpoint=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True)
    p.add_argument("--executable", required=True)
    accept(**vars(p.parse_args()))
