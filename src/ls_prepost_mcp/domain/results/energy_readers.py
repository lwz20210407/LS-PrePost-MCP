"""Strict LS-DYNA energy records; binary data uses the shared MPP reader only."""
from __future__ import annotations

import re
import string
from pathlib import Path

import numpy as np

from . import lasso_backend
from .ascii_records import RecordTooLong, bounded_lines, tokenize_scalar
from .energy import ENERGIES, MAX_ROWS, PART_FIELDS, EnergyBalanceError
from .lasso_backend import MissingComponentError
from .mpp_shards import SHARD

LABELS = {key.replace("_", " "): key for key in ENERGIES}
LABELS.update({"sliding interface energy": "sliding_energy", "system damping energy": "damping_energy",
               "spring and damper energy": "spring_and_damper_energy"})
GLSTAT_LABEL_CHARACTERS = frozenset(string.ascii_letters + string.digits + "_ /()#%-")
MATERIAL = re.compile(r"mat\.\s*#\s*=\s*([+-]?\d+)", re.I)
PART_KEYS = {"inten": "internal_energy", "kinen": "kinetic_energy", "hgeng": "hourglass_energy",
             "eroded_ie": "eroded_internal_energy", "eroded_ke": "eroded_kinetic_energy",
             "eroded_hg": "eroded_hourglass_energy"}
PART_PAIR = re.compile(r"\b(" + "|".join(PART_KEYS) + r")\s*=\s*(\S+)", re.I)
MAX_RECORD_CHARS = 16_384


def _lines(path, *, errors="replace", max_record_chars=MAX_RECORD_CHARS):
    # Bound mistaken binary input / enormous records without buffering a whole line.
    with open(path, encoding="utf-8-sig", errors=errors) as stream:
        while line := stream.readline(max_record_chars + 1):
            if len(line) > max_record_chars:
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


def _glstat_lines(path):
    # Q12's replacement decoding and lack of a 256 MiB file policy are deliberate.
    # Leave the existing _lines path for MATSUM unchanged.
    try:
        yield from bounded_lines(path, max_record_chars=MAX_RECORD_CHARS, encoding="utf-8-sig", errors="replace")
    except RecordTooLong as error:
        raise EnergyBalanceError("ASCII energy record exceeds 16384 characters; unsupported input") from error


def _columns(records, names):
    result = {"time": [record["time"] for record in records]}
    for key in names:
        values = [record.get(key) for record in records]
        result[key] = values if any(value is not None for value in values) else None
    return result


def read_ascii_glstat(path):
    """Read named time blocks only. Missing block fields remain null, never zero."""
    records, current, wall_names = [], None, set()
    for line in _glstat_lines(path):
        field = tokenize_scalar(line, separators=".:=", minimum_dots=2, require_dot_space=False,
                                label_characters=GLSTAT_LABEL_CHARACTERS)
        if field is None:
            continue
        label = " ".join(field.raw_label.lower().split())
        key = "time" if label == "time" else LABELS.get(label)
        wall = "wall#" in (label + field.suffix.lower())
        if key is None and not wall:
            continue
        value = _number(field.value_token, f"glstat {label}")
        if key == "time":
            current = {"time": value, "_walls": {}}
            records.append(current)
            if len(records) > MAX_ROWS:
                raise EnergyBalanceError("glstat exceeds one million samples")
        elif current is not None:
            if wall:
                identity = label + field.suffix.strip().lower()
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
    return _matsum_records(_lines(path))


def read_ascii_matsum_details(path, *, max_record_chars=MAX_RECORD_CHARS):
    """Expose raw block/field identity for Q06; keep Q12's nullable wrapper unchanged.

    The material-record parsing and numeric conversion are shared. Observations
    about empty blocks, legends and lexical identity do not impose a Q12 policy.
    """
    details = {"blocks": [], "source_column_names": {"time": [], "id": []}, "issues": []}
    details["parts"] = _matsum_records(_lines(path, errors="strict", max_record_chars=max_record_chars), details)
    return details


def _matsum_records(lines, details=None):
    records, current, time, legend, count = {}, None, None, False, 0
    block = None

    def issue(message):
        if details is not None and len(details["issues"]) < 16:
            details["issues"].append(message)

    def label(key, value):
        if details is not None:
            names = details["source_column_names"].setdefault(key, [])
            if value not in names:
                if len(names) >= 64:
                    issue("Too many MATSUM source label variants")
                else:
                    names.append(value)

    def numeric_token(key, token, value):
        if details is not None:
            if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?", token):
                issue(f"Invalid MATSUM numeric token for {key}")
            elif value == 0 and re.search("[1-9]", re.split("[eEdD]", token)[0]):
                issue(f"MATSUM numeric token underflows float64 for {key}")

    for line in lines:
        if "{BEGIN LEGEND}" in line:
            if legend:
                issue("Nested MATSUM legend")
            legend = True
        if "{END LEGEND}" in line:
            if not legend:
                issue("Unmatched MATSUM legend ending")
            legend = False
            continue
        if legend:
            continue
        tm = re.match(r"\s*(time)\s*=\s*(\S+)", line, re.I)
        if tm:
            time, current = _number(tm[2], "matsum time"), None
            numeric_token("time", tm[2], time)
            label("time", tm[1])
            if details is not None:
                if len(details["blocks"]) >= MAX_ROWS:
                    raise EnergyBalanceError("MATSUM exceeds one million time blocks")
                block = {"time": time, "ids": [], "rows": []}
                details["blocks"].append(block)
            continue
        if re.match(r"\s*time\s*=", line, re.I):
            issue("Malformed MATSUM time record")
        mat = MATERIAL.search(line)
        raw_id = re.search(r"(mat\.\s*#)\s*=\s*(\S*)", line, re.I)
        if raw_id:
            label("id", raw_id[1])
            if not re.fullmatch(r"[+-]?\d+", raw_id[2]):
                issue("Malformed MATSUM part identifier")
        if mat:
            if time is None or int(mat[1]) <= 0:
                raise EnergyBalanceError("MATSUM record needs a time and positive stored part ID")
            pid = int(mat[1])
            current = {"time": time}
            records.setdefault(pid, []).append(current)
            if details is not None and block is not None:
                block["ids"].append(pid)
                block["rows"].append(current)
            count += 1
            if count > MAX_ROWS:
                raise EnergyBalanceError("MATSUM exceeds one million part rows")
        if current is not None:
            for pair in PART_PAIR.finditer(line):
                key = PART_KEYS[pair[1].lower()]
                if key in current:
                    raise EnergyBalanceError(f"Duplicate MATSUM {key} in one part record")
                current[key] = _number(pair[2], f"matsum {key}")
                label(key, pair[1])
                numeric_token(key, pair[2], current[key])
    if legend:
        issue("Truncated MATSUM legend")
    if not records:
        if details is not None and details["issues"]:
            return {}
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
