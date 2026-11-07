"""Q06 literal SLEOUT interface energies; summaries are syntax-checked only.

Supported column layouts are slave/master/frictional and surfa/surfb/frictional.
The aliases name written positions, without certifying keyword/UI identities or
combining sides, applying validity masks, or calculating energy conservation.
Only non-row-like prose and optional legend records are supported as preamble;
ambiguous numeric titles/orphan records are rejected rather than distinguished.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from .lasso_backend import ResultsError

MAX_BYTES = 256 * 1024 * 1024
MAX_RECORD_CHARS = 16_384
MAX_ROWS = 1_000_000
COMPONENTS = {"side_a_energy": 0, "side_b_energy": 1, "frictional_energy": 2}
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eEdD][+-]?[0-9]+)?")
TIME = re.compile(r"contact\s+interface\s+energy\s+file,\s*time\s*=\s*(\S+)", re.I)
HEADER = re.compile(r"#\s+(\S+)\s+(\S+)\s+cycle\s*=\s*([0-9]+)\s+(\S+)", re.I)
LAYOUTS = {("slave", "master", "frictional"): ("slave", "mastr"),
           ("surfa", "surfb", "frictional"): ("surfa", "surfb")}


def _number(token):
    if not NUMBER.fullmatch(token):
        raise ResultsError("Invalid SLEOUT numeric field")
    value = float(token.replace("D", "E").replace("d", "e"))
    if not math.isfinite(value):
        raise ResultsError("Nonfinite SLEOUT numeric field")
    if value == 0 and re.search("[1-9]", re.split("[eEdD]", token)[0]):
        raise ResultsError("SLEOUT numeric field underflows float64")
    return value


def validate_size(path):
    if Path(path).stat().st_size > MAX_BYTES:
        raise ResultsError("ASCII SLEOUT input exceeds 256 MiB")


def read(path, component):
    """Read one bounded explicit source, without opening a binary/model companion."""
    from .ascii_records import ByteBudgetExceeded, RecordTooLong, bounded_lines

    validate_size(path)
    try:
        return parse(bounded_lines(path, max_record_chars=MAX_RECORD_CHARS, max_bytes=MAX_BYTES,
                                   encoding="utf-8-sig", errors="strict"), component)
    except RecordTooLong as error:
        raise ResultsError("ASCII SLEOUT record exceeds 16384 characters") from error
    except ByteBudgetExceeded as error:
        raise ResultsError("ASCII SLEOUT input exceeds 256 MiB while reading") from error


def parse(lines, component):
    """Require complete frames; preserve first-frame raw ID order and literal values."""
    if component not in COMPONENTS:
        raise ResultsError(f"SLEOUT component must be one of {list(COMPONENTS)}")
    column = COMPONENTS[component]
    times, ids, values, source_labels = [], [], [], []
    current, legend, row_count = None, False, 0

    def finish():
        if current is None:
            return
        if current["labels"] is None:
            raise ResultsError("SLEOUT time block missing its complete column header")
        if not current["rows"] or current["summary"] != 4:
            raise ResultsError("Empty or truncated SLEOUT table/summary")
        if times and current["time"] <= times[-1]:
            raise ResultsError("SLEOUT times must be strictly increasing")
        if not ids:
            ids.extend(current["rows"])
        elif set(current["rows"]) != set(ids):
            raise ResultsError("SLEOUT interface membership changes between time blocks")
        times.append(current["time"])
        values.append([current["rows"][identity][column] for identity in ids])

    for line in lines:
        text = line.strip()
        if not text:
            continue
        if "{BEGIN LEGEND}" in text:
            if text != "{BEGIN LEGEND}" or legend or current is not None:
                raise ResultsError("Malformed, nested or misplaced SLEOUT legend")
            legend = True
            continue
        if "{END LEGEND}" in text:
            if text != "{END LEGEND}" or not legend:
                raise ResultsError("Malformed or unmatched SLEOUT legend ending")
            legend = False
            continue
        if legend:
            continue
        normalized = " ".join(text.casefold().split())
        if normalized.startswith("contact interface energy"):
            header = TIME.fullmatch(text)
            if header is None:
                raise ResultsError("Malformed or truncated SLEOUT time header")
            finish()
            current = dict(time=_number(header[1]), labels=None, rows={}, summary=0)
            continue
        if current is None:
            tokens = text.split()
            # Numeric-leading preamble is ambiguous with an orphan ID/row and
            # is rejected regardless of column count, rather than guessed to
            # be a model title. Also reserve damaged IDs followed by scalars.
            row_like = (NUMBER.fullmatch(tokens[0]) is not None or tokens[0][0] in "+-*0123456789"
                        or tokens[0].casefold() in ("nan", "inf", "infinity")
                        or (len(tokens) > 1 and all(NUMBER.fullmatch(token) for token in tokens[1:])))
            if text.startswith("#") or normalized.startswith(("summary", "total ", "friction energy")) or row_like:
                raise ResultsError("Unsupported SLEOUT preamble/table syntax outside an active time block")
            continue
        if text.startswith("#"):
            header = HEADER.fullmatch(text)
            if current["labels"] is not None or header is None:
                raise ResultsError("Duplicate or incomplete SLEOUT column header")
            labels = (header[1], header[2], header[4])
            layout = tuple(label.casefold() for label in labels)
            if layout not in LAYOUTS:
                raise ResultsError("Unsupported SLEOUT column header")
            current["labels"] = layout
            label = labels[column]
            if label not in source_labels:
                if len(source_labels) >= 16:
                    raise ResultsError("Too many SLEOUT source label variants")
                source_labels.append(label)
            continue
        if current["labels"] is None:
            raise ResultsError("SLEOUT record before its complete column header")
        if normalized.startswith(("summary", "total ", "friction energy")) or current["summary"]:
            index = current["summary"]
            if not current["rows"] or index >= 4:
                raise ResultsError("Empty SLEOUT table or duplicate summary")
            left, right = LAYOUTS[current["labels"]]
            labels = (rf"summary\s+total\s+{left}\s+side", rf"total\s+{right}\s+side",
                      r"total\s+energy", r"friction\s+energy")
            summary = re.fullmatch(labels[index] + r"\s*=\s*(\S+)", text, re.I)
            if summary is None:
                raise ResultsError("Malformed or incomplete SLEOUT summary")
            _number(summary[1])  # Complete numeric syntax only; no conservation calculation.
            current["summary"] += 1
            continue
        fields = text.split()
        if len(fields) != 4:
            raise ResultsError("Malformed or truncated SLEOUT interface row")
        if not re.fullmatch(r"[0-9]+", fields[0]) or int(fields[0]) <= 0:
            raise ResultsError("SLEOUT needs a positive printed interface ID")
        identity = int(fields[0])
        if identity in current["rows"]:
            raise ResultsError("Duplicate SLEOUT interface ID in one time block")
        row_values = [_number(token) for token in fields[1:]]
        row_count += 1
        if row_count > MAX_ROWS:
            raise ResultsError("ASCII SLEOUT exceeds one million interface rows")
        current["rows"][identity] = row_values
    if legend:
        raise ResultsError("Truncated SLEOUT legend")
    finish()
    if not times:
        raise ResultsError("No supported ASCII SLEOUT time blocks")
    return dict(backend="ls-dyna-ascii", source_kind="ascii", source_format="sleout", time=times,
                ids=ids, values=values,
                entity_metadata=dict(scope="per_interface", id_source="printed raw interface ID",
                                     id_mapping="as written; keyword/UI identity not independently certified",
                                     column_order="first complete time block", validity="raw_unmasked",
                                     alive_mask_available=False, deletion_validity="unknown",
                                     summary_records_validated=4*len(times), summary_exported=False,
                                     summary_validation="complete grammar only; no conservation calculation"),
                source_column_names=dict(time=["time"], id=["#"], value=source_labels),
                shards=[], repeated_times_dropped=0,
                warnings=["ASCII SLEOUT has no alive/deletion mask; raw/unmasked curves have unknown deletion validity"],
                merge="none; one explicit ASCII SLEOUT; raw interface IDs joined literally; no side merge")
