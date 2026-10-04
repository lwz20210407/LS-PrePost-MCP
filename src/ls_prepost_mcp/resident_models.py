"""Explicit activation of managed resident models; never reopen or unload them."""

import contextlib
import uuid
from pathlib import Path

from .checkpoint_context import checkpoint_expected_empty, context_path, save_checkpoint_context
from .jobs import atomic_json
from .model_context import canonical_native_path, verify_loaded_model
from .windows_model_list import inspect_models
from .windows_transport import WindowsCommandTransport

CONTEXT_FIELDS = (
    "source",
    "staged_model",
    "model_kind",
    "last_checkpoint",
    "last_verified_source",
    "last_list_source",
    "native_export_aliases",
    "reset_recovery_source",
    "reset_rollback_checkpoint",
)


def remember_model(meta):
    """Retain known managed source ownership, not a cached native row number."""
    source = meta.get("staged_model")
    if source:
        key, _ = canonical_native_path(source)
        meta.setdefault("resident_model_contexts", {})[key] = {
            name: meta.get(name) for name in CONTEXT_FIELDS
        }


def source_candidates(context):
    primary = context["staged_model"]
    candidates = [primary]
    if context["model_kind"] != "keyword":
        return candidates
    if context.get("reset_recovery_source") == primary and context.get("last_checkpoint") == context.get(
        "reset_rollback_checkpoint"
    ):
        # Reset's undo file belongs to the previous model, not the blank one.
        return candidates
    return (
        candidates
        + [context.get(k) for k in ("last_checkpoint", "last_verified_source", "last_list_source")]
        + list(context.get("native_export_aliases") or [])
    )


def remember_exports(meta, paths, native_data, session_id, session_directory):
    """Bind actual native saves only after verifying the currently managed source.

    Beam-safe inspection also saves a keyword file and changes the native file
    label. Preserve that proven alias without changing the recovery checkpoint.
    """
    paths = [Path(p) for p in paths if Path(p).is_file()]
    if (
        not paths
        or not meta.get("staged_model")
        or meta.get("model_kind") != "keyword"
        or not isinstance(native_data, dict)
    ):
        return None
    try:
        verified = verify_context(meta, native_data, session_id)
    except (ValueError, OSError):
        return dict(
            registered=False,
            reason="Active source not verified; exported path is not trusted as a resident alias",
        )
    aliases = list(meta.get("native_export_aliases") or [])
    for path in paths:
        save_checkpoint_context(path, session_id, native_data, session_directory)
        if str(path) not in aliases:
            aliases.append(str(path))
    meta["native_export_aliases"] = aliases
    remember_model(meta)
    return dict(registered=True, paths=[str(p) for p in paths], model_context=verified)


def owned_target(meta, source_path, session_id=None):
    key, _ = canonical_native_path(source_path)
    target = meta.get("resident_model_contexts", {}).get(key)
    if target is None and session_id:
        matches = []
        for context in meta.get("resident_model_contexts", {}).values():
            if context.get("model_kind") != "keyword":
                continue
            aliases = source_candidates(context)[1:]
            if any(p and canonical_native_path(p)[0] == key for p in aliases):
                if not context_path(source_path).is_file():
                    raise ValueError("Requested resident alias lacks file-bound context")
                checkpoint_expected_empty(source_path, session_id)
                matches.append(context)
        if len(matches) != 1:
            raise ValueError("Requested resident source is unmanaged or ambiguous")
        target = matches[0]
    if not target or target.get("model_kind") not in ("keyword", "d3plot"):
        raise ValueError("Target must be a successfully opened managed resident source from this session")
    registered_key = canonical_native_path(target["staged_model"])[0]
    if meta.get("resident_model_contexts", {}).get(registered_key) != target:
        raise ValueError("Resident context source identity mismatch")
    return dict(target)


def matching_row(rows, source_path):
    wanted, _ = canonical_native_path(source_path)
    matches = []
    for row in rows:
        try:
            actual, _ = canonical_native_path(row.get("path"))
        except ValueError:
            continue
        if actual == wanted:
            matches.append(row)
    if len(matches) != 1:
        raise ValueError("Resident source is absent or ambiguous in the current native model list")
    return matches[0]


