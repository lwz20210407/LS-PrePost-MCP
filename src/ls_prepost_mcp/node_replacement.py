"""Native node replacement with explicit supported-card repair and native reopen."""

import copy
from collections import Counter
from pathlib import Path

from .entity_cards import fields, inspect_cards, native_blocks
from .gui_mesh import check_same_nodes, check_same_parts, mesh_index
from .mesh_quality import element_metrics
from .segment_geometry import canonical_cycle

MESH = {"*NODE", "*ELEMENT_SHELL", "*ELEMENT_SOLID"}
NODE_SETS = {"*SET_NODE_LIST", "*SET_NODE_LIST_TITLE"}
SEGMENTS = {"*SET_SEGMENT", "*SET_SEGMENT_TITLE"}
SPC_NODES = {"*BOUNDARY_SPC_NODE", "*BOUNDARY_SPC_NODE_ID"}


def mapped_geometry(state, source, target):
    nodes, elements = mesh_index(state)
    if source == target or source not in nodes or target not in nodes:
        raise ValueError("Replacement requires two distinct registered node IDs")
    result, affected = {}, []
    for key, conn in elements.items():
        if key[0] not in ("shell", "solid"):
            raise ValueError("Node replacement currently verifies shell/solid models only")
        mapped = tuple(target if n == source else n for n in conn)
        result[key] = mapped
        if source not in conn:
            continue
        if target in conn:
            raise ValueError("Replacement would collapse an element's distinct nodes")
        corners = list(dict.fromkeys(n for n in mapped if n))
        metric = element_metrics(key[0], [nodes[n] for n in corners])
        if (not metric["supported"] or metric["min_edge"] <= 0 or metric.get("area", 1) <= 0
                or metric.get("signed_volume", 1) <= 0 or metric.get("minimum_jacobian", 1) <= 0
                or metric.get("min_angle", 90) <= 0 or metric.get("warpage_degrees", 0) >= 90):
            raise ValueError("Replacement would create unsupported/degenerate/inverted geometry")
        affected.append(dict(type=key[0], id=key[1]))
    return nodes, result, affected


def expected_references(index, source, target):
    expected = copy.deepcopy(index)
    for key, record in expected["sets"].items():
        if key[0] == "node":
            record["member_ids"] = sorted({target if n == source else n for n in record["member_ids"]})
        elif key[0] == "segment":
            seen = set()
            for face in record["segments"]:
                nodes = [target if n == source else n for n in face["node_ids"]]
                if len(nodes) != len(set(nodes)) or tuple(sorted(nodes)) in seen:
                    raise ValueError("Replacement would collapse/duplicate a Segment face or edge")
                seen.add(tuple(sorted(nodes)))
                face["node_ids"] = list(canonical_cycle(nodes))
            record["segments"].sort(key=lambda face:face["node_ids"])
    active = []
    for record in expected["spcs"]:
        if record["target_type"] == "node":
            if record["target_id"] == source:
                record["target_id"] = target
            members = [record["target_id"]]
        else:
            key = ("node", record["target_id"])
            if key not in expected["sets"]:
                raise ValueError("SPC refers to an unresolved node set")
            members = expected["sets"][key]["member_ids"]
        if target in members:
            for other in active:
                if other["coordinate_system"] != record["coordinate_system"] or any(a and b for a,b in zip(other["dofs"], record["dofs"])):
                    raise ValueError("Replacement merges overlapping SPC DOFs or different coordinate systems")
            active.append(record)
    return expected


