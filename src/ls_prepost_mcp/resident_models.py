"""Explicit activation of managed resident models; never reopen or unload them."""

import uuid
from pathlib import Path

from .checkpoint_context import checkpoint_expected_empty, context_path
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
    return candidates + [context.get(k) for k in ("last_checkpoint", "last_verified_source")]


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


def activate(service, session_id, source_path):
    manager = service._session_manager()
    with manager.lock(session_id):
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
        listed = inspect_models(transport)
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
        remember_model(meta)
        manager.save(session_id, meta)
        result = manager.dispatch(
            session_id, "inspect_model", {}, native_commands=["model select " + str(row["row_index"])]
        )
        if result["status"] != "succeeded":
            return result
        atomic_json(Path(result["job_directory"]) / "models-before.json", listed)
        try:
            after = inspect_models(transport)
            atomic_json(Path(result["job_directory"]) / "models-after.json", after)
            verified = verify_context(target, result["data"], session_id)
            if after["models"] != listed["models"]:
                raise ValueError("Resident model list changed during activation")
            incoming = checkpoint(target)
            meta = manager.read(session_id)
            meta.update(target)
            meta["last_verified_source"] = verified["expected_source"]
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
