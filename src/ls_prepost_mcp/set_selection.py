"""Resolve permanent list-set members inside the selection transaction lock."""

from pathlib import Path

from .entity_cards import inspect_cards, set_members
from .gui_entities import stable_scene
from .jobs import atomic_json, fingerprint


def union_members(index, kind, set_ids, limit=20000):
    selected, counts = set(), {}
    for sid in set_ids:
        members = set_members(index, kind, sid)
        selected.update(members)
        counts[str(sid)] = len(members)
        if len(selected) > limit:
            raise ValueError("Set union exceeds20000 member selection budget; narrow the sets, not the model")
    return sorted(selected), counts


def prepare_set_selection(kind, set_ids, verification):
    def prepare(manager, session_id, snapshot_parameters):
        if manager.read(session_id)["model_kind"] != "keyword":
            raise ValueError(
                "Permanent set selection currently requires a keyword model; no implicit keyword/result association"
            )
        before = manager.dispatch(session_id, "gui_mesh_digest", dict(visibility_readback=True))
        if before["status"] != "succeeded":
            return before
        exported = manager.dispatch(
            session_id,
            "gui_mesh_digest",
            dict(visibility_readback=True),
            export=True,
            artifacts=(("model.k", "keyword"),),
        )
        if exported["status"] != "succeeded":
            return exported
        try:
            stable_scene(before["data"], exported["data"])
        except Exception:
            meta = manager.read(session_id)
            meta.update(state="uncertain", dirty=True)
            manager.save(session_id, meta)
            raise
        path = Path(exported["job_directory"]) / "model.k"
        members, counts = union_members(inspect_cards(path), kind, set_ids)
        # The native registry query checks existence in this domain, then applies
        # active-part scope and inversion before selecting and reading back IDs.
        snapshot_parameters["registry_query"]["entity_ids"] = members
        evidence = dict(
            entity_type=kind,
            set_ids=list(set_ids),
            operation="union",
            per_set_count=counts,
            union_count=len(members),
            source=fingerprint(path),
            job_directory=exported["job_directory"],
            scope="Current native-export explicit lists; not arbitrary set variants or solver expansion",
        )
        atomic_json(path.parent / "set-selection-source.json", evidence)
        verification["set_source"] = evidence
        return None

    return prepare
