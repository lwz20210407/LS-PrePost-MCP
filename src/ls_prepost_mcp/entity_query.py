"""G04 identification over the shared keyword and result readers; no sibling guessing."""

from __future__ import annotations

import hashlib
import re

import numpy as np

from .core.contracts import CheckResult, JobResult, Selector
from .core.validation import unit_label
from .domain.model import KeywordDeck, geometry
from .domain.model.operations import inspect_loaded_deck
from .domain.model.selectors import resolve
from .domain.results import lasso_backend as lb
from .jobs import atomic_json
from .post_backend import selected_database

FAMILIES = {"solid": ("*ELEMENT_SOLID", 8), "shell": ("*ELEMENT_SHELL", 4)}


def _sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _uid(value):
    return (
        int(value)
        if isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)) and value > 0
        else None
    )


def _binary_tables(arrays, node_ids, parts):
    tables = {}
    for family, (_, width) in FAMILIES.items():
        ids = np.asarray(arrays.get(f"element_{family}_ids", np.empty(0, dtype=np.int64)))
        if not ids.size:
            tables[family] = (ids, np.empty(0, dtype=np.int64), np.empty((0, width), dtype=np.int64))
            continue
        lb._index(ids, [], family)
        conn = np.asarray(arrays[f"element_{family}_node_indexes"])
        owners = np.asarray(arrays[f"element_{family}_part_indexes"])
        if (
            conn.shape != (ids.size, width)
            or conn.dtype.kind not in "iu"
            or np.any(conn < 0)
            or np.any(conn >= node_ids.size)
            or owners.shape != ids.shape
            or owners.dtype.kind not in "iu"
            or np.any(owners < 0)
            or np.any(owners >= parts.size)
        ):
            raise ValueError("Result connectivity/Part-index axis cannot be matched to stored user IDs")
        tables[family] = (ids, parts[owners], node_ids[conn])
    return tables


def _material(pid, definitions, warnings):
    row = definitions.get(pid, {})
    mid = _uid(row.get("mid"))
    if mid is None:
        warnings.add(
            "Material user IDs are unavailable for one or more identified Parts; no numeric fallback was used"
        )
    return mid, _uid(row.get("secid"))


def _describe(kind, selected, node_ids, xyz, tables, parts, definitions, warnings):
    lookup = geometry._index(node_ids)
    entities = []
    for uid in selected:
        uid = int(uid)
        row = {"entity_id": uid, "entity_type": kind}
        if kind == "node":
            row["coordinates"] = xyz[lookup[np.asarray(uid)]].tolist()
            owners = set()
            for _, pids, conn in tables.values():
                owners.update(int(p) for p in pids[(conn == uid).any(axis=1)])
            row["part_ids"] = sorted(owners)
            mids = [_material(p, definitions, warnings)[0] for p in sorted(owners)]
            row["material_ids"] = (
                sorted({mid for mid in mids if mid is not None}) if all(m is not None for m in mids) else None
            )
        elif kind in FAMILIES:
            ids, pids, conn = tables[kind]
            index = int(lb._index(ids, [uid], kind)[0])
            nodes = conn[index]
            if np.any(nodes <= 0) or np.any(nodes >= lookup.size) or np.any(lookup[nodes] < 0):
                raise ValueError("Element references a missing user node ID")
            pid = int(pids[index])
            mid, sid = _material(pid, definitions, warnings)
            row.update(
                part_id=pid,
                material_id=mid,
                section_id=sid,
                node_ids=nodes.tolist(),
                node_coordinates=xyz[lookup[nodes]].tolist(),
            )
        else:
            mid, sid = _material(uid, definitions, warnings)
            used = []
            counts = {}
            for family, (_, pids, conn) in tables.items():
                chosen = conn[pids == uid]
                counts[family] = int(chosen.shape[0])
                used.extend(chosen.reshape(-1).tolist())
            used = np.unique(used).astype(np.int64)
            if used.size and (np.any(used <= 0) or np.any(used >= lookup.size) or np.any(lookup[used] < 0)):
                raise ValueError("Part references missing geometry nodes")
            bbox = (
                [xyz[lookup[used]].min(axis=0).tolist(), xyz[lookup[used]].max(axis=0).tolist()]
                if used.size
                else None
            )
            row.update(
                material_id=mid, section_id=sid, node_count=int(used.size), element_counts=counts, bounds=bbox
            )
        entities.append(row)
    return entities


