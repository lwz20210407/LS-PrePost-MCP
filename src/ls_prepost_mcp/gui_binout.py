"""Finite native Binout reads in the current GUI, independent of displayed model."""

from .core.native_log import native_errors, read_delta
from .jobs import atomic_json
from .model_context import LOAD_ERROR
from .native import commands as nc


def binout_executor(service, session_id):
    def execute(directory, manifest):
        manager = service._session_manager()
        with manager.lock(session_id):
            meta = service._visible_mesh_session(session_id, manager, allow_results=True)
            manifest.update(
                session_id=session_id, process=meta["process"], execution_mode="visible_gui_scl_binout"
            )
            before = manager.dispatch(session_id, "inspect_model", dict(include_display_scope=True))
            if before["status"] != "succeeded":
                raise ValueError("Cannot establish Binout GUI baseline")
            atomic_json(directory / "before.json", before["data"])
            log = manager.directory(session_id) / "lspost.msg"
            offset = log.stat().st_size if log.exists() else 0
            result = manager.dispatch(
                session_id,
                "inspect_model",
                dict(include_display_scope=True),
                native_commands=[nc.run_script(directory / "binout.scl", "scl")],
            )
            manifest["native_request"] = {k: v for k, v in result.items() if k != "data"}
            if result["status"] != "succeeded":
                raise RuntimeError("Native Binout request failed or did not complete")
            after = result["data"]
            atomic_json(directory / "after.json", after)
            for key in (
                "counts",
                "part_ids",
                "current_state",
                "model_directory",
                "part_visibility",
                "selection_count",
            ):
                if key not in before["data"] or key not in after or before["data"][key] != after[key]:
                    current = manager.read(session_id)
                    current.update(state="uncertain", dirty=True)
                    manager.save(session_id, current)
                    raise ValueError("Binout read changed or could not verify GUI " + key)
            if log.exists():
                text = read_delta(log, offset, existed=True)
                (directory / "native-binout.log").write_text(text, encoding="utf8")
                if native_errors(text) or any(LOAD_ERROR.search(line) for line in text.splitlines()):
                    raise ValueError("Native Binout log reports an error")
            manifest["gui_verification"] = dict(
                inventory_state_part_visibility_selection_count_preserved=True,
                scope="Inventory, active model path, current state, part flags and selection count; not full geometry/camera certification",
            )

    return execute
