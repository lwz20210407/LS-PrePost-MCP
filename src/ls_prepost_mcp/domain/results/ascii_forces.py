"""Q06 named RCFORC/SECFORC text records; never infer missing values or merge files.

RCFORC retains the written interface side. SECFORC requires its explicit three-line
column header and complete force/moment/centroid triplets. Unsupported layouts fail.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from .lasso_backend import ResultsError

MAX_BYTES = 256 * 1024 * 1024
MAX_RECORD_CHARS = 16_384
MAX_RECORDS = 1_000_000
CONTACT = re.compile(r"^\s*(slave|master|surfa|surfb)\s+(\d+)\s+time\s+(\S+)\s+(.+)$", re.I)
UNDEFINED = re.compile(r"^\s*interface number,\s*(\d+)\s*,is single surface-resultants are undefined\s*$", re.I)
SIDES = {"slave": 0, "surfa": 0, "master": 1, "surfb": 1}
CONTACT_FIELDS = {"x_force": "x", "y_force": "y", "z_force": "z", "mass": "mass",
                  "x_moment": "mx", "y_moment": "my", "z_moment": "mz"}
SECTION_FIELDS = ("x_force", "y_force", "z_force", "force_magnitude", "x_moment", "y_moment",
                  "z_moment", "moment_magnitude", "x_centroid", "y_centroid", "z_centroid", "area")
SECTION_HEADERS = (
    "line#1 section# time x-force y-force z-force magnitude",
    "line#2 resultant moments x-moment y-moment z-moment magnitude",
    "line#3 centroids x y z area",
)


def _lines(path, metadata):
    if Path(path).stat().st_size > MAX_BYTES:
        raise ResultsError("ASCII forces input exceeds 256 MiB")
    legend = False
    titles = metadata.setdefault("legend_titles", {})
    with open(path, encoding="utf-8-sig", errors="replace") as stream:
        while line := stream.readline(MAX_RECORD_CHARS + 1):
            if len(line) > MAX_RECORD_CHARS:
                raise ResultsError("ASCII force record exceeds 16384 characters")
            if "{BEGIN LEGEND}" in line:
                if legend:
                    raise ResultsError("Nested ASCII legend")
                legend = True
                continue
            if "{END LEGEND}" in line:
                if not legend:
                    raise ResultsError("Unmatched ASCII legend ending")
                legend = False
                continue
            if legend and line.strip():
                match = re.fullmatch(r"\s*(\d+)\s+(.+?)\s*", line)
                if match and int(match[1]) > 0:
                    key, title = str(int(match[1])), match[2]
                    if key in titles and titles[key] != title:
                        titles[key] = None
                        metadata.setdefault("ambiguous_legend_ids", {})[key] = True
                    if key not in titles and len(titles) >= MAX_RECORDS:
                        raise ResultsError("ASCII legend exceeds one million entries")
                    if key not in metadata.get("ambiguous_legend_ids", {}):
                        titles[key] = title
                else:
                    metadata["unparsed_legend_lines"] = metadata.get("unparsed_legend_lines", 0) + 1
            elif not legend and line.strip():
                yield line.strip()
    if legend:
        raise ResultsError("Truncated ASCII legend")


def _number(token):
    try:
        value = float(token.replace("D", "E").replace("d", "e"))
    except ValueError as error:
        raise ResultsError("Invalid ASCII force number") from error
    if not math.isfinite(value):
        raise ResultsError("Nonfinite ASCII force number")
    return value


def _id(token):
    if not re.fullmatch(r"\d+", token) or int(token) < 1:
        raise ResultsError("ASCII forces need positive stored entity IDs")
    return int(token)


def _contact(path, component, metadata):
    if component not in CONTACT_FIELDS:
        raise ResultsError(f"RCFORC component must be one of {list(CONTACT_FIELDS)}")
    seen = False
    undefined = set()
    for line in _lines(path, metadata):
        if match := UNDEFINED.fullmatch(line):
            undefined.add(_id(match[1]))
            continue
        match = CONTACT.fullmatch(line)
        if match:
            seen = True
            tokens = match[4].split()
            if len(tokens) % 2:
                raise ResultsError("Incomplete RCFORC named field/value pairs")
            fields = {}
            for name, token in zip(tokens[::2], tokens[1::2]):
                name = name.lower()
                if name not in CONTACT_FIELDS.values() or name in fields:
                    raise ResultsError("Unsupported or duplicate RCFORC field")
                fields[name] = _number(token)
            if not {"x", "y", "z", "mass", CONTACT_FIELDS[component]} <= fields.keys():
                raise ResultsError(f"RCFORC missing required field or requested component {component}")
            yield (_id(match[2]), SIDES[match[1].lower()]), _number(match[3]), fields[CONTACT_FIELDS[component]]
        elif seen or re.match(r"^(slave|master|surfa|surfb)\b", line, re.I):
            raise ResultsError("Unsupported or malformed RCFORC data record")
    metadata["undefined_interface_ids"] = sorted(undefined)


def _section(path, component, metadata):
    if component not in SECTION_FIELDS:
        raise ResultsError(f"SECFORC component must be one of {list(SECTION_FIELDS)}")
    headers, pending, systems = [], [], {}
    for line in _lines(path, metadata):
        normalized = " ".join(line.lower().split())
        if normalized.startswith("line#"):
            if pending:
                raise ResultsError("SECFORC header interrupts an incomplete record")
            if normalized != SECTION_HEADERS[len(headers) % 3]:
                raise ResultsError("Unsupported SECFORC column header")
            headers.append(normalized)
            continue
        if len(headers) < 3:
            if headers or re.match(r"^\d+\s+[-+.\d]", line):
                raise ResultsError("SECFORC requires its complete three-line column header before data")
            continue
        if len(pending) == 0:
            tokens = line.split()
            if len(tokens) != 6:
                raise ResultsError("SECFORC force row needs section ID, time and four components")
            pending = [_id(tokens[0]), _number(tokens[1]), [_number(v) for v in tokens[2:]]]
        elif len(pending) == 3:
            match = re.fullmatch(r"(ac\s+ID\s*=\s*(\d+))\s+(.+)", line, re.I)
            tokens = match[3].split() if match else line.split()
            coordinate = int(match[2]) if match else None
            pid = pending[0]
            reference = systems.setdefault(pid, {"id": coordinate, "prefixes": []})
            if reference["id"] != coordinate:
                raise ResultsError("SECFORC local-frame reference changes within one section history")
            if match and match[1] not in reference["prefixes"]:
                reference["prefixes"].append(match[1])
            if len(tokens) != 4:
                raise ResultsError("SECFORC moment row needs four components")
            pending.append([_number(v) for v in tokens])
        else:
            tokens = line.split()
            if len(tokens) != 4:
                raise ResultsError("SECFORC centroid row needs three coordinates and area")
            values = pending[2] + pending[3] + [_number(v) for v in tokens]
            yield (pending[0],), pending[1], values[SECTION_FIELDS.index(component)]
            pending = []
    if pending or len(headers) % 3:
        raise ResultsError("Truncated SECFORC three-line record or header")
    metadata["frame_references"] = systems


def read(path, database, component):
    """Return the shared time/entity matrix contract, in written order and units.

    Every entity must have the same strictly increasing times. Duplicate records,
    gaps and mismatched grids fail; there is no sorting, fill, interpolation or sum.
    """
    if database not in ("rcforc", "secforc"):
        raise ResultsError("ASCII force database must be rcforc or secforc")
    metadata, series, count = {}, {}, 0
    reader = _contact if database == "rcforc" else _section
    for key, time, value in reader(path, component, metadata):
        count += 1
        if count > MAX_RECORDS:
            raise ResultsError("ASCII forces exceed one million stored entity rows")
        samples = series.setdefault(key, [])
        if samples and time <= samples[-1][0]:
            raise ResultsError("ASCII forces need strictly increasing times without duplicate entity records")
        samples.append((time, value))
    if not series:
        raise ResultsError("No supported ASCII force records; undefined resultants are not zero")
    keys = list(series)
    times = [t for t, _ in series[keys[0]]]
    if any([t for t, _ in series[key]] != times for key in keys):
        raise ResultsError("ASCII force entity time grids differ; no missing values are inferred")
    warnings = []
    if metadata.get("ambiguous_legend_ids"):
        metadata["ambiguous_legend_ids"] = sorted(metadata["ambiguous_legend_ids"], key=int)
        warnings.append("Conflicting ASCII legend titles left null; see ambiguous_legend_ids")
    if metadata.get("unparsed_legend_lines"):
        warnings.append("Some ASCII legend lines could not be associated with positive stored IDs; see unparsed_legend_lines")
    if database == "rcforc":
        metadata["side"] = [key[1] for key in keys]
        metadata["side_meaning"] = {"0": "slave/SURFA (secondary)", "1": "master/SURFB (main)"}
        if metadata["undefined_interface_ids"]:
            warnings.append("Undefined single-surface resultants omitted for interface IDs "
                            + str(metadata["undefined_interface_ids"]))
    else:
        systems = metadata.pop("frame_references")
        metadata["local_frame_reference"] = [systems[key[0]] for key in keys]
    return {"backend": "ls-dyna-ascii", "source_format": database, "time": times,
            "ids": [key[0] for key in keys],
            "values": [[series[key][i][1] for key in keys] for i in range(len(times))],
            "entity_metadata": metadata, "shards": [], "repeated_times_dropped": 0,
            "warnings": warnings, "merge": "none; one explicit ASCII file with identical entity time grids"}
