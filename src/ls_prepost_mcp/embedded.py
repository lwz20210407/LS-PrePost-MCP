"""Bundled application-side bridge. Keep compatible with embedded Python 3.6+.

Only this module executes inside LS-PrePost; no user Python is evaluated.
"""

import csv
import hashlib
import json
import math
import os
import struct
import sys
import traceback
from array import array as packed_array

if __package__:
    from .native import commands as nc
    from .native import versions as nv
else:
    import importlib.util

    def _support_module(name):
        root = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(root, "native_" + name + ".py")
        if not os.path.isfile(path):
            path = os.path.join(root, "native", name + ".py")
        spec = importlib.util.spec_from_file_location("_lspp_native_" + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    nc = _support_module("commands")
    nv = _support_module("versions")


def read_native_masses(path, expected_count):
    """Read standard ELEMENT_MASS without guessing undocumented SDK enum codes."""
    masses, keyword = {}, None
    with open(path, encoding="utf8", errors="strict") as stream:
        for line in stream:
            text = line.strip()
            if not text or text.startswith("$"):
                continue
            if text.startswith("*"):
                keyword = text.upper()
                continue
            if keyword != "*ELEMENT_MASS":
                continue
            fields = line.split(",") if "," in line else [line[:8], line[8:16], line[16:32], line[32:40]]
            if len(fields) > 4 and any(v.strip() for v in fields[4:]) or "," not in line and line[40:].strip():
                raise ValueError("Extended mass record is not supported")
            fields += [""] * 4
            uid, nid = int(fields[0]), int(fields[1])
            mass = float(fields[2].replace("D", "E").replace("d", "e"))
            pid = int(fields[3].strip() or 0)
            if uid <= 0 or nid <= 0 or pid < 0 or not math.isfinite(mass) or mass < 0 or uid in masses:
                raise ValueError("Invalid/duplicate native mass element")
            masses[uid] = (nid, mass, pid)
            if len(masses) > expected_count:
                raise ValueError("Native mass registry count mismatch")
    if len(masses) != expected_count:
        raise ValueError("Incomplete native mass inventory; standard ELEMENT_MASS only")
    return masses


class BeamSafeDataCenter:
    """Read standard beam endpoints from a fresh native keyword export, not the faulty array binding."""
    def __init__(self, dc, directory):
        self.original = dc
        self.Type = dc.Type
        expected = {int(v) for v in dc.get_data("element_ids", type=dc.Type.BEAM)}
        self.beams = {}
        self.masses = {}
        mass_path = os.path.join(directory, "mass-count.json")
        if os.path.isfile(mass_path):
            with open(mass_path) as stream:
                mass_count = json.load(stream)
            if mass_count is not None:
                if type(mass_count) is not int or not 0 <= mass_count <= 1000000:
                    raise ValueError("Invalid native mass count")
                if mass_count != int(dc.get_data("num_mass_elements")):
                    raise ValueError("Native mass count changed since export")
                if mass_count:
                    self.masses = read_native_masses(os.path.join(directory, "beam-connectivity.k"), mass_count)
        with open(os.path.join(directory, "beam-count.json")) as stream:
            count = json.load(stream)
        if type(count) is not int or not 0 <= count <= 1000000 or count != len(expected):
            raise ValueError("Native beam registry count mismatch")
        if count:
            keyword = None
            with open(os.path.join(directory, "beam-connectivity.k"), encoding="utf8", errors="replace") as stream:
                for line in stream:
                    text = line.strip()
                    if not text or text.startswith("$"):
                        continue
                    if text.startswith("*"):
                        keyword = text.upper()
                        continue
                    if keyword != "*ELEMENT_BEAM":
                        continue
                    fields = line.split(",") if "," in line else [line[i:i+8] for i in range(0, 40, 8)]
                    uid, pid, n1, n2 = [int(v) for v in fields[:4]]
                    if uid not in expected or uid in self.beams or min(pid, n1, n2) <= 0:
                        raise ValueError("Invalid native keyword beam record")
                    self.beams[uid] = [n1, n2]
        if set(self.beams) != expected:
            raise ValueError("Incomplete/unsupported native keyword beam connectivity; standard ELEMENT_BEAM only")

    def get_data(self, key, *args, **kwargs):
        kind = kwargs.get("type", args[0] if args else None)
        if key == "element_connectivity" and kind == self.Type.BEAM:
            if len(args) > 1 or "id" not in kwargs:
                raise ValueError("Safe beam connectivity requires an explicit id keyword")
            return self.beams[kwargs["id"]]
        return self.original.get_data(key, *args, **kwargs)


def shell_orientation_cycle(connectivity):
    values = list(connectivity)
    if len(values) == 4 and values[3] in (0, values[2]):
        values.pop()
    if len(values) not in (3, 4) or any(n <= 0 for n in values) or len(set(values)) != len(values):
        raise ValueError("Normal reversal supports standard noncollapsed Tri3/Quad4 shells")
    return min(tuple(values[i:] + values[:i]) for i in range(len(values)))


def orientation_digest_update(digest, uid, cycle):
    digest.update(struct.pack("!qq", uid, len(cycle)))
    digest.update(struct.pack("!" + "q" * len(cycle), *cycle))


def topology_shell_ids(connectivity, coordinates, seeds, mode, rings, angle):
    """Independent visible-shell graph reference for native adjacent/propagate."""
    if not set(seeds) <= set(connectivity):
        raise ValueError("Topology seeds must be registered visible standard shells")
    members, faces, normals = {}, {}, {}
    for eid, raw in connectivity.items():
        cycle = shell_orientation_cycle(raw)
        faces[eid] = cycle
        keys = cycle if mode == "adjacent" else [tuple(sorted((cycle[i], cycle[(i+1) % len(cycle)]))) for i in range(len(cycle))]
        for key in keys:
            members.setdefault(key, []).append(eid)
    def normal(eid):
        if eid not in normals:
            p = [coordinates[uid] for uid in faces[eid]]
            a = [p[1][i]-p[0][i] for i in range(3)] if len(p) == 3 else [p[2][i]-p[0][i] for i in range(3)]
            b = [p[2][i]-p[0][i] for i in range(3)] if len(p) == 3 else [p[3][i]-p[1][i] for i in range(3)]
            n = [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
            length = math.hypot(*n)
            if not math.isfinite(length) or length == 0:
                raise ValueError("Degenerate shell has no feature-angle normal")
            normals[eid] = [v/length for v in n]
        return normals[eid]
    selected, frontier = set(seeds), set(seeds)
    iteration = 0
    while frontier and (mode == "propagate" or iteration < rings):
        next_frontier = set()
        for eid in frontier:
            cycle = faces[eid]
            keys = cycle if mode == "adjacent" else [tuple(sorted((cycle[i], cycle[(i+1) % len(cycle)]))) for i in range(len(cycle))]
            for key in keys:
                for other in members[key]:
                    if other in selected:
                        continue
                    if mode == "propagate":
                        cosine = min(1., max(0., abs(sum(a*b for a,b in zip(normal(eid), normal(other))))))
                        if math.degrees(math.acos(cosine)) > angle + 1e-7:
                            continue
                    next_frontier.add(other)
        selected.update(next_frontier)
        frontier = next_frontier
        iteration += 1
    return sorted(selected)


def scoped_mesh_state(dc, lp, parameters, output_directory=None):
    """Stream complete native geometry fingerprints, materialize only requested nodes.

    This remains O(model size) work: unchanged entities are checked, not sampled.
    Native SDK arrays may be transient, so consume each before the next SDK call.
    """
    wanted_nodes = parameters.get("node_ids", [])
    wanted_ids = parameters.get("entity_ids", [])
    domain = parameters.get("entity_type", "node")
    query = parameters.get("selection_query")
    registry_query = parameters.get("registry_query")
    normal_scope = parameters.get("normal_scope")
    topology = parameters.get("topology_query")
    topology_faces = {}
    topology_error = None
    if topology is not None and (query or registry_query or normal_scope or wanted_nodes or wanted_ids or domain != "shell"):
        raise ValueError("Topology query requires an independent shell scope")
    normal_ids = None
    if normal_scope is not None:
        if query or registry_query or wanted_nodes or wanted_ids or not isinstance(normal_scope, dict):
            raise ValueError("Normal scope cannot be combined with another mesh scope")
        normal_ids = normal_scope.get("shell_ids")
        if normal_ids is not None:
            if (not isinstance(normal_ids, list) or not 1 <= len(normal_ids) <= 20000 or
                    any(type(uid) is not int or uid <= 0 for uid in normal_ids) or len(set(normal_ids)) != len(normal_ids)):
                raise ValueError("Explicit normal scope requires1..20000 unique shell IDs")
            normal_ids = set(normal_ids)
    if registry_query and (query or wanted_nodes or wanted_ids):
        raise ValueError("Registry query cannot be combined with explicit digest scopes")
    if query and (domain != "node" or wanted_nodes or wanted_ids or query.get("kind") not in ("box", "sphere", "plane")):
        raise ValueError("Spatial queries require node domain and no explicit IDs")
    if domain not in ("node", "shell", "solid", "beam", "element", "part"):
        raise ValueError("Unsupported scoped entity domain")
    for values in (wanted_nodes, wanted_ids):
        if (not isinstance(values, list) or len(values) > 20000
                or any(type(v) is not int or v <= 0 for v in values)
                or len(values) != len(set(values))):
            raise ValueError("Scoped IDs must be unique positive integers, at most20000")
    wanted_nodes, wanted_ids = set(wanted_nodes), set(wanted_ids)
    hashes = {key: hashlib.sha256() for key in (
        "node_ids", "coordinates", "unselected_coordinates", "connectivity", "part_membership",
        "unselected_connectivity", "normal_current", "normal_reversed")}
    node_indices, rows, matched, occurrences = {}, {}, [], {}
    get = dc.get_data
    masses = getattr(dc, "masses", {})
    mass_nodes = {row[0] for row in masses.values()}
    if masses and (domain == "element" or topology is not None or normal_scope is not None):
        raise ValueError("Mass preservation supports node/part/typed structural inspection, not all-element selection or shell topology/normal editing")
    array = get("validpart_ids")
    parts = [int(array[i]) for i in range(len(array))]
    visibility, filter_elements, active_elements = {}, set(), set()
    requested_parts = registry_query.get("part_ids") if registry_query else None
    if requested_parts is not None and not set(requested_parts) <= set(parts):
        raise ValueError("Unknown part ID")
    for pid in parts:
        visibility[str(pid)] = bool(lp.check_if_part_is_active_u(pid))
        array = get("elemofpart_ids", type=1, id=pid)
        hashes["part_membership"].update(struct.pack("!qq", pid, len(array)))
        for i in range(len(array)):
            eid = int(array[i])
            hashes["part_membership"].update(struct.pack("!q", eid))
            if registry_query:
                if requested_parts is not None and pid in requested_parts:
                    filter_elements.add(eid)
            if visibility[str(pid)] and (registry_query or parameters.get("visibility_readback")):
                active_elements.add(eid)
        if domain == "part" and pid in wanted_ids:
            matched.append(pid)
    domain_ids, filter_ids, active_ids, both_ids, seen_elements = set(), set(), set(), set(), set()
    registry = get("node_ids")
    count = len(registry)
    query_ids = packed_array("q") if query else None
    accum = packed_array("d", [0.0]) * count if query else None
    for i in range(count):
        uid = int(registry[i])
        mass_nodes.discard(uid)
        if registry_query and domain == "node":
            domain_ids.add(uid)
        if query:
            query_ids.append(uid)
        hashes["node_ids"].update(struct.pack("!q", uid))
        if uid in wanted_nodes:
            if uid in rows:
                raise ValueError("Duplicate requested native node ID")
            node_indices[i] = uid
            rows[uid] = [uid]
        if domain == "node" and uid in wanted_ids:
            matched.append(uid)
    if set(rows) != wanted_nodes:
        raise ValueError("Unknown requested node IDs")
    if mass_nodes:
        raise ValueError("Native mass element references an unregistered node")
    for axis, key in enumerate(("node_x", "node_y", "node_z")):
        array = get(key, type=dc.Type.NODE)
        if len(array) != count:
            raise ValueError("Native node coordinate count differs from registry")
        for start in range(0, count, 1024):
            whole, unchanged = bytearray(), bytearray()
            for i in range(start, min(count, start + 1024)):
                value = float(array[i])
                if not math.isfinite(value):
                    raise ValueError("Nonfinite native reference coordinate")
                if query:
                    if query["kind"] == "box":
                        if not query["lower"][axis] <= value <= query["upper"][axis]:
                            accum[i] = 1.0
                    elif query["kind"] == "sphere":
                        accum[i] = math.hypot(accum[i], value - query["center"][axis])
                    else:
                        accum[i] += (value - query["point"][axis]) * query["direction"][axis]
                    if not math.isfinite(accum[i]):
                        raise ValueError("Spatial predicate exceeds finite numeric range")
                packed = struct.pack("!d", value)
                whole.extend(packed)
                if i in node_indices:
                    rows[node_indices[i]].append(value)
                else:
                    unchanged.extend(packed)
            hashes["coordinates"].update(whole)
            hashes["unselected_coordinates"].update(unchanged)
    if query:
        for i, value in enumerate(accum):
            if query["kind"] == "box":
                chosen = (value == 0) == query["inside"]
            elif query["kind"] == "sphere":
                chosen = (value <= query["radius"]) == query["inside"]
            else:
                chosen = (abs(value) <= query["tolerance"] if query["side"] == "band" else
                          value > query["tolerance"] if query["side"] == "positive" else
                          value < -query["tolerance"])
            if chosen:
                matched.append(query_ids[i])
                if len(matched) > 20000:
                    raise ValueError("Spatial selection exceeds20000 selected nodes per operation; narrow the region. This is not a global model-size limit")
    element_count, affected_count, affected = 0, 0, []
    display_active_count, inactive_in_visible_parts = 0, 0
    visibility_path, visibility_buffer, visibility_hash = None, bytearray(), hashlib.sha256()
    if parameters.get("visibility_readback"):
        if output_directory is None:
            raise ValueError("Visibility binary requires an explicit job directory")
        visibility_path = os.path.join(output_directory, "visibility.bin")
        with open(visibility_path, "wb"):
            pass

    def flush_visibility():
        if visibility_buffer:
            with open(visibility_path, "ab") as stream:
                stream.write(visibility_buffer)
            visibility_hash.update(visibility_buffer)
            visibility_buffer.clear()
    normal_count = 0
    for label, kind in (("shell", dc.Type.SHELL), ("solid", dc.Type.SOLID), ("beam", dc.Type.BEAM)):
        # Materialize only domain IDs: a new SDK call may invalidate the array.
        # Coordinates/connectivity are never retained for unrequested entities.
        array = get("element_ids", type=kind)
        eids = [int(array[i]) for i in range(len(array))]
        hashes["connectivity"].update(label.encode("ascii") + struct.pack("!q", len(eids)))
        if normal_scope is not None:
            hashes["unselected_connectivity"].update(label.encode("ascii") + struct.pack("!q", len(eids)))
        for uid in eids:
            array = get("element_connectivity", type=kind, id=uid)
            conn = [int(array[i]) for i in range(len(array))]
            hashes["connectivity"].update(struct.pack("!qq", uid, len(conn)))
            hashes["connectivity"].update(struct.pack("!" + "q" * len(conn), *conn))
            if normal_scope is not None and label == "shell" and (normal_ids is None or uid in normal_ids):
                cycle = shell_orientation_cycle(conn)
                reversed_cycle = shell_orientation_cycle(list(reversed(cycle)))
                orientation_digest_update(hashes["normal_current"], uid, cycle)
                orientation_digest_update(hashes["normal_reversed"], uid, reversed_cycle)
                normal_count += 1
            elif normal_scope is not None:
                hashes["unselected_connectivity"].update(struct.pack("!qq", uid, len(conn)))
                hashes["unselected_connectivity"].update(struct.pack("!" + "q" * len(conn), *conn))
            element_count += 1
            if parameters.get("visibility_readback"):
                if element_count > 1000000:
                    raise ValueError("Visibility readback exceeds one million entities")
                display_active = int(bool(lp.check_if_element_is_active_u(uid, kind)))
                display_active_count += display_active
                if not display_active and uid in active_elements:
                    inactive_in_visible_parts += 1
                visibility_buffer.extend(struct.pack("!BqB", {"beam": 1, "shell": 2, "solid": 3}[label],
                                         uid, display_active))
                if len(visibility_buffer) >= 40960:
                    flush_visibility()
            if topology is not None and label == "shell" and lp.check_if_element_is_active_u(uid, kind):
                if len(topology_faces) >= 1000000:
                    raise ValueError("Topology reference exceeds one million visible shells")
                topology_faces[uid] = conn
            if registry_query:
                needs_unique = domain not in ("node", "part") or (domain == "node" and
                    (requested_parts is not None or registry_query["scope"] == "active_parts"))
                if needs_unique and uid in seen_elements:
                    raise ValueError("Part-aware selection requires globally unique element IDs")
                seen_elements.add(uid)
                if domain == "node":
                    if uid in filter_elements:
                        filter_ids.update(n for n in conn if n)
                    if uid in active_elements:
                        active_ids.update(n for n in conn if n)
                    if uid in filter_elements and uid in active_elements:
                        both_ids.update(n for n in conn if n)
                elif domain in (label, "element"):
                    domain_ids.add(uid)
                    if uid in filter_elements:
                        filter_ids.add(uid)
                    if uid in active_elements:
                        active_ids.add(uid)
            if wanted_nodes.intersection(conn):
                affected_count += 1
                if len(affected) < 20:
                    affected.append(dict(type=label, id=uid))
            if uid in wanted_ids and domain not in ("node", "part"):
                occurrences[uid] = occurrences.get(uid, 0) + 1
                if domain in (label, "element"):
                    matched.append(uid)
    if element_count + len(masses) != int(get("num_elements")):
        raise ValueError("Scoped verification does not cover this model's element types")
    if masses:
        hashes["connectivity"].update(b"mass" + struct.pack("!q", len(masses)))
        for uid in sorted(masses):
            nid, mass, pid = masses[uid]
            hashes["connectivity"].update(struct.pack("!qqd", uid, nid, mass))
            hashes["part_membership"].update(struct.pack("!qq", uid, pid))
            if registry_query and domain == "node":
                if uid in seen_elements:
                    raise ValueError("Part-aware selection requires globally unique element IDs")
                if uid in filter_elements:
                    filter_ids.add(nid)
                if uid in active_elements:
                    active_ids.add(nid)
                if uid in filter_elements and uid in active_elements:
                    both_ids.add(nid)
            if nid in wanted_nodes:
                affected_count += 1
                if len(affected) < 20:
                    affected.append(dict(type="mass", id=uid))
    flush_visibility()
    if normal_scope is not None and (normal_count == 0 or normal_ids is not None and normal_count != len(normal_ids)):
        raise ValueError("No shells or unknown explicit shell IDs for normal reversal")
    if any(n > 1 for n in occurrences.values()):
        raise ValueError("Requested element IDs are ambiguous across native domains")
    native_plan, selection_limit = None, 20000
    if topology is not None:
        needed = {uid for conn in topology_faces.values() for uid in conn if uid}
        array = get("node_ids")
        positions = {int(array[i]):i for i in range(len(array)) if int(array[i]) in needed}
        if set(positions) != needed:
            raise ValueError("Shell topology references missing nodes")
        coordinates = {uid:[] for uid in needed}
        for key in ("node_x", "node_y", "node_z"):
            array = get(key, type=dc.Type.NODE)
            for uid, index in positions.items():
                coordinates[uid].append(float(array[index]))
        try:
            matched = topology_shell_ids(topology_faces, coordinates, topology["seed_ids"], topology["mode"],
                                         topology["rings"], topology["feature_angle"])
        except ValueError as exc:
            topology_error = str(exc)
            matched = []
        native_plan = dict(strategy="topology", target="shell", **topology)
        selection_limit = 1000000
    if registry_query:
        if domain == "node" and (not filter_ids <= domain_ids or not active_ids <= domain_ids):
            raise ValueError("Part connectivity refers to an unregistered node")
        if domain == "part":
            domain_ids = set(parts)
            filter_ids = set(requested_parts or [])
            active_ids = {pid for pid in parts if visibility[str(pid)]}
        explicit = registry_query.get("entity_ids")
        if explicit is not None and not set(explicit) <= domain_ids:
            raise ValueError("Unknown selected entity IDs")
        candidates = set(explicit) if explicit is not None else filter_ids if requested_parts is not None else domain_ids
        eligible = domain_ids if registry_query["scope"] == "all" else active_ids
        selected_set = eligible - candidates if registry_query["invert"] else candidates & eligible
        target = "element" if domain in ("solid", "beam") else domain
        whole_domain = domain in ("node", "part", "shell", "element") or len(domain_ids) == element_count
        if selected_set and selected_set == domain_ids and whole_domain:
            native_plan = dict(strategy="whole", target=target)
        elif domain != "part" and explicit is None and not registry_query["invert"]:
            chosen_parts = parts if requested_parts is None else requested_parts
            if registry_query["scope"] == "active_parts":
                chosen_parts = [pid for pid in chosen_parts if visibility[str(pid)]]
            # Whole-scope node selection includes orphans, so only use part
            # commands when connectivity precisely defines the requested scope.
            if domain == "node":
                bulk_ids = (both_ids if requested_parts is not None and registry_query["scope"] == "active_parts" else
                            filter_ids if requested_parts is not None else active_ids)
            else:
                bulk_ids = (filter_elements & active_elements if requested_parts is not None and registry_query["scope"] == "active_parts" else
                            filter_elements if requested_parts is not None else active_elements if registry_query["scope"] == "active_parts" else seen_elements)
            if selected_set == bulk_ids and (domain != "node" or requested_parts is not None or registry_query["scope"] == "active_parts"):
                native_plan = dict(strategy="parts", target=target, part_ids=chosen_parts)
        selection_limit = 1000000 if native_plan else 20000
        if len(selected_set) > selection_limit:
            raise ValueError("Selected set exceeds the command/readback budget for this operation; this is not a global model-size limit")
        matched = sorted(selected_set)
    if not query and not registry_query and topology is None:
        if len(matched) != len(set(matched)) or (set(matched) != wanted_ids and parameters.get("allow_missing_entity_ids") is not True):
            raise ValueError("Requested IDs are absent or duplicated in the native entity registry")
    selection_count = int(get("num_selection"))
    selected = None
    if selection_count <= selection_limit:
        array = get("selection_ids", type=0)
        selected = [int(array[i]) for i in range(len(array))]
        if len(selected) != selection_count:
            raise ValueError("Native selection count differs from selected-ID readback")
    return dict(
        nodes=[rows[k] for k in sorted(rows)], elements=[],
        part_ids=parts, part_visibility=visibility, selection_ids=selected,
        registry_probe=parameters.get("allow_missing_entity_ids") is True,
        missing_entity_ids=sorted(wanted_ids - set(matched)),
        selection_types=None, registry_matches=matched,
        query_selected_ids=matched if query or registry_query or topology is not None else None,
        native_selection_plan=native_plan, selection_limit=selection_limit,
        topology_error=topology_error,
        affected_element_count=affected_count, affected_element_sample=affected,
        mesh_digest={key: value.hexdigest() for key, value in hashes.items()},
        digest_contract="native_registry_order_sha256_v1",
        digest_node_ids=sorted(wanted_nodes),
        normal_scope=normal_scope, normal_count=normal_count,
        auxiliary_elements=(dict(mass_count=len(masses), method="native_keyword_and_sdk_count",
                                 properties="element ID, node ID, mass, part ID", display_verified=False)
                            if masses else None),
        visibility_binary=(dict(format="native_display_active_v1", file="visibility.bin", record_format="!BqB",
                               count=element_count, active_count=display_active_count,
                               inactive_in_visible_parts=inactive_in_visible_parts,
                               byte_count=element_count*10, sha256=visibility_hash.hexdigest())
                           if visibility_path else None),
        verification_scope="All reference coordinates/connectivity/part membership streamed; only requested nodes materialized",
    )


def run(request_path, response_path):
    request = json.load(open(request_path, encoding="utf-8"))
    response = {"job_id": request["job_id"], "ok": False}
    try:
        import DataCenter as dc
        import LsPrePost as lp

        action = request["action"]
        p = request["parameters"]
        if action == "connectivity" and p.get("element_type") == "beam" and not request.get("safe_beam_connectivity"):
            raise RuntimeError("Native beam connectivity array binding failed heap-safety tests; use a protocol4 GUI session with native keyword readback")
        if action in ("extract_nodal", "node_history"):
            nv.require_vector_abi(sys.version_info)
        job_directory = request.get("job_directory", os.getcwd())
        if request.get("safe_beam_connectivity"):
            dc = BeamSafeDataCenter(dc, job_directory)
        if request.get("model"):
            # The application may reset cwd from GUI preferences. Load file families
            # from their parent, then restore the owned job cwd for every artifact.
            source = request["model"]
            os.chdir(os.path.dirname(source))
            try:
                kind = request["file_type"]
                load_name = (
                    source.replace("\\", "/")
                    if kind == "keyword" and request.get("absolute_keyword_path")
                    else os.path.basename(source)
                )
                lp.execute_command(nc.open_model(load_name, kind, openc=kind == "d3plot"))
            finally:
                os.chdir(job_directory)
            if int(dc.get_data("num_nodes")) <= 0 and request.get("expected_empty") is not True:
                raise ValueError("Input did not load a nonempty finite-element model")

        def get(key, **kw):
            return dc.get_data(key, **kw)

        def sequence(value):
            return [value[i] for i in range(len(value))]

        def inventory():
            data = {
                "python_version": sys.version,
                "python_executable": sys.executable,
                "python_prefix": sys.prefix,
                "warnings": [],
                "counts": {},
            }
            if isinstance(dc, BeamSafeDataCenter) and dc.beams:
                data["beam_connectivity_backend"] = "lsprepost_native_keyword_export"
                data["beam_connectivity_scope"] = "Standard ELEMENT_BEAM endpoints; fresh full keyword export per structural read, no array-binding call"
            aliases = {
                "nodes": ["num_nodes"],
                "elements": ["num_elements", "num_elem"],
                "states": ["num_states"],
            }
            for label, names in aliases.items():
                for key in names:
                    try:
                        data["counts"][label] = int(get(key))
                        break
                    except Exception:
                        pass
                else:
                    data["warnings"].append("Unavailable counter: " + label)
            try:
                data["part_ids"] = sequence(get("validpart_ids"))
            except Exception:
                data["part_ids"] = []
            try:
                data["state_times"] = sequence(get("state_times"))
            except Exception:
                data["state_times"] = []
            try:
                data["current_state"] = int(get("current_state"))
            except Exception:
                data["current_state"] = None
            try:
                data["model_directory"] = str(get("model_directory"))
            except Exception:
                data["model_directory"] = None
            return data

        def check_state(state):
            count = int(get("num_states"))
            if not 1 <= state <= count:
                raise ValueError("Native state must be 1..%s" % count)

        def node_rows(ids, keys, state):
            if state is not None:
                check_state(state)
                lp.switch_state(state)
            all_ids = sequence(get("node_ids"))
            lookup = {int(uid): i for i, uid in enumerate(all_ids)}
            missing = [uid for uid in ids if uid not in lookup]
            if missing:
                raise ValueError("Unknown user node IDs: " + str(missing[:20]))
            # Older bindings may expose application-owned buffers. Materialize
            # each component before the next native call can reuse its memory.
            arrays = [
                sequence(dc.get_data(key, dc.Type.NODE, **({"ist": state} if state else {}))) for key in keys
            ]
            if any(len(a) != len(all_ids) for a in arrays):
                raise ValueError("Node IDs and result array lengths differ")
            return [[uid] + [float(a[lookup[uid]]) for a in arrays] for uid in ids]

        if action in ("probe", "inspect_model"):
            data = inventory()
            if p.get("include_display_scope"):
                data["part_visibility"] = {str(int(pid)): bool(lp.check_if_part_is_active_u(int(pid))) for pid in data["part_ids"]}
                data["selection_count"] = int(get("num_selection"))
            if action == "probe":
                data["sdk_functions"] = [name for name in dir(lp) if not name.startswith("_")]
        elif action == "scl_probe":
            with open("scl_nodes.txt") as f:
                scl_nodes = int(f.read().strip())
            python_nodes = int(get("num_nodes"))
            if scl_nodes != python_nodes:
                raise ValueError("SCL and Python counters disagree")
            data = {"scl_nodes": scl_nodes, "python_nodes": python_nodes, "match": True}
        elif action == "gui_mesh_digest":
            data = inventory()
            data.update(scoped_mesh_state(dc, lp, p, job_directory))
        elif action == "gui_mesh_page":
            label, offset, limit = p["entity_type"], p["offset"], p["limit"]
            if label not in ("node", "shell", "solid", "beam"):
                raise ValueError("Unsupported mesh page entity_type")
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 5000:
                raise ValueError("Invalid mesh page bounds")
            data = inventory()
            kind = {"node": dc.Type.NODE, "shell": dc.Type.SHELL,
                    "solid": dc.Type.SOLID, "beam": dc.Type.BEAM}[label]
            registry = get("node_ids") if label == "node" else get("element_ids", type=kind)
            total = len(registry)
            end = min(total, offset + limit)
            selected = [int(registry[i]) for i in range(offset, end)]
            if label == "node":
                # Native coordinate arrays are whole-domain buffers, but only
                # the requested slice is materialized before another SDK call.
                arrays = []
                for key in ("node_x", "node_y", "node_z"):
                    values = get(key, type=kind)
                    if len(values) != total:
                        raise ValueError("Native node coordinate length differs from registry")
                    arrays.append([float(values[i]) for i in range(offset, end)])
                rows = [[uid] + [a[i] for a in arrays] for i, uid in enumerate(selected)]
                data["nodes"] = rows
            else:
                data["elements"] = [
                    {"type": label, "id": uid,
                     "nodes": [int(n) for n in sequence(get("element_connectivity", type=kind, id=uid))]}
                    for uid in selected
                ]
            data.update(entity_type=label, offset=offset, limit=limit, total=total,
                        returned=len(selected), next_offset=end if end < total else None,
                        id_kind="user", coordinate_configuration="reference",
                        snapshot_scope="one locked native request; no cross-page atomicity")
        elif action == "gui_mesh_state":
            data = inventory()
            if max(data["counts"].get("nodes", 0), data["counts"].get("elements", 0)) > 20000:
                raise ValueError("GUI mesh verification currently supports at most 20000 nodes/elements")
            node_ids = [int(x) for x in sequence(get("node_ids"))]
            data["nodes"] = node_rows(node_ids, ["node_x", "node_y", "node_z"], None)
            elements = []
            for label, kind in [("shell", dc.Type.SHELL), ("solid", dc.Type.SOLID), ("beam", dc.Type.BEAM)]:
                for eid in sequence(get("element_ids", type=kind)):
                    elements.append({"type": label, "id": int(eid),
                                     "nodes": [int(n) for n in sequence(get("element_connectivity", type=kind, id=int(eid)))]})
            if len(elements) != data["counts"].get("elements"):
                raise ValueError("GUI mesh snapshot does not cover this model's element types")
            data["elements"] = elements
            data["part_elements"] = {str(int(pid)): [int(eid) for eid in sequence(get("elemofpart_ids", type=1, id=int(pid)))] for pid in data["part_ids"]}
            data["part_visibility"] = {str(int(pid)): bool(lp.check_if_part_is_active_u(int(pid))) for pid in data["part_ids"]}
            try:
                data["selection_ids"] = [int(x) for x in sequence(get("selection_ids", type=0))]
                # This binding returned invalid pointer-like integers for the
                # selection_types array in a real 4.13 GUI check. Do not expose
                # those values as verified entity type codes.
                data["selection_types"] = None
            except Exception:
                data["selection_ids"] = None
                data["selection_types"] = None
        elif action == "list_nodes":
            ids = sequence(get("node_ids"))
            selected = [int(x) for x in ids[p["offset"] : p["offset"] + p["limit"]]]
            rows = node_rows(selected, ["node_x", "node_y", "node_z"], None)
            data = {
                "total": len(ids),
                "coordinate_configuration": "reference",
                "columns": ["node_id", "x", "y", "z"],
                "rows": rows,
            }
        elif action == "list_parts":
            ids = sequence(get("validpart_ids"))
            parts = []
            for uid in ids[: p["limit"]]:
                item = {"part_id": int(uid)}
                try:
                    item["name"] = str(get("part_name", id=int(uid)))
                except Exception:
                    item["name"] = None
                parts.append(item)
            data = {"total": len(ids), "parts": parts}
        elif action == "connectivity":
            kind = {"shell": dc.Type.SHELL, "solid": dc.Type.SOLID, "beam": dc.Type.BEAM}[p["element_type"]]
            nodes = sequence(get("element_connectivity", type=kind, id=p["element_id"]))
            if not nodes:
                raise ValueError("No connectivity returned for the requested element")
            data = {
                "element_id": p["element_id"],
                "element_type": p["element_type"],
                "node_ids": nodes,
                "id_kind": "user",
            }
        elif action in ("extract_nodal", "node_history"):
            mapping = {
                "displacement": ["disp_x", "disp_y", "disp_z"],
                "velocity": ["velo_x", "velo_y", "velo_z"],
                "position": ["state_node_x", "state_node_y", "state_node_z"],
            }
            keys = mapping[p["quantity"]]
            states = [p["state"]] if action == "extract_nodal" else p["states"]
            times = sequence(get("state_times"))
            rows = []
            if p.get("preserve_state"):
                lp.execute_command(nc.animation('stop'))
            initial_state = int(get("current_state")) if p.get("preserve_state") else None
            if initial_state is not None:
                check_state(initial_state)
            try:
                for state in states:
                    check_state(state)
                    if state > len(times):
                        raise ValueError("Missing physical state time")
                    for row in node_rows(p["node_ids"], keys, state):
                        rows.append([state, float(times[state - 1])] + row)
            finally:
                if initial_state is not None:
                    lp.switch_state(initial_state)
            if p["quantity"] != "position":
                for row in rows:
                    row.append(math.sqrt(sum(v * v for v in row[-3:])))
            columns = ["state", "time", "node_id", "x", "y", "z"]
            if p["quantity"] != "position":
                columns.append("magnitude")
            if any(not math.isfinite(float(v)) for row in rows for v in row):
                raise ValueError("Nonfinite native nodal result/time")
            components = p.get("curve_components", [])
            if components:
                selected_times = [float(times[state - 1]) for state in states]
                if len(selected_times) < 2 or any(a >= b for a, b in zip(selected_times, selected_times[1:])):
                    raise ValueError("Scalar curves require strictly increasing physical time")
            with open(os.path.join(job_directory, "nodal.csv"), "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)
            curves = []
            for uid in (p["node_ids"] if components else []):
                samples = [row for row in rows if row[2] == uid]
                for component in components:
                    filename = "node_%d_%s.csv" % (uid, component)
                    column = columns.index(component)
                    with open(os.path.join(job_directory, filename), "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(["time", "value"])
                        writer.writerows([[row[1], row[column]] for row in samples])
                    curves.append({"node_id": uid, "component": component,
                                   "quantity": p["quantity"], "units": p["units"],
                                   "time_unit": p.get("time_unit"), "row_count": len(samples),
                                   "path": os.path.join(job_directory, filename)})
            data = {
                "quantity": p["quantity"],
                "columns": columns,
                "row_count": len(rows),
                "states": states,
                "units": p["units"],
                "id_kind": "user",
                "preview": rows[:20],
                "field_spec": p.get("field_spec"),
                "curves": curves,
                "original_state": initial_state,
                "state_restore_requested": initial_state is not None,
                "state_restored": False,
                "animation_policy": "stopped; not automatically resumed" if initial_state is not None else "unchanged",
            }
        elif action == "create_plate":
            nx, ny = p["nx"], p["ny"]
            ox, oy, oz = p["origin"]
            lx, ly = p["size"]
            coords = [ox, oy, oz, ox + lx, oy, oz, ox + lx, oy + ly, oz, ox, oy + ly, oz]
            lp.execute_command("meshing 4pshell create %d %d " % (nx, ny) + " ".join(str(x) for x in coords))
            lp.execute_command(
                "meshing 4pshell accept %d %d %d plate" % (p["part_id"], p["element_start"], p["node_start"])
            )
            data = inventory()
            if (
                data["counts"].get("nodes") != (nx + 1) * (ny + 1)
                or data["counts"].get("elements") != nx * ny
            ):
                raise ValueError("Native mesh counts do not match the requested plate")
            data["units"] = p["units"]
        elif action == "create_box":
            nx, ny, nz = p["divisions"]
            lower = p["origin"]
            upper = [lower[i] + p["size"][i] for i in range(3)]
            lp.execute_command(
                "meshing boxsolid create "
                + " ".join(str(v) for v in lower + upper)
                + " %d %d %d 0.0" % (nx, ny, nz)
            )
            lp.execute_command(
                "meshing boxsolid accept %d %d %d boxsolid"
                % (p["part_id"], p["element_start"], p["node_start"])
            )
            data = inventory()
            if (
                data["counts"].get("nodes") != (nx + 1) * (ny + 1) * (nz + 1)
                or int(get("num_solid_elements")) != nx * ny * nz
            ):
                raise ValueError("Native box mesh counts differ from requested divisions")
            data["units"] = p["units"]
        elif action == "create_sphere":
            try:
                before = set(int(v) for v in sequence(get("node_ids")))
                old_parts = set(int(v) for v in sequence(get("validpart_ids")))
            except Exception:
                before, old_parts = set(), set()
            if p["part_id"] in old_parts:
                raise ValueError("Sphere part ID already exists")
            lp.execute_command(
                "meshing spheresolid create "
                + " ".join(str(v) for v in p["center"])
                + " %s %d 1 0 0 0 1 0" % (p["radius"], p["divisions"])
            )
            lp.execute_command("meshing spheresolid accept %d" % p["part_id"])
            ids = [int(v) for v in sequence(get("node_ids"))]
            created = [v for v in ids if v not in before]
            if not created or len(ids) != len(set(ids)):
                raise ValueError("Sphere did not create a unique node registry")
            rows = node_rows(created, ["node_x", "node_y", "node_z"], None)
            radii = [math.sqrt(sum((row[i + 1] - p["center"][i]) ** 2 for i in range(3))) for row in rows]
            if abs(max(radii) - p["radius"]) > max(1e-6, p["radius"] * 1e-5):
                raise ValueError("Sphere mesh extent differs from requested radius")
            data = inventory()
            data.update(created_node_count=len(created), maximum_radius=max(radii), units=p["units"])
        elif action == "rotate_nodes":
            ids = [int(v) for v in sequence(get("node_ids"))]
            selected = set(p["node_ids"])
            if not selected.issubset(set(ids)):
                raise ValueError("Unknown node ID")
            before = node_rows(ids, ["node_x", "node_y", "node_z"], None)
            lp.execute_command(nc.selection('clear'))
            lp.execute_command(nc.selection_target('node'))
            lp.execute_command(nc.selection_transfer(0))
            for uid in p["node_ids"]:
                lp.execute_command(nc.selection_add('node', uid, 'node'))
            lp.execute_command(
                "rotate_model " + " ".join(str(v) for v in p["center"]) + " %s %s" % (p["axis"], p["angle"])
            )
            lp.execute_command("rotate_model accept 0 0 0")
            lp.execute_command(nc.selection('clear'))
            after = node_rows(ids, ["node_x", "node_y", "node_z"], None)
            angle = math.radians(p["angle"])
            cos, sin = math.cos(angle), math.sin(angle)
            axis = {"x": 0, "y": 1, "z": 2}[p["axis"]]
            a, b = (axis + 1) % 3, (axis + 2) % 3
            max_error = 0.0
            for old, new in zip(before, after):
                expected = old[1:]
                if old[0] in selected:
                    qa, qb = expected[a] - p["center"][a], expected[b] - p["center"][b]
                    expected[a] = p["center"][a] + cos * qa - sin * qb
                    expected[b] = p["center"][b] + sin * qa + cos * qb
                for i in range(3):
                    error = abs(new[i + 1] - expected[i])
                    max_error = max(max_error, error)
                    if error > max(1e-6, abs(expected[i]) * 1e-5):
                        raise ValueError("Native rotation coordinate verification failed")
            data = {
                "rotated_nodes": len(selected),
                "axis": p["axis"],
                "angle_degrees": p["angle"],
                "maximum_coordinate_error": max_error,
            }
        elif action == "translate_nodes":
            all_ids = [int(v) for v in sequence(get("node_ids"))]
            if len(all_ids) > 1000000:
                raise ValueError("Translation verification is limited to one million nodes")
            selected = set(p["node_ids"])
            if not selected.issubset(set(all_ids)):
                raise ValueError("Requested user node ID does not exist")
            before = node_rows(all_ids, ["node_x", "node_y", "node_z"], None)
            lp.execute_command(nc.selection('clear'))
            lp.execute_command(nc.selection_target('node'))
            for uid in p["node_ids"]:
                lp.execute_command(nc.selection_add('node', uid, 'node'))
            lp.execute_command("translate_model " + " ".join(str(v) for v in p["offset"]))
            lp.execute_command("translate_model accept")
            lp.execute_command(nc.selection('clear'))
            after_ids = [int(v) for v in sequence(get("node_ids"))]
            if after_ids != all_ids:
                raise ValueError("Translation unexpectedly changed the node ID registry")
            after = node_rows(all_ids, ["node_x", "node_y", "node_z"], None)
            max_error = 0.0
            for old, new in zip(before, after):
                expected = [old[i + 1] + (p["offset"][i] if old[0] in selected else 0) for i in range(3)]
                for i in range(3):
                    error = abs(new[i + 1] - expected[i])
                    max_error = max(max_error, error)
                    if error > max(1e-7, abs(expected[i]) * 1e-6):
                        raise ValueError("Native translation changed an unexpected coordinate")
            data = {
                "translated_nodes": len(selected),
                "verified_nodes": len(all_ids),
                "max_coordinate_error": max_error,
                "units": p["units"],
                "verification": "All selected and unselected coordinates checked before save",
            }
        elif action == "move_elements_to_part":
            kind = {"shell": dc.Type.SHELL, "solid": dc.Type.SOLID, "beam": dc.Type.BEAM}[p["element_type"]]
            before_ids = [int(v) for v in sequence(get("element_ids", type=kind))]
            if not set(p["element_ids"]).issubset(set(before_ids)):
                raise ValueError("Requested user element ID not found")
            for other_kind in (dc.Type.SHELL, dc.Type.SOLID, dc.Type.BEAM):
                if other_kind != kind:
                    other_ids = set(int(v) for v in sequence(get("element_ids", type=other_kind)))
                    if set(p["element_ids"]) & other_ids:
                        raise ValueError(
                            "Generic native selector is ambiguous: selected ID also occurs in another element type"
                        )
            before_nodes = int(get("num_nodes"))
            before_elements = int(get("num_elements"))
            lp.execute_command(nc.selection('clear'))
            lp.execute_command(nc.selection_target('element'))
            for uid in p["element_ids"]:
                lp.execute_command(nc.selection_add('element', uid, 'element'))
            lp.execute_command('elemmove apply %d "mcp_part"' % p["part_id"])
            lp.execute_command("elemmove accept %d" % p["part_id"])
            lp.execute_command(nc.selection('clear'))
            moved = set(int(v) for v in sequence(get("elemofpart_ids", type=1, id=p["part_id"])))
            if not set(p["element_ids"]).issubset(moved):
                raise ValueError("Native target part does not contain requested element IDs")
            if int(get("num_nodes")) != before_nodes or int(get("num_elements")) != before_elements:
                raise ValueError("Part reassignment changed mesh counts")
            data = {
                "element_type": p["element_type"],
                "element_ids": p["element_ids"],
                "part_id": p["part_id"],
                "verification": "Target part membership and mesh counts checked; target material/section requires explicit configuration",
            }
        elif action == "extrude_shell":
            part_ids = [int(v) for v in sequence(get("validpart_ids"))]
            shell_count = int(get("num_shell_elements"))
            if part_ids != [p["part_id"]] or shell_count != int(get("num_elements")):
                raise ValueError("Initial extrusion adapter requires a single shell-only part")
            if shell_count * p["layers"] > 100000:
                raise ValueError("Extrusion exceeds 100000 solid elements")
            before_shells = [int(v) for v in sequence(get("element_ids", type=dc.Type.SHELL))]
            z = [float(v) for v in sequence(get("node_z"))]
            if max(z) - min(z) > 1e-8:
                raise ValueError("Initial extrusion adapter requires a planar XY shell mesh")
            lp.execute_command(nc.selection('clear'))
            lp.execute_command(nc.selection_target('shell'))
            lp.execute_command(nc.selection_add('shell', p['part_id'], 'part'))
            lp.execute_command(
                "elgenerate solid shelldrag 2 0 %s %d 0 0 0 0 0 10000" % (p["length"], p["layers"])
            )
            lp.execute_command(nc.selection('clear'))
            lp.execute_command("elgenerate accept")
            data = inventory()
            data["solid_count"] = int(get("num_solid_elements"))
            solid_ids = [int(v) for v in sequence(get("element_ids", type=dc.Type.SOLID))]
            if len(solid_ids) != len(set(solid_ids)) or before_shells != [
                int(v) for v in sequence(get("element_ids", type=dc.Type.SHELL))
            ]:
                raise ValueError("Extrusion changed source shell IDs or produced duplicate solid IDs")
            if data["solid_count"] != shell_count * p["layers"]:
                raise ValueError("Extrusion did not create expected number of solids")
            after_z = [float(v) for v in sequence(get("node_z"))]
            if abs((max(after_z) - min(after_z)) - p["length"]) > max(1e-6, p["length"] * 1e-6):
                raise ValueError("Extrusion extent does not match requested length")
            data.update(units=p["units"], source_shells_retained=True, z_extent=max(after_z) - min(after_z))
        elif action == "gui_new":
            with open("initial.k", "w") as f:
                f.write("*KEYWORD\n*TITLE\nMCP session model\n*END\n")
            lp.execute_command(
                nc.open_model(os.path.join(job_directory, "initial.k"))
            )
            data = inventory()
        elif action == "gui_display":
            if p.get("state") is not None:
                check_state(p["state"])
                lp.execute_command(nc.animation('stop'))
                lp.switch_state(p["state"])
            for command in p["commands"]:
                lp.execute_command(command)
            if p.get("capture"):
                output = os.path.join(job_directory, "snapshot.png").replace("\\", "/")
                lp.execute_command(nc.print_png(output))
            data = inventory()
            data["applied_commands"] = p["commands"]
        elif action == "gui_parts":
            valid = [int(v) for v in sequence(get("validpart_ids"))]
            if not set(p["part_ids"]).issubset(set(valid)):
                raise ValueError("Unknown part IDs")
            before = {uid: bool(lp.check_if_part_is_active_u(uid)) for uid in valid}
            if p["mode"] == "all":
                lp.execute_command("pall")
            elif p["mode"] == "isolate":
                lp.execute_command("m " + ",".join(str(v) for v in p["part_ids"]))
            else:
                prefix = "+m " if p["mode"] == "show" else "-m "
                for uid in p["part_ids"]:
                    lp.execute_command(prefix + str(uid))
            after = {uid: bool(lp.check_if_part_is_active_u(uid)) for uid in valid}
            expected = dict(before)
            if p["mode"] in ("all", "isolate"):
                expected = {uid: (p["mode"] == "all" or uid in p["part_ids"]) for uid in valid}
            else:
                for uid in p["part_ids"]:
                    expected[uid] = p["mode"] == "show"
            if after != expected:
                raise ValueError("Native part visibility did not match requested state")
            data = {"visibility": after, "mode": p["mode"], "verified": True}
        elif action == "gui_animation":
            if p["operation"] == "stop":
                lp.execute_command(nc.animation('stop'))
            else:
                check_state(p["first"])
                check_state(p["last"])
                lp.execute_command(nc.animation('first', p['first']))
                lp.execute_command(nc.animation('last', p['last']))
                lp.execute_command(nc.animation('incr', p['increment']))
                lp.execute_command(nc.animation(p['direction']))
                lp.execute_command(nc.animation('start'))
            data = {
                "operation": p["operation"],
                "configuration": p,
                "verification": "Native commands submitted; use current_state/captured frames to observe playback",
            }
        elif action == "render_snapshot":
            averaging = p.get("averaging", "minmax")
            if averaging not in ("minmax", "nodal", "none"):
                raise ValueError("Unsupported display averaging")
            if p.get("state") is not None:
                check_state(p["state"])
                lp.switch_state(p["state"])
            if p.get("fringe_code") is not None:
                lp.execute_command(nc.fringe(p['fringe_code']))
                lp.execute_command(nc.plot_fringe())
            lp.execute_command(nc.averaging(averaging))
            lp.execute_command(p["view"])
            lp.execute_command("ac")
            output = os.path.join(job_directory, "snapshot.png").replace("\\", "/")
            lp.execute_command(nc.print_png(output))
            data = {
                "view": p["view"],
                "state": p.get("state"),
                "fringe_code": p.get("fringe_code"),
                "display_averaging": averaging,
                "title_policy": "Preserve model title and native result names",
                "note": "Image validation does not establish physical result correctness",
            }
        elif action == "export_keyword":
            data = inventory()
        elif action == "raw_command":
            lp.execute_command(p["command"])
            os.chdir(job_directory)
            data = inventory()
            for key, expected in p["expected_counts"].items():
                if data["counts"].get(key) != expected:
                    raise ValueError("Raw command count verification failed: " + key)
            data["command"] = p["command"]
            data["verification_scope"] = "Inventory and declared outputs only; raw command semantics are user-defined"
        elif action == "gui_measure":
            response["query_started"] = False
            mode = p["measurement"]
            uids = p["node_ids"]
            state = p.get("state")
            data = inventory()
            keys = ["node_x", "node_y", "node_z"] if state is None else ["state_node_x", "state_node_y", "state_node_z"]
            positions = node_rows(uids, keys, state)
            if any(not math.isfinite(v) for row in positions for v in row[1:]):
                raise ValueError("Nonfinite native measurement coordinates")
            if mode in ("distance", "height", "angle3", "angle4", "circle3"):
                pairs = [(0, 1)] if mode in ("distance", "height") else [(0, 1), (1, 2)] if mode in ("angle3", "circle3") else [(0, 1), (2, 3)]
                for a, b in pairs:
                    if positions[a][1:] == positions[b][1:]:
                        raise ValueError("Native coordinate precision cannot resolve a required segment")
                if mode == "circle3":
                    a = [positions[1][j] - positions[0][j] for j in (1, 2, 3)]
                    b = [positions[2][j] - positions[0][j] for j in (1, 2, 3)]
                    cross = [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
                    if sum(v*v for v in cross) <= 1e-20 * sum(v*v for v in a) * sum(v*v for v in b):
                        raise ValueError("Three-point circle requires noncollinear native coordinates")
            commands = ["measure axes set 0", "measure scalefactor 1"]
            response["query_started"] = True
            if mode == "coordinates":
                queries = ["ident node %d" % uid for uid in uids]
            else:
                token = {"distance": "dist", "height": "dist", "angle3": "angle3", "angle4": "angle4", "circle3": "3pt-radius"}[mode]
                queries = ["measure " + token + " " + " ".join("N%d" % uid for uid in uids)]
            for command in commands:
                lp.execute_command(command)
            values = []
            for command in queries:
                lp.execute_command(command)
                raw = [lp.cmd_result_get_value(i) for i in range(lp.cmd_result_get_value_count())]
                if not raw or any(type(v) not in (int, float) or not math.isfinite(v) for v in raw):
                    raise ValueError("Native measurement returned no finite numeric result")
                values.append(raw)
            data.update(measurement=mode, node_positions=positions, native_values=values,
                        native_commands=commands+queries, axes_requested=0, scale_requested=1,
                        native_model_context="active model, unqualified node tokens", coordinate_configuration="reference" if state is None else "current_state")
        elif action == "measure_parts":
            valid = set(int(x) for x in sequence(get("validpart_ids")))
            if not set(p["part_ids"]).issubset(valid):
                raise ValueError("Unknown user part ID")
            rows = []
            for uid in p["part_ids"]:
                lp.execute_command("measure vol part %d" % uid)
                values = [lp.cmd_result_get_value(i) for i in range(lp.cmd_result_get_value_count())]
                if not values:
                    raise ValueError("Native measurement returned no values")
                rows.append({"part_id": uid, "command_values": values})
            data = {
                "measurements": rows,
                "note": "Raw command-result layout is build-dependent; values are not assigned guessed units",
            }
        else:
            raise ValueError("Unsupported bridge action: " + action)
        response.update(ok=True, data=data)
    except Exception as exc:
        response.update(
            error={"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        )
    with open(response_path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(response, f, ensure_ascii=False, indent=2, allow_nan=False)
    os.replace(response_path + ".tmp", response_path)
