"""Targeted native-export entity inspection; never rewrite an existing deck here."""

import hashlib
import math
from collections import Counter

from .deck_backend import api

DOFS = ("dofx", "dofy", "dofz", "dofrx", "dofry", "dofrz")
CAPTURE = ("*SET_NODE", "*SET_PART", "*SET_SEGMENT", "*BOUNDARY_SPC", "*BOUNDARY_PRESCRIBED_MOTION", "*DEFINE_COORDINATE")


def native_blocks(path):
    """Hash unmodified native card blocks incrementally, retain only entity cards."""
    name, lines, digest, size = None, [], None, 0
    with path.open(encoding="utf-8-sig", errors="strict") as stream:
        for raw in stream:
            line = raw.rstrip()
            if not line.strip() or line.lstrip().startswith("$"):
                continue
            if line.startswith("*"):
                if name is not None:
                    yield name, digest.hexdigest(), lines
                name = line.split(",")[0].split()[0].upper()
                digest, lines, size = hashlib.sha256(), [], 0
            if name is None:
                raise ValueError("Native export contains data outside a keyword")
            digest.update((line + "\n").encode("utf-8"))
            if name.startswith(CAPTURE):
                size += len(line)
                if size > 16 * 1024 * 1024:
                    raise ValueError("Entity card exceeds the 16 MiB inspection budget")
                lines.append(line)
        if name is not None:
            yield name, digest.hexdigest(), lines


def _members(values):
    result = []
    for value in values:
        if value is None or (isinstance(value, float) and math.isnan(value)) or value == 0:
            continue  # native final-row padding
        if isinstance(value, bool) or int(value) != value or value <= 0:
            raise ValueError("Invalid set member ID")
        result.append(int(value))
    if len(result) != len(set(result)):
        raise ValueError("Duplicate set members require explicit review")
    return sorted(result)


def fields(line):
    return [v.strip() for v in line.split(",")] if "," in line else [line[i:i+10].strip() for i in range(0, len(line), 10)]


def list_set(name, lines):
    """Explicit ten-column/CSV list parsing avoids SeriesCard CSV truncation."""
    titled = name.endswith("_TITLE")
    start = 2 if titled else 1
    if len(lines) <= start:
        raise ValueError("Missing set header")
    header = fields(lines[start]) + [""] * 8
    sid = int(header[0])
    if sid <= 0:
        raise ValueError("Nonpositive set ID")
    attrs = [float(v) if v else 0.0 for v in header[1:5]]
    if not all(math.isfinite(v) for v in attrs):
        raise ValueError("Nonfinite set attributes")
    members = _members([int(v) for line in lines[start+1:] for v in fields(line) if v])
    kind = "node" if name.startswith("*SET_NODE") else "part"
    return dict(entity_type=kind, set_id=sid, title=lines[1].strip() if titled else "",
                member_ids=members, attributes=attrs, solver=header[5] or "MECH",
                its=(header[6] or "1") if kind == "node" else None)


def spc_rows(name, lines):
    """Native *_ID exports may pack repeated ID/header + DOF pairs in one block."""
    named = name.endswith("_ID")
    data = lines[1:]
    if not data or (named and len(data) % 2):
        raise ValueError("Incomplete SPC ID/data pair")
    rows = []
    for i in range(0, len(data), 2 if named else 1):
        constraint_id, title = None, ""
        if named:
            head = data[i][:10].strip()
            if head and head.lstrip("+").isdigit():
                constraint_id, title = int(head), data[i][10:].strip()
            else:
                header = data[i].split(",", 1)
                constraint_id = int(header[0])
                title = header[1].strip() if len(header) > 1 else ""
        row = fields(data[i+1 if named else i])
        if len(row) > 8 and any(row[8:]):
            raise ValueError("Unsupported SPC row width")
        row = row[:8] + [""] * (8-len(row))
        values = [int(v) if v else 0 for v in row]
        if values[0] <= 0 or values[1] < 0 or any(v not in (0, 1) for v in values[2:]):
            raise ValueError("Invalid SPC target/coordinate/DOF fields")
        rows.append(dict(target_type="node_set" if name.startswith("*BOUNDARY_SPC_SET") else "node",
                         target_id=values[0], coordinate_system=values[1], dofs=values[2:],
                         constraint_id=constraint_id, title=title))
    return rows


def segment_set(name, lines):
    from .segment_geometry import canonical_cycle

    start = 2 if name.endswith("_TITLE") else 1
    if len(lines) <= start:
        raise ValueError("Missing segment-set header")
    header = fields(lines[start]) + [""] * 8
    sid = int(header[0])
    records, seen = [], set()
    for line in lines[start+1:]:
        row = fields(line) + [""] * 8
        nodes = [int(n) if n else 0 for n in row[:4]]
        if nodes[2:] == [0, 0]:
            nodes = nodes[:2]
        elif nodes[3] in (0, nodes[2]):
            nodes = nodes[:3]
        if any(n <= 0 for n in nodes) or len(nodes) != len(set(nodes)):
            raise ValueError("Invalid native segment connectivity")
        key = tuple(sorted(nodes))
        if key in seen:
            raise ValueError("Duplicate native segment face/edge")
        seen.add(key)
        attrs = [float(v) if v else 0.0 for v in row[4:8]]
        records.append(dict(node_ids=list(canonical_cycle(nodes)), attributes=attrs))
    attrs = [float(v) if v else 0.0 for v in header[1:5]]
    if sid <= 0 or not all(math.isfinite(v) for v in attrs + [v for r in records for v in r["attributes"]]):
        raise ValueError("Invalid segment-set ID/attributes")
    return dict(entity_type="segment", set_id=sid, title=lines[1].strip() if start == 2 else "",
                attributes=attrs, solver=header[5] or "MECH", its=int(header[6] or 0),
                segments=sorted(records, key=lambda r: r["node_ids"]))


