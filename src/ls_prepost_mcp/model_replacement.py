"""Explicit same-process replacement using a verified empty native staging model."""

import uuid
from pathlib import Path

from .jobs import atomic_json
from .resident_models import (
    list_identities,
    matching_resident_row,
    remember_model,
    unload,
    verify_context,
)
from .windows_model_list import inspect_models
from .windows_transport import WindowsCommandTransport


def new_context(source, staged, kind):
    return dict(
        source=source,
        staged_model=str(staged),
        model_kind=kind,
        last_checkpoint=str(staged) if kind == "keyword" else None,
        reset_recovery_source=None,
        reset_rollback_checkpoint=None,
        last_verified_source=None,
        last_list_source=None,
        native_export_aliases=[],
    )


def replace(service, session_id, path, file_type, expected_empty):
    if type(expected_empty) is not bool or expected_empty and file_type != "keyword":
        raise ValueError("expected_empty applies only to keyword replacements")
    manager = service._session_manager()
    with manager.lock(session_id):
        meta = manager.read(session_id)
        if meta["state"] != "ready" or meta.get("active_request") or meta.get("recording"):
            raise ValueError("Replacement requires a ready session without pending requests or recording")
        if not meta.get("staged_model"):
            raise ValueError("Open a managed model before requesting replacement")
        staged = manager.stage_input(session_id, path, file_type)
        source = str(service.settings.input_path(path))
        audit = manager.directory(session_id) / "model-operations" / uuid.uuid4().hex
        audit.mkdir(parents=True)
        transport = WindowsCommandTransport(meta["process"]["pid"])
        before = inspect_models(transport, close_panel=True)
        current = matching_resident_row(before["models"], meta, session_id)
        baseline = manager.dispatch(session_id, "inspect_model", {})
        if baseline["status"] != "succeeded":
            return baseline
        try:
            baseline_context = verify_context(meta, baseline["data"], session_id)
        except ValueError:
            meta.update(state="uncertain", dirty=True)
            manager.save(session_id, meta)
            raise
        old_source = meta["staged_model"]
        phases = []
        result = dict(
            status="failed",
            session_id=session_id,
            job_directory=str(audit),
            phases=phases,
            old_source=old_source,
            replacement_source=str(staged),
            old_model_unloaded=False,
        )
        atomic_json(audit / "before.json", dict(native_models=before, active_context=meta, baseline=baseline))

        def checked(name, operation):
            atomic_json(audit / (name + ".json"), operation)
            phases.append(
                dict(name=name, status=operation.get("status"), evidence=str(audit / (name + ".json")))
            )
            if operation.get("status") != "succeeded":
                raise RuntimeError("Replacement phase failed: " + name)
            return operation

        try:
            # Preserve current memory even if the managed dirty flag cannot
            # see a user's manual edit. Do not unload it before a verified load.
            if meta["model_kind"] == "keyword":
                saved = checked(
                    "save-old",
                    manager.dispatch(
                        session_id, "export_keyword", {}, artifacts=(("model.k", "keyword"),), export=True
                    ),
                )
                meta = manager.read(session_id)
                meta.update(last_checkpoint=saved["artifacts"][0]["path"], dirty=False)
            meta.update(
                last_list_source=current["path"], last_verified_source=baseline_context["expected_source"]
            )
            remember_model(meta)
            manager.save(session_id, meta)
            result["old_checkpoint"] = meta.get("last_checkpoint")
            anchor = None
            # cemptymodel leaves an existing keyword context unchanged on this
            # build. Leave result mode before either keyword or result loads:
            # direct result-to-result loading reproduced a native process exit.
            if meta["model_kind"] == "d3plot":
                empty = checked(
                    "create-empty-staging-model",
                    manager.dispatch(
                        session_id,
                        "inspect_model",
                        {},
                        native_commands=["cemptymodel"],
                        artifacts=(("model.k", "keyword"),),
                        export=True,
                    ),
                )
                counts = empty.get("data", {}).get("counts", {})
                if counts.get("nodes") != 0 or counts.get("elements") != 0 or counts.get("states", 2) > 1:
                    raise ValueError("Native staging model is not empty keyword context")
                anchor = Path(empty["artifacts"][0]["path"])
            result.update(
                temporary_model_created=anchor is not None,
                temporary_model_source=str(anchor) if anchor is not None else None,
            )
            opened = checked(
                "load-replacement",
                manager.dispatch(
                    session_id,
                    "inspect_model",
                    {},
                    model=staged,
                    file_type=file_type,
                    expected_empty=expected_empty,
                ),
            )
            # The empty model enters the native list when the replacement is
            # opened. Its saved absolute file identifies only this transaction.
            meta = manager.read(session_id)
            if anchor is not None:
                anchor_context = new_context(str(anchor), anchor, "keyword")
                meta.update(anchor_context)
                remember_model(meta)
            target = new_context(source, staged, file_type)
            meta.update(target)
            remember_model(meta)
            meta.update(
                dirty=False,
                model_generation=uuid.uuid4().hex,
                selection_buffers={},
                entity_visibility_last=None,
                managed_fringe=None,
                fringe_storage={},
            )
            after = inspect_models(transport, close_panel=True)
            atomic_json(audit / "after-load.json", after)
            target_row = matching_resident_row(after["models"], target, session_id)
            added_rows = {target_row["row_index"]}
            if anchor is not None:
                anchor_row = matching_resident_row(after["models"], anchor_context, session_id)
                added_rows.add(anchor_row["row_index"])
            remaining = [r for r in after["models"] if r["row_index"] not in added_rows]
            if list_identities(remaining, meta, session_id) != list_identities(
                before["models"], meta, session_id
            ):
                raise ValueError("Replacement load changed existing native model entries")
            manager.save(session_id, meta)
            # A timeout after sending remove has an unknown outcome, not False.
            result["old_model_unloaded"] = None
            removed = unload(service, session_id, old_source, str(staged), _manager=manager)
            result["old_model_unloaded"] = (
                True
                if removed.get("status") == "succeeded"
                else None
                if removed.get("unload_submitted")
                else False
            )
            checked("unload-old-model", removed)
            result["old_checkpoint"] = removed.get("removed_checkpoint")
            if anchor is not None:
                checked(
                    "unload-staging-model",
                    unload(service, session_id, str(anchor), str(staged), _manager=manager),
                )
            final = inspect_models(transport, close_panel=True)
            meta = manager.read(session_id)
            target_row = matching_resident_row(final["models"], meta, session_id)
            unaffected = [r for r in final["models"] if r["row_index"] != target_row["row_index"]]
            expected = [r for r in before["models"] if r["row_index"] != current["row_index"]]
            if list_identities(unaffected, meta, session_id) != list_identities(expected, meta, session_id):
                raise ValueError("Replacement did not preserve other resident models")
            result.update(
                status="succeeded",
                data=removed["data"],
                native_models=final,
                model_context=removed.get("model_context"),
                loaded_model_context=opened.get("model_context"),
                replacement_checkpoint=meta.get("last_checkpoint"),
                temporary_model_created=anchor is not None,
                temporary_model_removed=True,
                replacement_scope="Same owned process, explicit new-model load then old/temporary unload. Original files retained; known keyword memory checkpointed. No association, arbitrary scene restoration or multi-model recording certification.",
            )
        except Exception as exc:
            meta = manager.read(session_id)
            meta.update(state="uncertain", dirty=True)
            manager.save(session_id, meta)
            result.update(
                error=dict(type=type(exc).__name__, message=str(exc)),
                recovery_note="Do not replay replacement. Inspect saved phases/checkpoints and old_model_unloaded (null means unknown). Old removal is submitted only after the new load is verified; temporary cleanup may still be incomplete.",
            )
        atomic_json(audit / "replacement.json", result)
        manager.journal(
            session_id,
            dict(
                action="replace_gui_model",
                parameters=dict(path=path, file_type=file_type, expected_empty=expected_empty),
                result=result,
            ),
        )
        return result
