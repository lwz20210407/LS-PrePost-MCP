"""File-bound native inventory hints for saved keyword recovery.

The session's trusted checkpoint pointer decides what may be restored. This
sidecar only supplies its zero-entity expectation; it is not a physics verdict.
"""

import json
from pathlib import Path

from .jobs import atomic_json, fingerprint


def context_path(path):
    path = Path(path)
    return path.with_name(path.name + ".lspp-context.json")


def valid_counts(counts):
    return isinstance(counts, dict) and all(
        type(counts.get(k)) is int and counts[k] >= 0 for k in ("nodes", "elements")
    )


def save_checkpoint_context(path, session_id, data, session_directory):
    counts = data.get("counts") if isinstance(data, dict) else None
    if not valid_counts(counts):
        return None  # Legacy/limited replies cannot supply an empty expectation.
    path = Path(path).resolve()
    if not path.is_relative_to(Path(session_directory).resolve()):
        raise ValueError("Checkpoint context must stay inside the owned session")
    identity = fingerprint(path)
    record = dict(
        schema_version=1,
        session_id=session_id,
        file=identity,
        counts=counts,
        scope="Native inventory at saved/opened file; trusted checkpoint pointer is checked separately",
    )
    atomic_json(context_path(path), record)
    return record


def checkpoint_expected_empty(path, session_id):
    path = Path(path).resolve()
    sidecar = context_path(path)
    if not sidecar.exists():
        return False  # Preserve the legacy nonempty open rule; do not guess from text.
    record = json.loads(sidecar.read_text(encoding="utf8"))
    if (
        record.get("schema_version") != 1
        or record.get("session_id") != session_id
        or not valid_counts(record.get("counts"))
        or not isinstance(record.get("file"), dict)
    ):
        raise ValueError("Invalid or foreign checkpoint inventory context")
    saved, current = record["file"], fingerprint(path)
    if Path(saved.get("path", "")).resolve() != path or any(
        saved.get(k) != current[k] for k in ("sha256", "size")
    ):
        raise ValueError("Checkpoint changed since its native inventory was recorded")
    counts = record["counts"]
    if counts["nodes"] == 0:
        if counts["elements"] != 0:
            raise ValueError("Zero-node checkpoint cannot contain elements")
        return True
    return False


def reset_baseline(directory, rollback_checkpoint):
    path = str(Path(directory) / 'initial.k')
    return dict(source=None, staged_model=path, reset_recovery_source=path,
                reset_rollback_checkpoint=rollback_checkpoint, native_export_aliases=[],
                last_verified_source=None, last_list_source=None)


def restart_source(meta):
    if meta['model_kind'] != 'keyword':
        return meta.get('staged_model')
    reset = meta.get('reset_recovery_source')
    if (reset and meta.get('staged_model') == reset
            and meta.get('last_checkpoint') == meta.get('reset_rollback_checkpoint')):
        return reset  # Preserve last_checkpoint as explicit undo, not current state.
    return meta.get('last_checkpoint') or meta.get('staged_model')
