"""Strict LS-DYNA energy records; binary data uses the shared MPP reader only."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from . import lasso_backend
from .energy import ENERGIES, MAX_ROWS, PART_FIELDS, EnergyBalanceError
from .lasso_backend import MissingComponentError
from .mpp_shards import SHARD

LABELS = {key.replace("_", " "): key for key in ENERGIES}
LABELS.update({"sliding interface energy": "sliding_energy", "system damping energy": "damping_energy",
               "spring and damper energy": "spring_and_damper_energy"})
PAIR = re.compile(r"^\s*([a-zA-Z0-9_ /()#%-]+?)\s*(?:\.{2,}|:|=)\s*(\S+)(.*)$")
MATERIAL = re.compile(r"mat\.\s*#\s*=\s*([+-]?\d+)", re.I)
PART_KEYS = {"inten": "internal_energy", "kinen": "kinetic_energy", "hgeng": "hourglass_energy",
             "eroded_ie": "eroded_internal_energy", "eroded_ke": "eroded_kinetic_energy",
             "eroded_hg": "eroded_hourglass_energy"}
PART_PAIR = re.compile(r"\b(" + "|".join(PART_KEYS) + r")\s*=\s*(\S+)", re.I)
MAX_RECORD_CHARS = 16_384


def _lines(path):
    # Bound mistaken binary input / enormous records without buffering a whole line.
    with open(path, encoding="utf-8-sig", errors="replace") as stream:
        while line := stream.readline(MAX_RECORD_CHARS + 1):
            if len(line) > MAX_RECORD_CHARS:
                raise EnergyBalanceError("ASCII energy record exceeds 16384 characters; unsupported input")
            yield line


def _number(value, context):
    try:
        result = float(value.replace("D", "E").replace("d", "e"))
    except ValueError as error:
        raise EnergyBalanceError(f"Invalid numeric {context}") from error
    if not np.isfinite(result):
        raise EnergyBalanceError(f"Nonfinite numeric {context}")
    return result


def _columns(records, names):
    result = {"time": [record["time"] for record in records]}
    for key in names:
        values = [record.get(key) for record in records]
        result[key] = values if any(value is not None for value in values) else None
    return result


def read_ascii_glstat(path):
    """Read named time blocks only. Missing block fields remain null, never zero."""
    records, current, wall_names = [], None, set()
    for line in _lines(path):
        match = PAIR.match(line)
        if not match:
            continue
        label = " ".join(match[1].lower().split())
        key = "time" if label == "time" else LABELS.get(label)
        wall = "wall#" in (label + match[3].lower())
        if key is None and not wall:
            continue
        value = _number(match[2], f"glstat {label}")
        if key == "time":
            current = {"time": value, "_walls": {}}
            records.append(current)
            if len(records) > MAX_ROWS:
                raise EnergyBalanceError("glstat exceeds one million samples")
        elif current is not None:
            if wall:
                identity = label + match[3].strip().lower()
                if identity in current["_walls"]:
                    raise EnergyBalanceError("Duplicate glstat wall energy in one time block")
                current["_walls"][identity] = value
                wall_names.add(identity)
            elif key in current:
                raise EnergyBalanceError(f"Duplicate glstat {key} in one time block")
            else:
                current[key] = value
    if not records or not any(any(key in record for key in ENERGIES) for record in records):
        raise EnergyBalanceError("No LS-DYNA glstat named time/energy blocks recognized")
    for record in records:
        if "stonewall_energy" not in record and wall_names and record["_walls"].keys() == wall_names:
            record["stonewall_energy"] = sum(record["_walls"].values())
    return _columns(records, ENERGIES)


def read_ascii_matsum(path):
    """Read each material record including its HG continuation lines, skipping legends."""
    records, current, time, legend, count = {}, None, None, False, 0
    for line in _lines(path):
        if "{BEGIN LEGEND}" in line:
            legend = True
        if "{END LEGEND}" in line:
            legend = False
            continue
        if legend:
            continue
        tm = re.match(r"\s*time\s*=\s*(\S+)", line, re.I)
        if tm:
            time, current = _number(tm[1], "matsum time"), None
            continue
        mat = MATERIAL.search(line)
        if mat:
            if time is None or int(mat[1]) <= 0:
                raise EnergyBalanceError("MATSUM record needs a time and positive stored part ID")
            pid = int(mat[1])
            current = {"time": time}
            records.setdefault(pid, []).append(current)
            count += 1
            if count > MAX_ROWS:
                raise EnergyBalanceError("MATSUM exceeds one million part rows")
        if current is not None:
            for pair in PART_PAIR.finditer(line):
                key = PART_KEYS[pair[1].lower()]
                if key in current:
                    raise EnergyBalanceError(f"Duplicate MATSUM {key} in one part record")
                current[key] = _number(pair[2], f"matsum {key}")
    if not records:
        raise EnergyBalanceError("No LS-DYNA matsum time/material records recognized")
    return {pid: _columns(rows, PART_FIELDS) for pid, rows in records.items()}


def _series(path, database, component):
    if not SHARD.fullmatch(Path(path).name) and not Path(path).is_dir():
        raise EnergyBalanceError("Nonstandard binout filename unsupported; use an isolated standard family")
    return lasso_backend.binout_curves(path, database, component)


def read_binout_glstat(path):
    """Callers must confine the standard shard family before invoking shared reads."""
    base = _series(path, "glstat", "time")
    times = np.asarray(base["time"], dtype=float)
    if times.ndim != 1 or not times.size or times.size > MAX_ROWS:
        raise EnergyBalanceError("Invalid binout GLSTAT time vector")
    result = {"time": times.tolist()}
    for key in ENERGIES:
        aliases = {"sliding_energy": ("sliding_interface_energy", "sliding_energy"),
                   "damping_energy": ("system_damping_energy", "damping_energy")}.get(key, (key,))
        found = []
        for alias in aliases:
            try:
                found.append(_series(path, "glstat", alias))
            except MissingComponentError:
                pass
        if not found:
            result[key] = None
            continue
        item = found[0]
        if any(other["time"] != item["time"] or other["values"] != item["values"] for other in found[1:]):
            raise EnergyBalanceError(f"Conflicting GLSTAT aliases for {key}")
        values = np.asarray(item["values"], dtype=float)
        if values.shape == (times.size, 1):
            values = values[:, 0]
        if values.shape != times.shape or not np.array_equal(item["time"], times):
            raise EnergyBalanceError(f"GLSTAT {key}: state axes do not align")
        result[key] = values.tolist()
    return result


def read_binout_matsum(path):
    base = _series(path, "matsum", "time")
    ids, times = base["ids"], base["time"]
    if not ids or any(type(pid) is not int or pid <= 0 for pid in ids) or len(set(ids)) != len(ids):
        raise EnergyBalanceError("MATSUM needs unique positive stored part IDs")
    if not times or len(times) * len(ids) > MAX_ROWS:
        raise EnergyBalanceError("MATSUM export exceeds its bounded row limit or has no samples")
    parts = {pid: dict(time=times) for pid in ids}
    for key in PART_FIELDS:
        try:
            item = _series(path, "matsum", key)
        except MissingComponentError:
            for part in parts.values():
                part[key] = None
            continue
        values = np.asarray(item["values"], dtype=float)
        if len(ids) == 1 and values.shape == (len(times),):
            # Shared Binout reads flatten a single stored entity; keep its ID axis.
            values = values[:, None]
        if values.shape != (len(times), len(ids)) or item["ids"] != ids or item["time"] != times:
            raise EnergyBalanceError(f"MATSUM {key}: part IDs or time axes do not align")
        for index, pid in enumerate(ids):
            parts[pid][key] = values[:, index].tolist()
    return parts