def matching_resident_row(rows, context, session_id):
    """Native list paths can update to the model's most recent save filename."""
    candidates = source_candidates(context)
    matches = {}
    for source in dict.fromkeys(candidates):
        if not source:
            continue
        key, _ = canonical_native_path(source)
        found = [r for r in rows if r.get("path") and canonical_native_path(r["path"])[0] == key]
        if not found:
            continue
        if key != canonical_native_path(context["staged_model"])[0]:
            if not context_path(source).is_file():
                raise ValueError("Resident list alias lacks file-bound context")
            checkpoint_expected_empty(source, session_id)
        matches.update({r["row_index"]: r for r in found})
    if len(matches) != 1:
        raise ValueError("Managed resident source/checked aliases are absent or ambiguous in native list")
    return next(iter(matches.values()))


def verify_context(context, data, session_id=None):
    counts = data.get("counts", {})
    candidates = source_candidates(context) if session_id else [context["staged_model"]]
    failure = None
    for candidate in dict.fromkeys(candidates):
        if not candidate:
            continue
        try:
            check = verify_loaded_model(
                dict(
                    model=candidate,
                    file_type=context["model_kind"],
                    expected_empty=context["model_kind"] == "keyword" and counts.get("nodes") == 0,
                ),
                data,
            )
        except ValueError as exc:
            failure = exc
            continue
        if canonical_native_path(candidate)[0] != canonical_native_path(context["staged_model"])[0]:
            if not context_path(candidate).is_file():
                raise ValueError("Resident checkpoint alias lacks its file-bound context")
            checkpoint_expected_empty(
                candidate, session_id
            )  # Validate owner/hash, not current in-memory counts.
        return dict(check, resident_staged_source=context["staged_model"])
    raise failure or ValueError("No verified resident source identity")


def activate(service, session_id, source_path, *, _manager=None):
    # A containing resident-model transaction may already hold this lock.
    manager = _manager or service._session_manager()
    with contextlib.nullcontext() if _manager is not None else manager.lock(session_id):
        meta = manager.read(session_id)
        if meta["state"] != "ready" or meta.get("active_request"):
            raise ValueError("Resolve the pending or uncertain request before switching models")
        if meta.get("recording"):
            raise ValueError(
                "Resident-model activation is not portable in current single-baseline recordings; stop recording first"
            )
        remember_model(meta)
        target = owned_target(meta, source_path, session_id)
        if not meta.get("staged_model"):
            raise ValueError("Current native source has no managed context; explicitly open a model first")
        transport = WindowsCommandTransport(meta["process"]["pid"])
        transport.preflight()
        listed = inspect_models(transport, close_panel=True)
        row = matching_resident_row(listed["models"], target, session_id)
        baseline = manager.dispatch(session_id, "inspect_model", {})
        if baseline["status"] != "succeeded":
            return baseline
        try:
            baseline_context = verify_context(meta, baseline["data"], session_id)
            current = matching_resident_row(listed["models"], meta, session_id)
        except ValueError:
            meta.update(state="uncertain", dirty=True)
            manager.save(session_id, meta)
            raise
        if current["row_index"] == row["row_index"]:
            return dict(
                baseline,
                already_active=True,
                model_context=baseline_context,
                native_models=listed,
                activation_scope="Already active; no model command submitted",
            )

        def checkpoint(context):
            if context["model_kind"] != "keyword":
                return None
            saved = manager.dispatch(
                session_id, "export_keyword", {}, artifacts=(("model.k", "keyword"),), export=True
            )
            if saved["status"] != "succeeded":
                raise RuntimeError("Failed to preserve resident keyword model; inspect session evidence")
            return saved["artifacts"][0]["path"]

        # Always save outgoing keyword memory, including manual edits whose
        # dirty flag cannot be inferred. Publish its recovery file before switch.
        outgoing = checkpoint(meta)
        meta = manager.read(session_id)
        if outgoing:
            meta.update(last_checkpoint=outgoing, dirty=False)
        meta["last_verified_source"] = baseline_context["expected_source"]
        meta["last_list_source"] = current["path"]
        remember_model(meta)
        manager.save(session_id, meta)
        result = manager.dispatch(
            session_id, "inspect_model", {}, native_commands=["model select " + str(row["row_index"])]
        )
        if result["status"] != "succeeded":
            return result
        atomic_json(Path(result["job_directory"]) / "models-before.json", listed)
        try:
            after = inspect_models(transport, close_panel=True)
            atomic_json(Path(result["job_directory"]) / "models-after.json", after)
            verified = verify_context(target, result["data"], session_id)
            if list_identities(after["models"], meta, session_id) != list_identities(
                listed["models"], meta, session_id
            ):
                raise ValueError("Resident model list changed during activation")
            incoming = checkpoint(target)
            meta = manager.read(session_id)
            meta.update(target)
            meta["last_verified_source"] = verified["expected_source"]
            meta["last_list_source"] = matching_resident_row(after["models"], target, session_id)["path"]
            meta.update(
                model_generation=uuid.uuid4().hex,
                selection_buffers={},
                entity_visibility_last=None,
                managed_fringe=None,
                fringe_storage={},
                reset_recovery_source=None,
                reset_rollback_checkpoint=None,
                dirty=False,
            )
            if incoming:
                meta["last_checkpoint"] = incoming
            remember_model(meta)
            manager.save(session_id, meta)
            result.update(
                model_context=verified,
                native_models=after,
                already_active=False,
                outgoing_checkpoint=outgoing,
                active_checkpoint=incoming,
                activation_scope="Existing managed resident source only; no reopen/unload. Keyword memory saved before and after switching; model selection/scene replay and other resident crash recovery not certified.",
            )
        except Exception as exc:
            meta = manager.read(session_id)
            meta.update(state="uncertain", dirty=True)
            manager.save(session_id, meta)
            result.update(status="failed", error={"message": str(exc)}, outgoing_checkpoint=outgoing)
        atomic_json(Path(result["job_directory"]) / "activation.json", result)
        manager.journal(
            session_id,
            dict(action="activate_gui_model", parameters=dict(source_path=source_path), result=result),
        )
        return result


