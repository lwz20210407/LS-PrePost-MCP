"""Q06 dotted-label ASCII GLSTAT blocks, preserved as global scalar time series.

Supported blocks contain time, time step and the three core energies and end with
the written time-per-zone-cycle record. Optional energies are never zero-filled.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from .ascii_records import ByteBudgetExceeded, RecordTooLong, bounded_lines, tokenize_scalar
from .lasso_backend import ResultsError

MAX_BYTES = 256 * 1024 * 1024
MAX_RECORD_CHARS = 16_384
MAX_STATES = 1_000_000
COMPONENTS = {"kinetic_energy": "kinetic energy", "internal_energy": "internal energy",
              "total_energy": "total energy", "hourglass_energy": "hourglass energy",
              "time_step": "time step"}
REQUIRED = frozenset(("time", "time_step", "kinetic_energy", "internal_energy", "total_energy"))
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?")


def _number(token):
    try:
        value = float(token.replace("D", "E").replace("d", "e"))
    except ValueError as error:
        raise ResultsError("Invalid ASCII GLSTAT number") from error
    if not math.isfinite(value):
        raise ResultsError("Nonfinite ASCII GLSTAT number")
    if not NUMBER.fullmatch(token):
        raise ResultsError("Invalid ASCII GLSTAT number")
    mantissa = re.split("[eEdD]", token)[0]
    if value == 0 and re.search("[1-9]", mantissa):
        raise ResultsError("ASCII GLSTAT number underflows float64")
    return value


def validate_size(path):
    """Reject oversized text before any caller fingerprints the entire input."""
    if Path(path).stat().st_size > MAX_BYTES:
        raise ResultsError("ASCII GLSTAT input exceeds 256 MiB")


def _lines(path):
    validate_size(path)
    try:
        for line in bounded_lines(path, max_record_chars=MAX_RECORD_CHARS, encoding="utf-8-sig", errors="strict",
                                  max_bytes=MAX_BYTES):
            if line.strip():
                yield line.strip()
    except RecordTooLong as error:
        raise ResultsError("ASCII GLSTAT record exceeds 16384 characters") from error
    except ByteBudgetExceeded as error:
        raise ResultsError("ASCII GLSTAT input exceeds 256 MiB while reading") from error


def read(path, component):
    """Read a single explicit GLSTAT, without sorting, interpolation or unit inference."""
    if component not in COMPONENTS:
        raise ResultsError(f"GLSTAT component must be one of {list(COMPONENTS)}")
    keys = {label: key for key, label in COMPONENTS.items()}
    keys["time"] = "time"
    times, values, original_labels = [], [], {"time": [], component: []}
    current, finished, labels = None, False, set()
    waiting_for_time = False
    headings = []

    def finish():
        if current is None:
            return
        missing = (REQUIRED | {component}) - current.keys()
        if missing:
            raise ResultsError(f"GLSTAT block missing fields: {sorted(missing)}")
        if not finished:
            raise ResultsError("Truncated GLSTAT block: missing time-per-zone-cycle ending")
        if times and current["time"] <= times[-1]:
            raise ResultsError("GLSTAT times must be strictly increasing; no duplicate records")
        if len(times) >= MAX_STATES:
            raise ResultsError("ASCII GLSTAT exceeds one million states")
        times.append(current["time"])
        values.append(current[component])

    for line in _lines(path):
        if finished and line in headings:
            continue
        field = tokenize_scalar(line)
        # Q06 keeps its single-token grammar; suffix-aware lexing does not grant
        # this strict reader nullable/wall-energy semantics.
        if field is None or field.suffix.strip():
            bare_label = " ".join(line.rstrip(".").split()).casefold()
            if bare_label in keys:
                raise ResultsError("Truncated GLSTAT field: missing number")
            if current is not None and not finished:
                raise ResultsError("Malformed GLSTAT block: expected dotted label and number")
            if re.match(r"dt\s+of\s+cycle\b", line, re.I):
                if waiting_for_time:
                    raise ResultsError("Truncated GLSTAT cycle: next cycle heading replaced a missing time block")
                waiting_for_time = True
            elif current is None and len(headings) < 2:
                headings.append(line)
            # Solver title/version, cycle-control headings and optional summary prose.
            continue
        label = field.raw_label
        normalized = " ".join(label.casefold().split())
        key = keys.get(normalized)
        ending = re.fullmatch(r"time per zone cycle\s*\([^()]+\)", normalized.replace(".", ""))
        # Model titles can contain punctuation such as "A. B". Before the first
        # time, those are prose, not unknown numerical fields; retain at most the
        # title/version lines so identical pagination headings remain harmless.
        if current is None and key is None and not ending:
            if len(headings) < 2:
                headings.append(line)
            continue
        if len(label) > 256:
            raise ResultsError("ASCII GLSTAT label exceeds 256 characters")
        value = _number(field.value_token)
        if key == "time":
            finish()
            current, finished, labels = {"time": value}, False, {normalized}
            waiting_for_time = False
        elif key is not None:
            if current is None or finished:
                raise ResultsError("Malformed GLSTAT field outside an active time block")
            if normalized in labels:
                raise ResultsError(f"Duplicate GLSTAT field: {label}")
            current[key] = value
        elif ending:
            if current is None or finished:
                raise ResultsError("Malformed or duplicate GLSTAT block ending")
            missing = (REQUIRED | {component}) - current.keys()
            if missing:
                raise ResultsError(f"GLSTAT block missing fields: {sorted(missing)}")
            finished = True
        elif current is not None and not finished and normalized in labels:
            raise ResultsError(f"Duplicate GLSTAT field: {label}")
        if current is not None and not finished:
            labels.add(normalized)
            if len(labels) > 256:
                raise ResultsError("ASCII GLSTAT block exceeds 256 fields")
        if key in original_labels and label not in original_labels[key]:
            if len(original_labels[key]) >= 64:
                raise ResultsError("ASCII GLSTAT has too many source-label variants")
            original_labels[key].append(label)
    if waiting_for_time:
        raise ResultsError("Truncated GLSTAT cycle heading without a time block")
    finish()
    if not times:
        raise ResultsError("No supported ASCII GLSTAT time blocks")
    return {"backend": "ls-dyna-ascii", "source_format": "glstat", "source_kind": "ascii", "time": times,
            "ids": None, "values": values, "entity_metadata": {"scope": "global"},
            "source_column_names": {"time": original_labels["time"], "value": original_labels[component]},
            "shards": [], "repeated_times_dropped": 0, "warnings": [],
            "merge": "none; one explicit ASCII GLSTAT global history"}