def inspect_references(path, source, target):
    from ansys.dyna.core.lib.keyword_base import LinkType

    from .deck_backend import api

    Deck, kw = api()
    index = inspect_cards(path)
    node_blocks = []
    sensitive = ("*DEFINE_", "*BOUNDARY_", "*LOAD_", "*RIGIDWALL_")
    for name, _, lines in native_blocks(path, capture_prefixes=("*NODE",) + sensitive):
        if (name.startswith(("*INCLUDE", "*PARAMETER", "*CONSTRAINED", "*LOAD_NODE", "*INITIAL",
                             "*DATABASE_HISTORY_NODE", "*DEFINE_COORDINATE_NODES", "*BOUNDARY_PRESCRIBED_MOTION",
                             "*BOUNDARY_NON_REFLECTING_2D"))
                or name.startswith("*NODE_") or name.startswith("*ELEMENT_") and name not in MESH):
            raise ValueError("Node-reference remapping is not yet verified for " + name)
        if name == "*NODE":
            node_blocks.extend(lines)
        elif name.startswith(sensitive) and not name.startswith("*BOUNDARY_SPC"):
            fragment = Deck()
            fragment.loads("*KEYWORD\n" + "\n".join(lines) + "\n*END\n")
            cards = list(fragment.keywords)
            if (not cards or any(isinstance(card,str) for card in cards)
                    or any(LinkType.NODE in getattr(card,"_link_fields",{}).values() for card in cards)):
                raise ValueError("Unhandled direct-node reference metadata in " + name)
    if any(name.startswith(("*SET_NODE", "*SET_SEGMENT", "*BOUNDARY_SPC")) for name, _ in index["unresolved"]):
        raise ValueError("Unsupported node/segment/SPC variant prevents reference remapping")
    # Native node TC/RC flags are separate from SPC cards; do not discard or
    # invent their merged meaning. Read them through the pinned keyword schema.
    from .model_deck import table

    deck = Deck()
    deck.loads("*KEYWORD\n" + "\n".join(node_blocks) + "\n*END\n")
    frame = table(deck, kw.Node, "nodes")
    attributes = {int(row.nid):(int(row.tc), int(row.rc)) for row in frame.itertuples()}
    if source not in attributes or target not in attributes or any(attributes[n] != (0,0) for n in (source,target)):
        raise ValueError("Source/target NODE TC/RC attributes require explicit resolution")
    return index, expected_references(index, source, target), attributes


def patch_reference_cards(source_path, output, expected, source, target):
    """Patch only supported reference blocks in a fresh native-export copy."""
    text = Path(source_path).read_bytes().decode("utf8")
    lines = text.splitlines(keepends=True)
    starts = [i for i,line in enumerate(lines) if line.startswith("*")] + [len(lines)]
    out = lines[:starts[0]] if starts else lines

    def replace_ids(line, count):
        ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
        body = line.rstrip("\r\n")
        if "," in body:
            cells = body.split(",")
            for i in range(min(count,len(cells))):
                if cells[i].strip() and int(cells[i]) == source:
                    cells[i] = str(target)
            return ",".join(cells) + ending
        for i in range(count):
            cell = body[i*10:(i+1)*10]
            if cell.strip() and int(cell) == source:
                body = body[:i*10] + f"{target:10d}" + body[(i+1)*10:]
        return body + ending

    for begin, end in zip(starts, starts[1:]):
        block = list(lines[begin:end])
        name = block[0].strip().split()[0].split(",")[0].upper()
        data = [i for i,line in enumerate(block) if line.strip() and not line.lstrip().startswith("$")]
        if name in NODE_SETS:
            header = data[2 if name.endswith("_TITLE") else 1]
            sid = int(fields(block[header])[0])
            members = expected["sets"][("node",sid)]["member_ids"]
            ending = "\r\n" if block[header].endswith("\r\n") else "\n"
            comments = [line for line in block[header+1:] if not line.strip() or line.lstrip().startswith("$")]
            block = block[:header+1] + comments + ["".join(f"{n:10d}" for n in members[i:i+8])+ending for i in range(0,len(members),8)]
        elif name in SEGMENTS:
            for i in data[3 if name.endswith("_TITLE") else 2:]:
                block[i] = replace_ids(block[i],4)
        elif name in SPC_NODES:
            for i in (data[2::2] if name.endswith("_ID") else data[1:]):
                block[i] = replace_ids(block[i],1)
        out.extend(block)
    with Path(output).open("xb") as stream:
        stream.write("".join(out).encode("utf8"))


