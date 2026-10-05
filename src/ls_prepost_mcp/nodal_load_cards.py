"""Explicit nodal force/moment records; no follower/local-frame inference."""

import math

from .entity_cards import fields, set_members

LOAD_AXES = {"x": 1, "y": 2, "z": 3, "rx": 5, "ry": 6, "rz": 7}


def distribution_scale(scale, member_count, distribution):
    per_node = scale / member_count if distribution == "total_equal" else scale
    if per_node == 0 or not math.isfinite(per_node * member_count):
        raise ValueError("Distributed load scale underflows or summed scale overflows")
    return per_node


def nodal_load_rows(name, lines):
    if name not in ("*LOAD_NODE_POINT", "*LOAD_NODE_SET"):
        raise NotImplementedError("Unsupported nodal-load variant")
    result = []
    for line in lines[1:]:
        row = fields(line)
        if len(row) > 8 and any(row[8:]):
            raise NotImplementedError("Extended nodal-load layout")
        row += [""] * 8
        value = float((row[3] or "1").replace("D", "E").replace("d", "e"))
        if not math.isfinite(value):
            raise ValueError("Nonfinite nodal-load scale")
        record = dict(
            target_type="node_set" if name.endswith("_SET") else "node",
            target_id=int(row[0]),
            dof=int(row[1] or 0),
            curve_id=int(row[2]),
            scale=value,
            coordinate_system=int(row[4] or 0),
            m1=int(row[5] or 0),
            m2=int(row[6] or 0),
            m3=int(row[7] or 0),
        )
        result.append(record)
    return result


def load_overlap(existing, entities, members, dof):
    """Return overlapping fixed global DOFs; uncertain frames must be reviewed."""
    wanted = set(members)
    overlaps = []
    for record in existing:
        targets = (
            set_members(entities, "node", record["target_id"])
            if record["target_type"] == "node_set"
            else [record["target_id"]]
        )
        common = wanted.intersection(targets)
        if not common:
            continue
        if (
            record["coordinate_system"]
            or record["dof"] not in LOAD_AXES.values()
            or any(record[k] for k in ("m1", "m2", "m3"))
        ):
            raise ValueError("Overlapping local/follower nodal load requires explicit engineering review")
        if record["dof"] == dof:
            overlaps.append(dict(record, overlapping_node_count=len(common)))
    return overlaps
