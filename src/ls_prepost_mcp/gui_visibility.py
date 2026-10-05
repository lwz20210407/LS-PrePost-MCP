"""Entity Blank operations with complete native display-state preservation proof."""

import hashlib
import struct
from pathlib import Path

from pydantic import StrictInt

from .config import command_path
from .gui_mesh import verify_mesh_digest
from .gui_selection import part_visibility
from .jobs import atomic_json, check_artifact
from .post_backend import ids
from .programs import native_errors

CODES = {"shell": 10, "solid": 11, "beam": 12, "element": 19}


def flags(data, directory):
    if data.get("auxiliary_elements"):
        raise ValueError("Mass element display flags are not verified; refusing visibility mutation")
    metadata = data.get("visibility_binary")
    if metadata is None:
        raise ValueError("Start a new GUI session for the entity visibility bridge")
    count = metadata.get("count")
    if (metadata.get("format") != "native_display_active_v1" or metadata.get("record_format") != "!BqB"
            or metadata.get("file") != "visibility.bin" or type(count) is not int or not 0 <= count <= 1000000
            or metadata.get("byte_count") != count*10 or count != data["counts"]["elements"]):
        raise ValueError("Invalid native visibility binary contract")
    path = Path(directory)/"visibility.bin"
    if path.resolve().parent != Path(directory).resolve() or path.stat().st_size != count*10:
        raise ValueError("Invalid visibility binary location or size")
    out = {}
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(40960):
            if len(block) % 10:
                raise ValueError("Truncated native visibility record")
            digest.update(block)
            for kind, uid, active in struct.iter_unpack("!BqB", block):
                if kind not in (1, 2, 3) or uid <= 0 or active not in (0, 1):
                    raise ValueError("Invalid native entity visibility readback")
                key = ({1: "beam", 2: "shell", 3: "solid"}[kind], uid)
                if key in out:
                    raise ValueError("Duplicate native entity identity")
                out[key] = bool(active)
    if len(out) != count or digest.hexdigest() != metadata.get("sha256"):
        raise ValueError("Visibility binary count/hash mismatch")
    return out


def identity(data):
    return dict(counts=data["counts"], state=data["current_state"],
                geometry={k: data["mesh_digest"][k] for k in ("node_ids", "coordinates", "connectivity", "part_membership")})


def selected_commands(kind, identifiers):
    target = "shell" if kind == "shell" else "element"
    return ["genselect clear", "genselect target "+target]+[
        "genselect %s add %s %d" % (target, target, uid) for uid in sorted(identifiers)]


def transitions(kind, old, desired):
    """Set only changed flags: two global reversals bracket a subset hide for show."""
    code = CODES[kind]
    changed = {key for key in desired if desired[key] != old[key]}
    if not changed:
        return ["genselect clear"]
    scoped = {key for key in old if kind == "element" or key[0] == kind}
    shown, hidden = {key[1] for key in changed if desired[key]}, {key[1] for key in changed if not desired[key]}
    if len({desired[key] for key in scoped}) == 1:
        return ["unblank all %d" % code if shown else "blank all %d" % code, "genselect clear"]
    if changed == scoped:
        return ["blank reverse %d" % code, "genselect clear"]
    prefix = []
    all_shown = {key[1] for key in scoped if desired[key]}
    all_hidden = {key[1] for key in scoped if not desired[key]}
    # Reset the requested type and apply the smaller complement. This avoids
    # thousands of individual hide commands when isolating a tiny subset.
    if len(all_shown) < len(shown)+len(hidden) and len(all_shown) <= len(all_hidden):
        prefix, shown, hidden = ["blank all %d" % code], all_shown, set()
    elif len(all_hidden) < len(shown)+len(hidden):
        prefix, shown, hidden = ["unblank all %d" % code], set(), all_hidden
    if len(shown)+len(hidden) > 20000:
        raise ValueError("Nonuniform visibility transition exceeds the 20,000 explicit-ID budget; this is not a model-size limit")
    commands = prefix
    if shown:
        commands += ["blank reverse %d" % code]+selected_commands(kind, shown)+[
            "blank selection", "blank reverse %d" % code]
    if hidden:
        commands += selected_commands(kind, hidden)+["blank selection"]
    return commands+["genselect clear"]


