"""Readback contracts for native pressure curves and nonreflecting boundary cards."""

import math
from collections import Counter

import numpy as np

from .entity_cards import fields, list_set, motion_rows, native_blocks

PREFIXES = ("*DEFINE_CURVE", "*DEFINE_TABLE", "*DEFINE_FUNCTION", "*LOAD_SEGMENT_SET", "*BOUNDARY_NON_REFLECTING")


def number(value, default=0.0):
    result = float(value.replace("D", "E").replace("d", "e")) if value else default
    if not math.isfinite(result):
        raise ValueError("Nonfinite native boundary data")
    return result


def curve_record(name, lines):
    start = 2 if name.endswith("_TITLE") else 1
    row = fields(lines[start]) + [""]*8
    points = []
    for line in lines[start+1:]:
        values = line.split(",") if "," in line else [line[:20], line[20:40]]
        if len(values) != 2:
            raise ValueError("Unsupported native pressure curve row")
        points.append([number(v.strip()) for v in values])
    return dict(curve_id=int(row[0]), title=lines[1].strip() if start == 2 else "",
                sidr=int(row[1] or 0), sfa=number(row[2], 1.0), sfo=number(row[3], 1.0),
                offa=number(row[4]), offo=number(row[5]), dattyp=int(row[6] or 0), lcint=int(row[7] or 0), points=points)


def inspect_boundary_cards(path, include_ordered_node_sets=False, include_motions=False):
    prefixes = PREFIXES + (("*SET_NODE",) if include_ordered_node_sets else ())
    if include_motions:
        prefixes+=('*BOUNDARY_PRESCRIBED_MOTION',)
    result = dict(curves={}, loads=[], motions=[], nonreflecting=[], ordered_node_sets={}, namespace_ids=set(), unresolved=[], other=Counter())
    for name, digest, lines in native_blocks(path, prefixes):
        if name in ("*KEYWORD", "*END"):
            continue
        if not name.startswith(prefixes):
            result["other"][(name, digest)] += 1
        elif name.startswith('*BOUNDARY_PRESCRIBED_MOTION'):
            try:
                result['motions'].extend(motion_rows(name,lines))
            except NotImplementedError:
                result['unresolved'].append((name,digest))
        elif name in ("*SET_NODE_LIST", "*SET_NODE_LIST_TITLE"):
            record = list_set(name, lines)
            start = 3 if name.endswith("_TITLE") else 2
            record["order"] = [int(v) for line in lines[start:] for v in fields(line) if v and int(v) != 0]
            if record["set_id"] in result["ordered_node_sets"]:
                raise ValueError("Duplicate ordered node-set ID")
            result["ordered_node_sets"][record["set_id"]] = record
        elif name in ("*DEFINE_CURVE", "*DEFINE_CURVE_TITLE"):
            record = curve_record(name, lines)
            uid = record["curve_id"]
            if uid <= 0 or uid in result["namespace_ids"]:
                raise ValueError("Duplicate/invalid curve namespace ID")
            result["curves"][uid] = record
            result["namespace_ids"].add(uid)
        elif name in ("*LOAD_SEGMENT_SET", "*LOAD_SEGMENT_SET_ID"):
            named = name.endswith("_ID")
            data = lines[1:]
            if named and len(data) % 2:
                raise ValueError("Unsupported native load-ID record layout")
            for i in range(0, len(data), 2 if named else 1):
                load_id, title = None, ""
                if named:
                    head = data[i][:10].strip()
                    if head and head.lstrip("+").isdigit():
                        load_id, title = int(head), data[i][10:].strip()
                    else:
                        header = data[i].split(",", 1)
                        load_id, title = int(header[0]), header[1].strip() if len(header) > 1 else ""
                line = data[i+1 if named else i]
                row = fields(line) + [""]*4
                result["loads"].append(dict(set_id=int(row[0]), curve_id=int(row[1]), scale=number(row[2], 1.0),
                                             arrival_time=number(row[3]), load_id=load_id, title=title))
        elif name in ("*BOUNDARY_NON_REFLECTING", "*BOUNDARY_NON_REFLECTING_2D"):
            if len(lines) == 1:
                result["unresolved"].append((name, digest))  # unscoped ALE whole-boundary form
            for line in lines[1:]:
                row = fields(line) + [""]*3
                result["nonreflecting"].append(dict(dimension=2 if name.endswith("_2D") else 3,
                    target_id=int(row[0]), ad=number(row[1]), as_=number(row[2])))
        else:
            # Unknown variants are retained and block their affected namespace.
            result["unresolved"].append((name, digest))
            if name.startswith(("*DEFINE_TABLE", "*DEFINE_FUNCTION")):
                try:
                    index = 2 if name.endswith("_TITLE") else 1
                    uid = int(fields(lines[index])[0])
                    if uid in result["namespace_ids"]:
                        raise ValueError("Duplicate curve/table/function namespace ID")
                    result["namespace_ids"].add(uid)
                except (IndexError, TypeError):
                    raise ValueError("Cannot resolve native curve/table/function namespace") from None
    return result


