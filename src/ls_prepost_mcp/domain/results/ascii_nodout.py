"""Q06 fixed-width NODOUT translation fields, without nodal calculations.

Accepted tables have an I10 printed node ID and E12 fields: twelve translation
columns, optionally paired with nine rotation columns at the same step/time.
Rotation is validated for completeness only, never exported as a translation.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from .lasso_backend import ResultsError

MAX_BYTES = 256 * 1024 * 1024
MAX_RECORD_CHARS = 16_384
MAX_ROWS = 1_000_000
TRANSLATION = "nodal point x-disp y-disp z-disp x-vel y-vel z-vel x-accl y-accl z-accl x-coor y-coor z-coor"
ROTATION = "nodal point x-rot y-rot z-rot x-rot vel y-rot vel z-rot vel x-rot acc y-rot acc z-rot acc"
COMPONENTS = {f"{axis}_{quantity}": (offset+i, f"{axis}-{raw}")
              for quantity, offset, raw in [("displacement", 0, "disp"), ("velocity", 3, "vel"),
                                             ("acceleration", 6, "accl")]
              for i, axis in enumerate("xyz")}
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eEdD][+-]?[0-9]+)?")
IMPLICIT_EXPONENT = re.compile(r"([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))([+-][0-9]{3})")


def _spaced_label(text):
    return r"[ \t]*".join(re.escape(letter) for letter in text)


TIME_PREFIX = re.compile(_spaced_label("nodalprintout"), re.I)
TIME_RECORD_PREFIX = re.compile(_spaced_label("nodalprintoutfortimestep") + r"(?=$|[ \t(0-9])", re.I)
TIME_HEADER = re.compile(_spaced_label("nodalprintoutfortimestep") +
                         r"[ \t]+([0-9]+)[ \t]*\([ \t]*at[ \t]+time[ \t]+(\S+)[ \t]*\)", re.I)


def _number(token):
    normalized = token
    if not NUMBER.fullmatch(normalized):
        implicit = IMPLICIT_EXPONENT.fullmatch(normalized)
        if implicit is None:
            raise ResultsError("Invalid NODOUT numeric field")
        normalized = implicit[1] + "e" + implicit[2]
    value = float(normalized.replace("D", "E").replace("d", "e"))
    if not math.isfinite(value):
        raise ResultsError("Nonfinite NODOUT numeric field")
    if value == 0 and re.search("[1-9]", re.split("[eEdD]", normalized)[0]):
        raise ResultsError("NODOUT numeric field underflows float64")
    return value


def validate_size(path):
    if Path(path).stat().st_size > MAX_BYTES:
        raise ResultsError("ASCII NODOUT input exceeds 256 MiB")


def read(path, component):
    """Use the shared bounded source reader; it must supply the explicit byte budget API."""
    from .ascii_records import ByteBudgetExceeded, RecordTooLong, bounded_lines

    validate_size(path)
    try:
        return parse(bounded_lines(path, max_record_chars=MAX_RECORD_CHARS, max_bytes=MAX_BYTES,
                                   encoding="utf-8-sig", errors="strict"), component)
    except RecordTooLong as error:
        raise ResultsError("ASCII NODOUT record exceeds 16384 characters") from error
    except ByteBudgetExceeded as error:
        raise ResultsError("ASCII NODOUT input exceeds 256 MiB while reading") from error


def parse(lines, component):
    """Parse literal tables only: no sorting, interpolation, coordinate subtraction or ID join."""
    if component not in COMPONENTS:
        raise ResultsError(f"NODOUT component must be one of {list(COMPONENTS)}")
    column, _ = COMPONENTS[component]
    tables, current, row_count, legend = [], None, 0, False
    preamble, source_labels = set(), []

    def finish():
        if current is None:
            return
        if current["kind"] is None:
            raise ResultsError("NODOUT time block missing its complete column header")
        if not current["rows"]:
            raise ResultsError("Empty or truncated NODOUT table")
        tables.append(current)

    def fixed_row_shape(raw):
        # Reserve the physical I10+E12 slots before asking whether their contents
        # are valid. A NaN/negative ID/overflow marker must not turn a damaged
        # orphan record into an innocuous model title.
        raw = raw.rstrip("\r\n")
        for width in (9, 12):
            end = 10+12*width
            if len(raw) >= end and not raw[end:].strip():
                return True
        return False

    for line in lines:
        text = line.strip()
        if not text:
            continue
        if "{BEGIN LEGEND}" in text:
            if text != "{BEGIN LEGEND}":
                raise ResultsError("Malformed NODOUT legend record")
            if legend:
                raise ResultsError("Nested NODOUT legend")
            legend = True
            continue
        if "{END LEGEND}" in text:
            if text != "{END LEGEND}":
                raise ResultsError("Malformed NODOUT legend record")
            if not legend:
                raise ResultsError("Unmatched NODOUT legend ending")
            legend = False
            continue
        if legend:
            continue
        normalized = " ".join(text.casefold().split())
        if current is not None and text in preamble and text[0] not in "+-*0123456789":
            continue
        if (TIME_RECORD_PREFIX if current is None else TIME_PREFIX).match(text):
            # Whitespace flexibility belongs to the label, never the numeric
            # tokens: '0 .1', '1E -3' and a split step ID are not rewrites of data.
            header = TIME_HEADER.fullmatch(text)
            if header is None:
                raise ResultsError("Malformed or truncated NODOUT time/step header")
            finish()
            current = dict(time=_number(header[2]), step=int(header[1]), kind=None, rows={})
            continue
        if current is None:
            # The preface can contain a node-like word or a purely numeric model
            # title. Reserve complete table syntax, not loose word prefixes.
            if normalized in (TRANSLATION, ROTATION) or fixed_row_shape(line):
                raise ResultsError("NODOUT complete table syntax outside an active time block")
            if len(preamble) < 16:
                preamble.add(text)
            continue
        if normalized.startswith("nodal point"):
            if current is None or current["kind"] is not None:
                raise ResultsError("NODOUT duplicate column header or header without a time block")
            if normalized not in (TRANSLATION, ROTATION):
                raise ResultsError("Unsupported or truncated NODOUT column header")
            current["kind"] = "translation" if normalized == TRANSLATION else "rotation"
            if current["kind"] == "translation":
                original = text.split()[2+column]
                if original not in source_labels:
                    if len(source_labels) >= 16:
                        raise ResultsError("Too many NODOUT source label variants")
                    source_labels.append(original)
            continue
        if current["kind"] is None:
            raise ResultsError("NODOUT record before its column header")
        width = 12 if current["kind"] == "translation" else 9
        raw = line.rstrip("\r\n")
        expected = 10 + 12*width
        if "\t" in raw or len(raw) < expected or raw[expected:].strip():
            raise ResultsError("Malformed or truncated fixed-width NODOUT row")
        identity = raw[:10].strip()
        if not re.fullmatch(r"[0-9]+", identity) or int(identity) <= 0:
            raise ResultsError("NODOUT needs a positive printed node ID")
        node = int(identity)
        if node in current["rows"]:
            raise ResultsError("Duplicate NODOUT node ID in one table")
        values = [_number(raw[10+12*i:22+12*i].strip()) for i in range(width)]
        row_count += 1
        if row_count > MAX_ROWS:
            raise ResultsError("NODOUT exceeds one million total table rows")
        current["rows"][node] = values
    if legend:
        raise ResultsError("Truncated NODOUT legend")
    finish()
    translation = [t for t in tables if t["kind"] == "translation"]
    if not translation:
        raise ResultsError("No NODOUT translation tables")
    times = [t["time"] for t in translation]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ResultsError("NODOUT translation times must be strictly increasing")
    ids = list(translation[0]["rows"])
    if any(set(t["rows"]) != set(ids) for t in translation):
        raise ResultsError("NODOUT node membership changes between translation tables")
    rotations = [t for t in tables if t["kind"] == "rotation"]
    if rotations:
        if len(tables) != 2*len(translation):
            raise ResultsError("Incomplete or duplicated NODOUT translation/rotation pairs")
        for index, trans in enumerate(translation):
            rot = tables[2*index+1]
            if (tables[2*index] is not trans or rot["kind"] != "rotation"
                    or (trans["step"], trans["time"]) != (rot["step"], rot["time"])
                    or set(rot["rows"]) != set(ids)):
                raise ResultsError("NODOUT rotation table does not completely match its translation frame")
    return dict(backend="ls-dyna-ascii", source_kind="ascii", source_format="nodout", time=times, ids=ids,
                values=[[t["rows"][node][column] for node in ids] for t in translation],
                entity_metadata=dict(scope="per_node", id_source="printed nodal point ID",
                                     column_order="first translation table", frame="as written; no transform",
                                     rotation_tables_validated=len(rotations), rotation_exported=False,
                                     validity="raw_unmasked", alive_mask_available=False,
                                     deletion_validity="unknown",
                                     solver_step_range=[translation[0]["step"], translation[-1]["step"]]),
                source_column_names=dict(time=["at time"], id=["nodal point"], value=source_labels),
                shards=[], repeated_times_dropped=0,
                warnings=["ASCII NODOUT has no alive/deletion mask; raw/unmasked curves have unknown deletion validity"],
                merge="none; one explicit ASCII NODOUT; node IDs joined literally")