def inspect_cards(path):
    Deck, _ = api()
    result = dict(sets={}, spcs=[], coordinates={0}, unresolved=[], other=Counter())
    for name, digest, lines in native_blocks(path):
        if name.startswith(("*INCLUDE", "*PARAMETER")):
            raise ValueError("Entity editing currently requires a standalone resolved native deck")
        if name in ("*KEYWORD", "*END"):
            continue
        if not name.startswith(CAPTURE):
            result["other"][(name, digest)] += 1
            continue
        if name in ("*SET_SEGMENT", "*SET_SEGMENT_TITLE"):
            record = segment_set(name, lines)
            key = ("segment", record["set_id"])
            if key in result["sets"]:
                raise ValueError("Duplicate segment set IDs")
            result["sets"][key] = record
            continue
        if name in ("*SET_NODE_LIST", "*SET_NODE_LIST_TITLE", "*SET_PART_LIST", "*SET_PART_LIST_TITLE"):
            record = list_set(name, lines)
            key = (record["entity_type"], record["set_id"])
            if key in result["sets"]:
                raise ValueError("Duplicate same-domain set IDs in native export")
            result["sets"][key] = record
            continue
        if name in ("*BOUNDARY_SPC_NODE", "*BOUNDARY_SPC_NODE_ID", "*BOUNDARY_SPC_SET", "*BOUNDARY_SPC_SET_ID"):
            result["spcs"].extend(spc_rows(name, lines))
            continue
        deck = Deck()
        deck.loads("*KEYWORD\n" + "\n".join(lines) + "\n*END\n")
        cards = list(deck.keywords)
        if len(cards) != 1 or isinstance(cards[0], str):
            result["unresolved"].append((name, digest))
            continue
        card = cards[0]
        if name.startswith("*DEFINE_COORDINATE"):
            result["coordinates"].add(int(card.cid))
            result["other"][(name, digest)] += 1
        else:
            result["unresolved"].append((name, digest))
    return result


def set_members(index, kind, set_id):
    if any(name.startswith("*SET_" + kind.upper()) for name, _ in index["unresolved"]):
        raise ValueError("Unsupported same-domain set variants require explicit resolution before editing")
    try:
        return index["sets"][(kind, set_id)]["member_ids"]
    except KeyError as exc:
        raise ValueError("Requested native set does not exist") from exc


def check_spc_conflicts(index, members, coordinate_system, dofs, constraint_id):
    if any(name.startswith(("*BOUNDARY_SPC", "*BOUNDARY_PRESCRIBED_MOTION")) for name, _ in index["unresolved"]):
        raise ValueError("Existing SPC/motion variant is unresolved; cannot establish nonconflicting constraints")
    if coordinate_system not in index["coordinates"]:
        raise ValueError("Unknown coordinate system ID")
    wanted = set(members)
    for spc in index["spcs"]:
        if constraint_id is not None and spc["constraint_id"] == constraint_id:
            raise ValueError("Constraint ID already exists")
        old = ({spc["target_id"]} if spc["target_type"] == "node" else
               set(set_members(index, "node", spc["target_id"])))
        if old & wanted and (spc["coordinate_system"] != coordinate_system or
                             any(a and b for a, b in zip(dofs, spc["dofs"]))):
            raise ValueError("Existing SPC overlaps requested constrained nodes/DOFs or uses another coordinate system")


def verify_cards(before, after, new_set=None, new_spcs=None):
    if before["other"] != after["other"] or Counter(before["unresolved"]) != Counter(after["unresolved"]):
        raise ValueError("Native entity creation changed an unrelated keyword block")
    expected_sets = dict(before["sets"])
    if new_set:
        key = (new_set["entity_type"], new_set["set_id"])
        actual = after["sets"].get(key)
        if not actual or any(actual[k] != v for k, v in new_set.items()):
            raise ValueError("Native set members/title/attributes differ from the request")
        expected_sets[key] = actual
    if expected_sets != after["sets"]:
        raise ValueError("Unrequested set changes in native export")
    def canonical(items):
        return Counter((s["target_type"], s["target_id"], s["coordinate_system"], tuple(s["dofs"]),
                        s["constraint_id"], s["title"]) for s in items)
    if canonical(before["spcs"] + (new_spcs or [])) != canonical(after["spcs"]):
        raise ValueError("Native SPC rows/references differ from expected constraints")
    return dict(unrelated_native_cards_preserved=True, entity_references_verified=True,
                scope="Native exported cards, supported list sets/SPC and mesh identity; not solver/physics certification")