def removal_number(rows, target):
    value = target.get("display_number")
    if type(value) is not int or value <= 0 or sum(r.get("display_number") == value for r in rows) != 1:
        raise ValueError("Unloading requires a unique positive native display number")
    return value


def list_identities(rows, meta, session_id):
    """Stable comparison across row shifts and owned native save-path updates."""
    identities = []
    for row in rows:
        raw_path = row.get("path")
        identity = canonical_native_path(raw_path)[0] if raw_path else None
        owners = []
        for context in meta.get("resident_model_contexts", {}).values():
            if any(p and canonical_native_path(p)[0] == identity for p in source_candidates(context)):
                matching_resident_row([row], context, session_id)  # Validate any checkpoint alias.
                owners.append(canonical_native_path(context["staged_model"])[0])
        if len(owners) > 1:
            raise ValueError("Native list entry has ambiguous managed ownership")
        identities.append((row["display_label"], owners[0] if owners else identity))
    return identities


def unload(service, session_id, source_path, activate_source_path, *, _manager=None):
    manager = _manager or service._session_manager()
    with contextlib.nullcontext() if _manager is not None else manager.lock(session_id):
        meta = manager.read(session_id)
        if meta["state"] != "ready" or meta.get("active_request") or meta.get("recording"):
            raise ValueError(
                "Unloading requires a ready session without pending requests or active recording"
            )
        remember_model(meta)
        target = owned_target(meta, source_path, session_id)
        survivor = owned_target(meta, activate_source_path, session_id)
        target_key = canonical_native_path(target["staged_model"])[0]
        survivor_key = canonical_native_path(survivor["staged_model"])[0]
        if target_key == survivor_key:
            raise ValueError("Specify a different managed model to keep active after unloading")
        transport = WindowsCommandTransport(meta["process"]["pid"])
        transport.preflight()
        initial = inspect_models(transport, close_panel=True)
        audit = manager.directory(session_id) / "model-operations" / uuid.uuid4().hex
        audit.mkdir(parents=True)
        atomic_json(
            audit / "unload-preflight.json", dict(native_models=initial, target=target, survivor=survivor)
        )
        target_row = matching_resident_row(initial["models"], target, session_id)
        matching_resident_row(initial["models"], survivor, session_id)
        removal_number(initial["models"], target_row)
        removal_survivor = survivor
        if target["model_kind"] == "d3plot" and survivor["model_kind"] == "d3plot":
            # The tested native build can exit when removing one result while
            # another result is active. Use a verified resident keyword as the
            # temporary active model; still return the requested result active.
            removal_survivor = None
            for context in meta.get("resident_model_contexts", {}).values():
                if context.get("model_kind") != "keyword":
                    continue
                try:
                    matching_resident_row(initial["models"], context, session_id)
                except (ValueError, OSError):
                    continue
                removal_survivor = context
                break
            if removal_survivor is None:
                raise ValueError(
                    "Result-to-result unload requires a verified resident keyword intermediary; explicit replace_gui_model creates one"
                )

        # Capture even untracked manual keyword edits by visiting the target,
        # then preserve its memory while moving to the requested survivor.
        prepared = []
        for context in (target, removal_survivor):
            result = activate(service, session_id, context["staged_model"], _manager=manager)
            prepared.append(result)
            if result["status"] != "succeeded":
                return dict(result, unload_submitted=False, preparation=prepared)
        meta = manager.read(session_id)
        target = owned_target(meta, target["staged_model"], session_id)
        survivor = owned_target(meta, survivor["staged_model"], session_id)
        before = inspect_models(transport, close_panel=True)
        target_row = matching_resident_row(before["models"], target, session_id)
        number = removal_number(before["models"], target_row)
        remaining = [r for r in before["models"] if r["row_index"] != target_row["row_index"]]
        expected = list_identities(remaining, meta, session_id)
        result = manager.dispatch(
            session_id, "inspect_model", {}, native_commands=["model remove " + str(number)]
        )
        directory = Path(result["job_directory"])
        evidence = dict(
            target=target,
            survivor=survivor,
            before=before,
            preparation=prepared,
            remove_display_number=number,
            removed_checkpoint=target.get("last_checkpoint"),
            removal_active_source=removal_survivor["staged_model"],
        )
        atomic_json(directory / "unload-preparation.json", evidence)
        if result["status"] != "succeeded":
            return dict(result, unload_submitted=True, removed_checkpoint=target.get("last_checkpoint"))
        try:
            after = inspect_models(transport, close_panel=True)
            atomic_json(directory / "models-after-remove.json", after)
            if list_identities(after["models"], meta, session_id) != expected:
                raise ValueError(
                    "Native unload did not remove exactly the requested model and preserve other entries"
                )
            row = matching_resident_row(after["models"], survivor, session_id)
            selected = manager.dispatch(
                session_id, "inspect_model", {}, native_commands=["model select " + str(row["row_index"])]
            )
            atomic_json(directory / "survivor-reselected.json", selected)
            if selected["status"] != "succeeded":
                raise ValueError("Could not verify surviving active model after unload")
            verified = verify_context(survivor, selected["data"], session_id)
            final = inspect_models(transport, close_panel=True)
            if list_identities(final["models"], meta, session_id) != expected:
                raise ValueError("Native list changed while reselecting the surviving model")
            meta = manager.read(session_id)
            meta["resident_model_contexts"].pop(target_key)
            meta.setdefault("unloaded_model_checkpoints", []).append(dict(target, evidence=str(directory)))
            meta.update(survivor)
            meta["last_list_source"] = matching_resident_row(final["models"], survivor, session_id)["path"]
            meta.update(
                last_verified_source=verified["expected_source"],
                model_generation=uuid.uuid4().hex,
                selection_buffers={},
                entity_visibility_last=None,
                managed_fringe=None,
                fringe_storage={},
                reset_recovery_source=None,
                reset_rollback_checkpoint=None,
                dirty=False,
            )
            manager.save(session_id, meta)
            result.update(
                data=selected["data"],
                model_context=verified,
                native_models=final,
                unload_submitted=True,
                removed_checkpoint=target.get("last_checkpoint"),
                removed_source=target["staged_model"],
                active_source=survivor["staged_model"],
                remove_display_number=number,
                removal_active_source=removal_survivor["staged_model"],
                unload_scope="One managed resident model only; keyword checkpoint retained, files not deleted. Explicit survivor reselected and all remaining list entries verified. Full scene/multi-model crash recovery and replace/attach workflows remain separate.",
            )
        except Exception as exc:
            meta = manager.read(session_id)
            meta.update(state="uncertain", dirty=True)
            manager.save(session_id, meta)
            result.update(
                status="failed",
                error=dict(message=str(exc)),
                unload_submitted=True,
                removed_checkpoint=target.get("last_checkpoint"),
            )
        atomic_json(directory / "unload.json", result)
        manager.journal(
            session_id,
            dict(
                action="unload_gui_model",
                parameters=dict(source_path=source_path, activate_source_path=activate_source_path),
                result=result,
            ),
        )
        return result