def verify_boundary_delta(before, after, curve=None, load=None, nonreflecting=None, new_node_sets=None, motions=None):
    if before["other"] != after["other"] or Counter(before["unresolved"]) != Counter(after["unresolved"]):
        raise ValueError("Boundary creation changed an unrelated native keyword")
    expected_curves = dict(before["curves"])
    max_error = 0.0
    if curve is not None:
        actual = after["curves"].get(curve["curve_id"])
        if actual is None or any(actual[k] != v for k, v in curve.items() if k != "points"):
            raise ValueError("Native curve header differs from request")
        a, b = np.asarray(actual["points"]), np.asarray(curve["points"])
        if a.shape != b.shape or np.any(np.diff(a[:, 0]) <= 0) or not np.allclose(a, b, rtol=2e-6, atol=0):
            raise ValueError("Native pressure curve samples differ from request")
        max_error = float(np.max(np.abs(a-b)))
        expected_curves[curve["curve_id"]] = actual
    if expected_curves != after["curves"]:
        raise ValueError("Unexpected curve changes")
    expected_sets = dict(before.get("ordered_node_sets", {}))
    for record in new_node_sets or []:
        expected_sets[record["set_id"]] = record
    if expected_sets != after.get("ordered_node_sets", {}):
        raise ValueError("Native ordered node-set members/attributes/order changed")
    actual_load = None
    if load is not None:
        matches = [r for r in after["loads"] if all(r[k] == load[k] for k in ("set_id", "curve_id", "load_id", "title"))]
        if len(matches) != 1 or any(not math.isclose(matches[0][k], load[k], rel_tol=2e-6, abs_tol=0)
                                    for k in ("scale", "arrival_time")):
            raise ValueError("Native loads differ from requested references/parameters")
        actual_load = matches[0]
    for key, new in (("loads", actual_load), ("nonreflecting", nonreflecting)):
        expected = before[key] + ([] if new is None else new if isinstance(new, list) else [new])
        def canonical(rows):
            return Counter(tuple(sorted(row.items())) for row in rows)
        if canonical(expected) != canonical(after[key]):
            raise ValueError("Native " + key + " differ from requested references/parameters")
    actual_motions=[]
    for motion in motions or []:
        matches=[m for m in after.get('motions',[]) if all(m[k]==motion[k] for k in ('target_type','target_id','motion_id','title','dof','vad','curve_id','vector_id'))]
        if len(matches)!=1 or any(not math.isclose(matches[0][k],motion[k],rel_tol=2e-6,abs_tol=0) for k in ('scale','birth','death')):
            raise ValueError('Native prescribed-motion references/values differ from request')
        actual_motions.append(matches[0])
    if Counter(tuple(sorted(m.items())) for m in before.get('motions',[])+actual_motions) != Counter(tuple(sorted(m.items())) for m in after.get('motions',[])):
        raise ValueError('Unexpected prescribed-motion changes')
    return dict(native_card_references_verified=True, unrelated_native_cards_preserved=True,
                curve_maximum_absolute_error=max_error, curve_relative_tolerance=2e-6,
                actual_load=actual_load,
                actual_motions=actual_motions,
                solver_validated=False)