def query_entities(service, path, selector, source_kind, state, quantity, units):
    chosen = selector if isinstance(selector, Selector) else Selector.model_validate(selector)
    kind = chosen.entity_type
    if kind not in ("node", "solid", "shell", "part"):
        raise ValueError("Identify currently supports node, solid, shell and Part")
    if state is not None and (type(state) is not int or state < 1):
        raise ValueError("state must be a positive 1-based state number")
    if chosen.state is not None:
        if state is not None and state != chosen.state:
            raise ValueError("Selector deformed state and result state must agree")
        state = chosen.state
    if quantity is not None:
        if (
            not isinstance(quantity, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", quantity)
            or state is None
        ):
            raise ValueError("A named result quantity requires an explicit state")
        units = unit_label(units)
    if source_kind not in ("keyword", "d3plot"):
        raise ValueError("Unknown entity-query source_kind")
    if source_kind == "keyword" and (state is not None or quantity is not None):
        raise ValueError("Keyword identity has reference geometry only; state results require d3plot")
    source = service.settings.input_path(path)
    directory, manifest = service.jobs.create(
        "query_entities",
        dict(
            path=str(source),
            selector=chosen.model_dump(mode="json"),
            source_kind=source_kind,
            state=state,
            quantity=quantity,
            units=units,
        ),
    )
    data = {}
    try:
        warnings = set()
        with service._guard():
            if source_kind == "keyword":
                service.settings.native_keyword_report(source)
                deck = KeywordDeck.load(source)
                if any(
                    r.block.name not in ("*INCLUDE", "*INCLUDE_PATH", "*INCLUDE_PATH_RELATIVE")
                    for r in deck.includes
                ):
                    raise ValueError(
                        "Transformed/opaque Include coordinates are not certified for entity identity"
                    )
                if not deck.summary()["keyword_blocks"]:
                    raise ValueError("Input has no readable keyword blocks")
                files = [f.path for f in deck.files.values()]
                before = {str(f.path): hashlib.sha256(f.original).hexdigest() for f in deck.files.values()}
                info = inspect_loaded_deck(deck)
                node_ids, xyz = geometry.nodes(deck)
                tables = {f: geometry.elements(deck, key, width) for f, (key, width) in FAMILIES.items()}
                definitions = {int(row["pid"]): row for row in info["parts"]}
                if len(definitions) != len(info["parts"]):
                    raise ValueError("Duplicate Part IDs cannot be identified unambiguously")
                parts = np.asarray(sorted(definitions), dtype=np.int64)
                selected = resolve(deck, chosen)
                warnings.update(deck.warnings)
                if any(
                    not (name.startswith("*ELEMENT_SOLID") or name.startswith("*ELEMENT_SHELL"))
                    for name in info["elements"]
                ):
                    warnings.add("Ownership/bounds cover supported solid/shell connectivity only")
                arrays = None
            else:
                files = service._result_family(str(source))
                before = {str(p): _sha(p) for p in files}
                if chosen.predicate.kind != "ids":
                    raise ValueError(
                        "Result identification currently requires explicit ID predicates; other predicates belong to G03"
                    )
                if chosen.validity != "all" and (kind not in FAMILIES or state is None):
                    raise ValueError("Physical validity needs an element family and explicit state")
                if state is not None:
                    keys = ["node_displacement"]
                    if kind == "node" and quantity is not None and quantity.startswith("velocity_"):
                        keys.append("node_velocity")
                    if kind == "part" and quantity is not None:
                        keys.append(f"part_{quantity}")
                    if kind in FAMILIES:
                        keys.append(lb.FAMILIES[kind][1])
                        if quantity is not None:
                            keys.append(
                                lb.FAMILIES[kind][5]
                                if quantity == "effective_plastic_strain"
                                else lb.FAMILIES[kind][4]
                            )
                    db, _ = selected_database(source, [state], keys)
                    arrays = {str(getattr(k, "value", k)): v for k, v in db.arrays.items()}
                else:
                    arrays = lb._arrays(source, state_arrays=["timesteps"])
                node_ids = np.asarray(arrays["node_ids"])
                lb._index(node_ids, [], "Node")
                xyz = np.asarray(arrays["node_coordinates"], dtype=float)
                if chosen.configuration == "deformed":
                    if "node_displacement" not in arrays:
                        raise ValueError(
                            "No stored deformed node coordinates; reference fallback is not allowed"
                        )
                    xyz = np.asarray(arrays["node_displacement"][0], dtype=float)
                parts = lb._part_ids(arrays)
                lb._index(parts, [], "Part")
                tables = _binary_tables(arrays, node_ids, parts)
                universe = node_ids if kind == "node" else parts if kind == "part" else tables[kind][0]
                requested = list(chosen.predicate.ids)
                lb._index(universe, requested, kind)
                selected = np.asarray(sorted(requested), dtype=np.int64)
                if chosen.validity != "all":
                    key = lb.FAMILIES[kind][1]
                    if key not in arrays:
                        raise ValueError("No stored deletion flags; validity cannot be inferred")
                    positions = lb._index(universe, selected.tolist(), kind)
                    flags = np.asarray(arrays[key])
                    if flags.shape != (1, universe.size) or not np.isfinite(flags).all():
                        raise ValueError(
                            "Stored deletion flags are invalid or cannot be aligned with geometry IDs"
                        )
                    alive = flags[0, positions] != 0
                    selected = selected[alive if chosen.validity == "alive" else ~alive]
                definitions = {}
                warnings.add(
                    "d3plot does not identify keyword material/section user IDs; no neighboring model was loaded"
                )
            if selected.size > 1000:
                raise ValueError("Identify is limited to 1000 selected entities; narrow the Selector")
            lb._index(node_ids, [], "Node")
            universe = node_ids if kind == "node" else parts if kind == "part" else tables[kind][0]
            lb._index(universe, selected.tolist(), kind)
            if xyz.shape != (node_ids.size, 3) or not np.isfinite(xyz).all():
                raise ValueError("Node coordinates must be finite and aligned with stored user IDs")
            rows = _describe(kind, selected, node_ids, xyz, tables, parts, definitions, warnings)
            if quantity is not None and selected.size:
                if kind in FAMILIES:
                    key = (
                        lb.FAMILIES[kind][4]
                        if quantity != "effective_plastic_strain"
                        else lb.FAMILIES[kind][5]
                    )
                    if key not in arrays or np.asarray(arrays[key]).shape[1] != tables[kind][0].size:
                        raise ValueError(
                            "Result field axis cannot be matched to all geometry IDs; rigid/omitted rows need an explicit adapter"
                        )
                records = lb._history_from_arrays(arrays, kind, quantity, selected.tolist())
                values = {int(r["entity"]): r for r in records}
                for row in rows:
                    result = values[row["entity_id"]]
                    value = float(result["values"][0])
                    if not np.isfinite(value):
                        raise ValueError("Identified result is undefined/nonfinite")
                    row["result"] = {
                        "quantity": quantity,
                        "value": value,
                        "state": state,
                        "time": float(result["time"][0]),
                        "units": units,
                        "backend": lb.backend(),
                        "sampling": result.get("note", "as stored"),
                    }
            after = {str(p): _sha(p) for p in files}
            if before != after:
                raise ValueError("Entity source files changed during identification")
        manifest["inputs"] = [{"path": p, "sha256": sha} for p, sha in before.items()]
        data = {
            "entities": rows,
            "count": len(rows),
            "entity_type": kind,
            "source_kind": source_kind,
            "configuration": chosen.configuration,
            "validity": chosen.validity,
            "state": state,
            "result_units": units,
            "coordinate_units": "as stored; model length unit not inferred",
            "selection_order": "sorted user IDs",
            "read_only": True,
            "material_scope": "keyword Part links"
            if source_kind == "keyword"
            else "unknown keyword user IDs",
        }
        checks = [
            CheckResult(name="input_bytes_unchanged", status="passed"),
            CheckResult(name="requested_properties", status="missing" if warnings else "passed"),
        ]
        result = JobResult(
            operation="query_entities",
            status="partial" if warnings else "succeeded",
            job_id=manifest["job_id"],
            backend="keyword-engine" if source_kind == "keyword" else lb.backend(),
            data=data,
            checks=tuple(checks),
            warnings=tuple(sorted(warnings)),
            scope="Disk entities; no GUI visibility or source mutation",
        )
    except Exception as error:
        result = JobResult(
            operation="query_entities",
            status="failed",
            job_id=manifest["job_id"],
            backend="keyword-engine" if source_kind == "keyword" else lb.backend(),
            data={},
            error={"type": type(error).__name__, "message": str(error).strip() or type(error).__name__},
        )
    payload = result.model_dump(mode="json")
    atomic_json(directory / "job.json", {**manifest, "status": result.status, "result": payload})
    return payload
