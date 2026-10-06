"""Selection-driven native entity creation with card/mesh/scene readback."""

import json
from pathlib import Path

from pydantic import StrictInt

from .core.validation import integer
from .deck_backend import api
from .entity_cards import (
    DOFS,
    check_motion_conflicts,
    check_spc_conflicts,
    element_set_fragment,
    inspect_cards,
    set_members,
    verify_cards,
)
from .gui_mesh import verify_mesh_digest
from .gui_selection import mesh_signature, part_visibility
from .jobs import atomic_json, check_artifact
from .native import commands as nc
from .post_backend import ids


def entity_title(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 70 or any(not 32 <= ord(c) <= 126 for c in value):
        raise ValueError("Use a nonempty printable ASCII entity title (max70 characters); Unicode native labels are not yet verified")
    if not value.strip() or value.lstrip().startswith(("*", "$")):
        raise ValueError("Entity title cannot be blank or start with a keyword/comment marker")
    return value.strip()


def stable_scene(before, after):
    verify_mesh_digest(before, after)
    if (part_visibility(before) != part_visibility(after) or before["current_state"] != after["current_state"]
            or before.get("visibility_binary") is None or before["visibility_binary"] != after.get("visibility_binary")):
        raise ValueError("Entity operation changed part/element display-active flags or current state")
    return dict(geometry_preserved=True, display_active_preserved=None if before.get("auxiliary_elements") else True, state_preserved=True,
                structural_display_active_preserved=True,
                display_active_scope="Registered shell/solid/beam elements and parts; auxiliary mass glyph flags unverified" if before.get("auxiliary_elements") else "Registered elements and parts",
                auxiliary_elements=after.get("auxiliary_elements"),
                route="lsprepost_native_keyword_fragment_import", solver_validated=False)


def selection_source(manager, sid, directory, kind):
    path = Path(directory).resolve(strict=True)
    if path.parent != (manager.directory(sid) / "requests").resolve():
        raise ValueError("Selection source must be an owned request in this session")
    result = json.loads((path / "operation.json").read_text(encoding="utf-8"))
    verification = result.get("verification", {})
    generation = manager.read(sid).get("model_generation")
    if not generation or result.get("model_generation") != generation:
        raise ValueError("Selection belongs to an older model load; create a fresh selection in an updated session")
    if result.get("session_id") != sid or result.get("status") != "succeeded" or verification.get("entity_type") != kind:
        raise ValueError("Selection source is not a successful selection of the requested entity type")
    members = verification.get("selected_ids")
    ids(members, "selected_ids", 20000)
    state = json.loads((path / "after.json").read_text(encoding="utf-8"))
    return members, state, str(path)


class GuiEntityTools:
    def create_gui_entity_set(self, session_id: str, entity_type: str, set_id: StrictInt, title: str,
                              entity_ids: list[StrictInt] | None = None, selection_job: str | None = None,
                              mode: str = "create") -> dict:
        """Create native node/part/shell/solid/beam explicit-list sets from user IDs or a successful same-domain/session selection job (one source only). Reject stale models, empty/wrong-domain members and same-domain SID collisions. replace_members currently supports node/part only, preserving DA/solver/ITS; element-set replacement needs consumer impact analysis. Import a bounded keyword fragment in the visible GUI; verify cards, full mesh/state/display and unrelated cards. Max20000 members; no Generate/General/Add/Collect, Include, discrete/seatbelt or complete panel certification. Recorded result dependencies preserve selection-to-set replay."""

        if entity_type not in ("node", "part", "shell", "solid", "beam"):
            raise ValueError("Entity set type must be node, part, shell, solid or beam")
        if mode not in ("create", "replace_members"):
            raise ValueError("Set mode must be create or replace_members")
        element_set = entity_type in ("shell", "solid", "beam")
        if element_set and mode != "create":
            raise ValueError("Element-set replacement requires consumer impact analysis; currently create/query only")
        integer(set_id, "set_id")
        title = entity_title(title)
        if (entity_ids is None) == (selection_job is None):
            raise ValueError("Provide exactly one of entity_ids or selection_job")
        manager = self._session_manager()
        source_state = None
        if selection_job is not None:
            members, source_state, selection_job = selection_source(manager, session_id, selection_job, entity_type)
        else:
            ids(entity_ids, "entity_ids", 20000)
            members = sorted(entity_ids)
        Deck, kw = api()
        if element_set:
            fragment_text, attributes = element_set_fragment(entity_type, set_id, title, members)
        else:
            card = (kw.SetNodeList if entity_type == "node" else kw.SetPartList)(sid=set_id)
            setattr(card, "nodes" if entity_type == "node" else "parts", members)
            card.title = title
            fragment = Deck()
            fragment.append(card)
            attributes = dict(attributes=[0.0] * 4, solver="MECH", its="1" if entity_type == "node" else None)
        baseline = {}

        def precheck(state):
            if selection_job is not None:
                selection_source(manager, session_id, selection_job, entity_type)
            if set(state["registry_matches"]) != set(members):
                raise ValueError("Set references unknown current-model entities")
            if source_state is not None and (mesh_signature(state) != mesh_signature(source_state)
                    or state["current_state"] != source_state["current_state"]):
                raise ValueError("Selection model/state is stale; select again before creating a set")

        def preflight(path):
            baseline.update(inspect_cards(path))
            if any(n.startswith("*SET_" + entity_type.upper()) for n, _ in baseline["unresolved"]):
                raise ValueError("Resolve unsupported same-domain set variants before creating this set")
            present = (entity_type, set_id) in baseline["sets"]
            if mode == "create" and present:
                raise ValueError("Set ID already exists in this entity domain")
            if mode == "replace_members":
                if not present:
                    raise ValueError("Cannot replace a missing set")
                old = baseline["sets"][(entity_type, set_id)]
                for key, value in zip(("da1", "da2", "da3", "da4"), old["attributes"]):
                    setattr(card, key, value)
                card.solver = old["solver"]
                if entity_type == "node":
                    card.its = old["its"]
                expected.update(attributes=old["attributes"], solver=old["solver"], its=old["its"])
                hypothetical=dict(baseline,sets=dict(baseline['sets']))
                hypothetical['sets'][(entity_type,set_id)]=dict(old,member_ids=members)
                if entity_type=='node' and any(n.startswith(('*BOUNDARY_SPC','*BOUNDARY_PRESCRIBED_MOTION')) for n,_ in baseline['unresolved']):
                    raise ValueError('Cannot replace node-set members with unresolved SPC/motion consumers')
                for i, spc in enumerate(baseline["spcs"]):
                    if entity_type == "node" and spc["target_type"] == "node_set" and spc["target_id"] == set_id:
                        peers = dict(hypothetical, spcs=baseline["spcs"][:i] + baseline["spcs"][i+1:])
                        check_spc_conflicts(peers, members, spc["coordinate_system"], spc["dofs"], spc["constraint_id"])
                for i,motion in enumerate(baseline.get('motions',[])):
                    if entity_type=='node' and motion['target_type']=='node_set' and motion['target_id']==set_id:
                        peers=dict(hypothetical,motions=baseline['motions'][:i]+baseline['motions'][i+1:])
                        check_motion_conflicts(peers,members,motion['dof'])

        def commands(state, directory):
            path = directory / "entity-set.k"
            if element_set:
                path.write_text(fragment_text, encoding="ascii")
            else:
                fragment.export_file(str(path))
            return [nc.import_keyword(path)]

        expected = dict(entity_type=entity_type, set_id=set_id, title=title, member_ids=sorted(members),
                        **attributes)
        def postcheck(_, path, validation):
            audit = verify_cards(baseline, inspect_cards(path), new_set=expected)
            affected = [s for s in baseline["spcs"] if entity_type == "node" and s["target_type"] == "node_set" and s["target_id"] == set_id]
            affected_motions=[m for m in baseline.get('motions',[]) if entity_type=='node' and m['target_type']=='node_set' and m['target_id']==set_id]
            validation.update(expected, member_count=len(members), mode=mode, referencing_spc_constraints=affected,
                              referencing_prescribed_motions=affected_motions)
            return audit

        return self._gui_mesh_edit(session_id, "create_gui_entity_set",
            dict(entity_type=entity_type, set_id=set_id, title=title, entity_ids=entity_ids, selection_job=selection_job, mode=mode),
            commands, stable_scene, precheck, postcheck, preflight,
            snapshot_parameters=dict(entity_type=entity_type, entity_ids=members, visibility_readback=True,
                                     allow_missing_entity_ids=True))

    def inspect_gui_entity_sets(self, session_id: str, entity_type: str,
                                set_id: StrictInt | None = None, offset: StrictInt = 0, limit: StrictInt = 1000) -> dict:
        """Query native-export node/part/shell/solid/beam explicit-list or segment sets with titles/counts and domain-specific attributes; optional SID returns paged user IDs or oriented segment tuples. Temporary native export and scene checks preserve dirty/checkpoint ownership. Other variants are reported unresolved, never silently treated as empty or expanded."""

        if entity_type not in ("node", "part", "segment", "shell", "solid", "beam"):
            raise ValueError("Set type must be node, part, shell, solid, beam or segment")
        integer(offset, "offset", 0)
        integer(limit, "limit", 1, 5000)
        if set_id is not None:
            integer(set_id, "set_id")
        manager = self._session_manager()
        with manager.lock(session_id):
            meta = self._visible_mesh_session(session_id, manager)
            before = manager.dispatch(session_id, "gui_mesh_digest", dict(visibility_readback=True))
            if before["status"] != "succeeded":
                return before
            result = manager.dispatch(session_id, "gui_mesh_digest", dict(visibility_readback=True),
                                      export=True, artifacts=(("model.k", "keyword"),))
            if result["status"] != "succeeded":
                return result
            directory = Path(result["job_directory"])
            preserved = False
            try:
                verification = stable_scene(before["data"], result["data"])
                preserved = True
                index = inspect_cards(directory / "model.k")
                records = [dict(entity_type=k, set_id=sid, title=s["title"], member_count=len(s.get("segments", s.get("member_ids", []))))
                           for (k, sid), s in sorted(index["sets"].items()) if k == entity_type]
                if set_id is not None:
                    members = (index["sets"][("segment", set_id)]["segments"] if entity_type == "segment"
                               else set_members(index, entity_type, set_id))
                    record = index["sets"][(entity_type, set_id)]
                    data = dict(**{k: v for k, v in record.items() if k not in ("member_ids", "segments")},
                                total=len(members))
                    data["segments" if entity_type == "segment" else "member_ids"] = members[offset:offset+limit]
                else:
                    data = dict(sets=records[offset:offset+limit], total=len(records))
                data.update(offset=offset, limit=limit, next_offset=(offset+limit if offset+limit < data["total"] else None),
                            unresolved_keywords=sorted({n for n, _ in index["unresolved"] if n.startswith("*SET_" + entity_type.upper())}),
                            backend="lsprepost_native_keyword_export")
                result.update(data=data, verification=verification)
                atomic_json(directory / "entity-sets.json", data)
                result["artifacts"].append(check_artifact(directory / "entity-sets.json", "json"))
            except Exception as exc:
                result.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
            current = manager.read(session_id)
            current.update(dirty=meta.get("dirty", False) if preserved else True,
                           last_checkpoint=meta.get("last_checkpoint"))
            if not preserved:
                current["state"] = "uncertain"
            manager.save(session_id, current)
            atomic_json(directory / "operation.json", result)
            manager.journal(session_id, dict(action="inspect_gui_entity_sets",
                            parameters=dict(entity_type=entity_type, set_id=set_id, offset=offset, limit=limit), result=result))
            return result

    def create_gui_spc(self, session_id: str, constraint_id: StrictInt, title: str, dofs: list[StrictInt],
                       node_set_id: StrictInt | None = None, node_ids: list[StrictInt] | None = None,
                       coordinate_system: StrictInt = 0) -> dict:
        """Create native SPC_SET or SPC_NODE_ID with explicit six binary DOFs [X,Y,Z,RX,RY,RZ] and coordinate-system ID (0=global). Exactly one node-set SID or explicit node-ID list. For node lists allocate consecutive constraint IDs starting at constraint_id in sorted node-ID order (one native card per node); return the mapping. Check targets, coordinate reference, all allocated IDs and overlapping SPC DOFs; unresolved SPC/motion cards reject. Verify native cards and unchanged mesh/display. No rigid/material/solver constraint compatibility, prescribed nonzero motion or arbitrary set expansion certification."""

        integer(constraint_id, "constraint_id")
        integer(coordinate_system, "coordinate_system", 0)
        title = entity_title(title)
        if not isinstance(dofs, list) or len(dofs) != 6 or any(type(v) is not int or v not in (0, 1) for v in dofs) or not any(dofs):
            raise ValueError("Specify six binary DOFs with at least one constrained direction")
        if (node_set_id is None) == (node_ids is None):
            raise ValueError("Provide exactly one node_set_id or node_ids")
        if node_set_id is not None:
            integer(node_set_id, "node_set_id")
        else:
            ids(node_ids, "node_ids", 20000)
        Deck, kw = api()
        fragment = Deck()
        expected = []
        targets = [node_set_id] if node_set_id is not None else sorted(node_ids)
        integer(constraint_id + len(targets) - 1, "last allocated constraint ID")
        for i, target in enumerate(targets):
            if node_set_id is not None:
                card = kw.BoundarySpcSet(nsid=target, cid=coordinate_system, **dict(zip(DOFS, dofs)))
            else:
                import pandas as pd
                card = kw.BoundarySpcNode()
                # Native 4.13 import retained only the first row of a multirow
                # SPC_NODE_ID block. Emit individually named native entities.
                card.nodes = pd.DataFrame([dict(nid=target, cid=coordinate_system, **dict(zip(DOFS, dofs)))])
            card.id, card.heading = constraint_id + i, title
            fragment.append(card)
            expected.append(dict(target_type="node_set" if node_set_id is not None else "node", target_id=target,
                                 coordinate_system=coordinate_system, dofs=dofs, constraint_id=constraint_id+i, title=title))
        baseline, state_before, members = {}, {}, []
        manager = self._session_manager()

        def precheck(state):
            state_before.update(state)

        def preflight(path):
            baseline.update(inspect_cards(path))
            members.extend(set_members(baseline, "node", node_set_id) if node_set_id is not None else node_ids)
            ids(members, "target nodes", 20000)
            for constraint in expected:
                check_spc_conflicts(baseline, members if node_set_id is not None else [constraint["target_id"]],
                                    coordinate_system, dofs, constraint["constraint_id"])
            registry = manager.dispatch(session_id, "gui_mesh_digest", dict(entity_type="node", entity_ids=members,
                                                                           allow_missing_entity_ids=True))
            if registry["status"] != "succeeded":
                raise ValueError("Native target-node registry verification failed")
            verify_mesh_digest(state_before, registry["data"])
            if set(registry["data"]["registry_matches"]) != set(members):
                raise ValueError("SPC references unknown current-model nodes")

        def commands(state, directory):
            path = directory / "entity-spc.k"
            fragment.export_file(str(path))
            return [nc.import_keyword(path)]

        def postcheck(_, path, validation):
            audit = verify_cards(baseline, inspect_cards(path), new_spcs=expected)
            validation.update(constraints=expected, affected_node_count=len(members))
            return audit

        return self._gui_mesh_edit(session_id, "create_gui_spc",
            dict(constraint_id=constraint_id, title=title, dofs=dofs, node_set_id=node_set_id,
                 node_ids=node_ids, coordinate_system=coordinate_system), commands, stable_scene,
            precheck, postcheck, preflight, snapshot_parameters=dict(visibility_readback=True))