class GuiVisibilityTools:
    def set_gui_entity_visibility(self, session_id: str, entity_type: str, mode: str,
                                  entity_ids: list[StrictInt] | None = None, capture: bool = False) -> dict:
        """Native F8 element Blank for shell/solid/beam/all standard elements: hide/show/isolate/reverse or managed restore_last. None means entire requested domain; [] is explicit empty scope. Complete display-active flags, geometry/state and original part visibility are checked. Part flags are temporarily shown for readback, then restored; selection is cleared. Display-active is not an independent physical erosion mask. Node glyph visibility remains unsupported; do not substitute part hiding."""
        if entity_type not in CODES or mode not in ("hide", "show", "isolate", "reverse", "restore_last"):
            raise ValueError("Unsupported entity visibility type or mode")
        if entity_ids is not None:
            if not isinstance(entity_ids, list):
                raise ValueError("entity_ids must be a list")
            if entity_ids:
                ids(entity_ids, "entity_ids", 20000)
        if mode == "restore_last" and entity_ids is not None:
            raise ValueError("restore_last uses the owned last verified change, not supplied IDs")
        if type(capture) is not bool:
            raise ValueError("capture must be boolean")
        manager = self._session_manager()
        arguments = dict(entity_type=entity_type, mode=mode, entity_ids=entity_ids, capture=capture)
        with manager.lock(session_id):
            meta = self._visible_mesh_session(session_id, manager, allow_results=True)
            baseline = manager.dispatch(session_id, "gui_mesh_digest", {}, native_commands=["anim stop"])
            if baseline["status"] != "succeeded":
                return baseline
            original = baseline["data"]
            original_parts = part_visibility(original)
            restore = ["-m "+pid for pid, active in original_parts.items() if not active]+["genselect clear"]
            log = manager.directory(session_id)/"lspost.msg"
            offset = log.stat().st_size if log.exists() else 0
            result, directory, changed_scene = baseline, Path(baseline["job_directory"]), False
            failure = None
            old, desired = {}, {}
            pending_last = None
            preservation_verified = False
            try:
                reveal = ["+m "+pid for pid, active in original_parts.items() if not active]+["genselect clear"]
                view = manager.dispatch(session_id, "gui_mesh_digest", dict(visibility_readback=True), native_commands=reveal)
                result, directory = view, Path(view["job_directory"])
                if view["status"] != "succeeded":
                    raise ValueError("Native visibility baseline failed")
                verify_mesh_digest(original, view["data"])
                old = flags(view["data"], directory)
                domain = {key for key in old if entity_type == "element" or key[0] == entity_type}
                if not domain:
                    raise ValueError("Requested element domain is absent")
                if mode == "restore_last":
                    saved = manager.read(session_id).get("entity_visibility_last")
                    if not saved or saved["entity_type"] != entity_type or saved["identity"] != identity(original):
                        raise ValueError("No matching verified last change, or model/state changed")
                    target = {(kind, uid) for kind, uid, _ in saved["after"]}
                    if any(old.get((kind, uid)) != value for kind, uid, value in saved["after"]):
                        raise ValueError("Touched visibility changed externally; cannot restore the owned change")
                    desired = dict(old)
                    desired.update({(kind, uid): value for kind, uid, value in saved["before"]})
                else:
                    if entity_ids is None:
                        target = domain
                    else:
                        wanted = set(entity_ids)
                        target = {key for key in domain if key[1] in wanted}
                        if {key[1] for key in target} != wanted:
                            raise ValueError("Unknown selected entity IDs")
                    desired = dict(old)
                    for key in domain if mode == "isolate" else target:
                        desired[key] = (key in target) if mode == "isolate" else not old[key] if mode == "reverse" else mode == "show"
                all_ids = [key[1] for key in old]
                if len(all_ids) != len(set(all_ids)):
                    raise ValueError("Visibility selection requires globally unique element IDs")
                commands = transitions(entity_type, old, desired)
                changed_scene = True
                applied = manager.dispatch(session_id, "gui_mesh_digest", dict(visibility_readback=True), native_commands=commands)
                result, directory = applied, Path(applied["job_directory"])
                atomic_json(directory/"requested.json", arguments)
                atomic_json(directory/"before-visibility.json", dict(job_directory=view["job_directory"], native_state=view["data"]))
                if applied["status"] != "succeeded":
                    raise ValueError("Native Blank command/readback failed")
                verify_mesh_digest(original, applied["data"])
                actual = flags(applied["data"], directory)
                if actual != desired:
                    raise ValueError("Native display-active flags differ from requested visibility; deletion/other validity may prevent display")
                changed = {key for key in old if old[key] != desired[key]}
                result["verification"] = dict(entity_type=entity_type, mode=mode, scope_count=len(domain),
                    requested_count=len(target), changed_count=len(changed), visible_count=sum(desired[key] for key in domain),
                    geometry_preserved=True, unrequested_visibility_preserved=True,
                    visibility_scope="Native display-active flags with parts shown; not independent physical alive/erosion flags",
                    scene_after="Original part flags restored; general selection cleared; animation stopped")
                if mode != "restore_last" and changed:
                    pending_last = dict(entity_type=entity_type, identity=identity(original),
                        before=[[kind, uid, old[(kind, uid)]] for kind, uid in sorted(changed)],
                        after=[[kind, uid, desired[(kind, uid)]] for kind, uid in sorted(changed)])
            except Exception as exc:
                failure = exc
            finally:
                if not manager.read(session_id).get("active_request"):
                    try:
                        restored = manager.dispatch(session_id, "gui_mesh_digest", {}, native_commands=restore)
                        if restored["status"] != "succeeded":
                            raise ValueError("Original part/geometry restoration could not be verified")
                        verify_mesh_digest(original, restored["data"])
                        if part_visibility(restored["data"]) != original_parts or restored["data"]["current_state"] != original["current_state"]:
                            raise ValueError("State/part visibility differs after Blank")
                        preservation_verified = True
                        if failure is None and result.get("verification"):
                            result["verification"]["part_visibility_preserved"] = True
                    except Exception as exc:
                        failure = failure or exc
            if failure:
                uncertain = not preservation_verified or bool(manager.read(session_id).get("active_request"))
                result.update(status="uncertain" if uncertain else "failed", error=dict(type=type(failure).__name__, message=str(failure)), artifacts=[])
                result["warnings"] = ["Partial visibility changes may remain" if changed_scene else "No Blank transition submitted"]
                if uncertain:
                    current = manager.read(session_id)
                    current.update(state="uncertain", last_error=str(failure))
                    manager.save(session_id, current)
            else:
                try:
                    with log.open("rb") as stream:
                        stream.seek(offset)
                        text = stream.read().decode("utf8", errors="replace")
                    (directory/"native.log").write_text(text, encoding="utf8")
                    if native_errors(text):
                        raise ValueError("Native Blank reported command errors")
                    atomic_json(directory/"verification.json", result["verification"])
                    result["artifacts"].append(check_artifact(directory/"verification.json", "json"))
                    if capture:
                        image = manager.dispatch(session_id, "inspect_model", {}, native_commands=[
                            "print png "+command_path(directory/"visibility.png")+' opaque enlisted "OGL1x1"'])
                        if image["status"] == "succeeded":
                            result["artifacts"].append(check_artifact(directory/"visibility.png", "png"))
                        else:
                            raise ValueError("Visibility image failed")
                except Exception as exc:
                    result.update(status="uncertain" if manager.read(session_id).get("active_request") else "failed",
                                  error=dict(type=type(exc).__name__, message=str(exc)), artifacts=[])
            if result["status"] == "succeeded":
                current = manager.read(session_id)
                if mode == "restore_last" or pending_last:
                    current["entity_visibility_last"] = pending_last
                    manager.save(session_id, current)
            if result.get("data"):
                atomic_json(directory/"native-state.json", result["data"])
                result["data"] = dict(model_kind=meta["model_kind"], native_state=original["current_state"],
                                      part_visibility=original_parts, verification=result.get("verification"))
            result["parameters"] = arguments
            atomic_json(directory/"operation.json", result)
            manager.journal(session_id, dict(action="set_gui_entity_visibility", parameters=arguments, result=result))
            return result