def verify_references(expected, actual):
    if expected["sets"] != actual["sets"]:
        raise ValueError("Native reopened sets differ from mapped node/segment membership")
    def constraints(index):
        return Counter((r["target_type"],r["target_id"],r["coordinate_system"],tuple(r["dofs"]),r["constraint_id"],r["title"]) for r in index["spcs"])
    if constraints(expected) != constraints(actual):
        raise ValueError("Native reopened SPC rows differ from expected mapping")
    def nonmesh(index):
        return Counter({key:value for key,value in index["other"].items() if key[0] not in MESH})
    if nonmesh(expected) != nonmesh(actual) or expected["unresolved"] != actual["unresolved"]:
        raise ValueError("Node replacement changed an unrelated native keyword block")


def replace_node(service, sid, source, target, units):
    from .post_backend import ids
    from .service import unit_label

    ids([source,target], "source/target node IDs", 2)
    unit_label(units)
    context = {}
    def precheck(state):
        nodes, _, affected = mapped_geometry(state, source, target)
        context["affected"] = affected
        context["native_nodes"] = set(nodes)
    def preflight(path):
        before, expected, attrs = inspect_references(path,source,target)
        if set(attrs) != context["native_nodes"]:
            raise ValueError("Native and keyword NODE attribute registries disagree")
        context.update(before=before,expected=expected,attributes=attrs)
    def verify(before, after):
        old, expected, affected = mapped_geometry(before,source,target)
        nodes, elements = mesh_index(after)
        check_same_nodes({k:v for k,v in old.items() if k != source}, nodes)
        check_same_parts(before,after)
        if elements != expected or before["part_visibility"] != after["part_visibility"]:
            raise ValueError("Native replacement changed unexpected connectivity or part visibility")
        return dict(removed_node=source, retained_node=target, affected_elements=affected,
                    target_coordinates_preserved=True, all_remaining_coordinates_verified=True,
                    backend="native_node_replace+targeted_reference_patch+native_reopen")
    def finalize(before, raw):
        verify(before,raw["data"])
        raw_dir = Path(raw["job_directory"])
        repaired = raw_dir / "references-fixed.k"
        patch_reference_cards(raw_dir/"model.k",repaired,context["expected"],source,target)
        verify_references(context["expected"],inspect_cards(repaired))
        manager = service._session_manager()
        opened = manager.dispatch(sid,"inspect_model",{},model=repaired,file_type="keyword")
        if opened["status"] != "succeeded":
            raise ValueError("Reference-repaired keyword did not reopen natively")
        commands = ["+m "+pid if visible else "-m "+pid for pid,visible in before["part_visibility"].items()]
        result = manager.dispatch(sid,"gui_mesh_state",{},native_commands=commands+["genselect clear"],
                                  artifacts=(("model.k","keyword"),),export=True)
        result["raw_replace_request"] = raw["job_directory"]
        result["reference_patch"] = str(repaired)
        result["execution_mode"] = "visible_gui_native_replace_targeted_reference_patch_native_reopen"
        return result
    def postcheck(_, path, verification):
        actual, _, attrs = inspect_references(path,target,target)
        verify_references(context["expected"],actual)
        if attrs != {k:v for k,v in context["attributes"].items() if k != source}:
            raise ValueError("Replacement changed remaining NODE attributes")
        return dict(node_sets_and_segments_and_spcs_verified=True, unrelated_blocks_preserved=True,
                    unchanged_keyword_families=sorted({name for name,_ in context["expected"]["other"] if name not in MESH}),
                    all_keywords_certified=False, scope="Supported list sets, Segment sets, SPCs and native mesh; no solver/physics certification")
    commands = ["elemedit replace clear",f"elemedit replace two {source} {target} 2","elemedit replace accept","genselect clear"]
    return service._gui_mesh_edit(sid,"replace_gui_node",dict(source_node_id=source,target_node_id=target,units=units),
        commands,verify,precheck,postcheck,preflight,finalize_native=finalize)
