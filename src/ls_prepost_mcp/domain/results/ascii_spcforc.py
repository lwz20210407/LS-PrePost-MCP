"""Q06 literal SPCFORC local force/moment vectors, without a frame transform.

The printed node ID is the entity key. setid is retained as a raw reference,
never interpreted as a coordinate-system ID. Force resultants are checked for
complete syntax only, without exporting or using them for conservation checks.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from .lasso_backend import ResultsError

MAX_BYTES = 256 * 1024 * 1024
MAX_RECORD_CHARS = 16_384
MAX_ROWS = 1_000_000
COMPONENTS = {f"{axis}_{quantity}": (kind, index)
              for quantity, kind in (("force", "forces"), ("moment", "moments"))
              for index, axis in enumerate("xyz")}
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eEdD][+-]?[0-9]+)?")
TIME = re.compile(r"(output\s+at\s+time)\s*=\s*(\S+)", re.I)
NODE = re.compile(r"(node\s*=)\s*([0-9]+)\s+(local\s+x\s*,\s*y\s*,\s*z\s+(forces|moments))"
                  r"\s*=\s*(\S+)\s+(\S+)\s+(\S+)\s+(setid\s*=)\s*([0-9]+)", re.I)
SUMMARY = re.compile(r"force\s+resultants\s*=\s*(\S+)\s+(\S+)\s+(\S+)", re.I)


def _number(token):
    if not NUMBER.fullmatch(token):
        raise ResultsError("Invalid or unsupported SPCFORC numeric field")
    value = float(token.replace("D", "E").replace("d", "e"))
    if not math.isfinite(value):
        raise ResultsError("Nonfinite SPCFORC numeric field")
    if value == 0 and re.search("[1-9]", re.split("[eEdD]", token)[0]):
        raise ResultsError("SPCFORC numeric field underflows float64")
    return value


def validate_size(path):
    if Path(path).stat().st_size > MAX_BYTES:
        raise ResultsError("ASCII SPCFORC input exceeds 256 MiB")


def read(path, component):
    """Read one bounded explicit file; no binary/model companion or optional LASSO read."""
    from .ascii_records import ByteBudgetExceeded, RecordTooLong, bounded_lines

    validate_size(path)
    try:
        return parse(bounded_lines(path, max_record_chars=MAX_RECORD_CHARS, max_bytes=MAX_BYTES,
                                   encoding="utf-8-sig", errors="strict"), component)
    except RecordTooLong as error:
        raise ResultsError("ASCII SPCFORC record exceeds 16384 characters") from error
    except ByteBudgetExceeded as error:
        raise ResultsError("ASCII SPCFORC input exceeds 256 MiB while reading") from error


def parse(lines, component):
    """Require stable complete frames; join literal node IDs in first-force-row order."""
    if component not in COMPONENTS:
        raise ResultsError(f"SPCFORC component must be one of {list(COMPONENTS)}")
    requested, column = COMPONENTS[component]
    times, ids, values, source_labels, time_labels = [], [], [], [], []
    references, raw_nodes, raw_sets = {}, {}, {}
    current, legend, row_count, moment_mode = None, False, 0, None

    def remember(collection, key, token):
        variants = collection.setdefault(key, [])
        if token not in variants:
            if len(variants) >= 16:
                raise ResultsError("Too many SPCFORC raw source label/ID variants")
            variants.append(token)

    def finish():
        nonlocal moment_mode
        if current is None:
            return
        forces, moments = current["forces"], current["moments"]
        if not forces or not current["summary"]:
            raise ResultsError("Empty or truncated SPCFORC frame/force resultants")
        has_moments = bool(moments)
        if has_moments and set(moments) != set(forces):
            raise ResultsError("SPCFORC force/moment node pairs are incomplete")
        if moment_mode is None:
            moment_mode = has_moments
        elif moment_mode != has_moments:
            raise ResultsError("SPCFORC force/moment record mode changes between frames")
        if times and current["time"] <= times[-1]:
            raise ResultsError("SPCFORC times must be strictly increasing")
        if not ids:
            ids.extend(forces)
        elif set(forces) != set(ids):
            raise ResultsError("SPCFORC node membership changes between frames")
        if requested == "moments" and not has_moments:
            raise ResultsError("SPCFORC requested moment component is not stored; missing values are unknown")
        times.append(current["time"])
        values.append([current[requested][node][column] for node in ids])

    for line in lines:
        text = line.strip()
        if not text:
            continue
        if "{BEGIN LEGEND}" in text:
            if text != "{BEGIN LEGEND}" or legend or current is not None:
                raise ResultsError("Malformed, nested or misplaced SPCFORC legend")
            legend = True
            continue
        if "{END LEGEND}" in text:
            if text != "{END LEGEND}" or not legend:
                raise ResultsError("Malformed or unmatched SPCFORC legend ending")
            legend = False
            continue
        if legend:
            continue
        normalized = " ".join(text.casefold().split())
        if normalized.startswith("output"):
            header = TIME.fullmatch(text)
            if header is None:
                raise ResultsError("Malformed or unsupported SPCFORC time header")
            finish()
            if header[1] not in time_labels:
                if len(time_labels) >= 16:
                    raise ResultsError("Too many SPCFORC time label variants")
                time_labels.append(header[1])
            current = dict(time=_number(header[2]), forces={}, moments={}, summary=False)
            continue
        if current is None:
            tokens = text.split()
            row_like = (tokens[0][0] in "+-*0123456789" or tokens[0][0].isdigit()
                        or tokens[0].casefold() in ("nan", "inf", "infinity")
                        or NUMBER.fullmatch(tokens[0]) is not None
                        or (len(tokens) > 1 and all(NUMBER.fullmatch(token) for token in tokens[1:])))
            if normalized.startswith(("node", "force resultants", "local ", "setid", "forces", "moments")) or row_like:
                raise ResultsError("Unsupported SPCFORC preamble/table syntax outside an active time block")
            continue
        summary = SUMMARY.fullmatch(text)
        if summary is not None:
            if current["summary"] or not current["forces"]:
                raise ResultsError("Duplicate SPCFORC force resultants or summary before node forces")
            [_number(token) for token in summary.groups()]  # Grammar only; no conservation calculation.
            current["summary"] = True
            continue
        if current["summary"]:
            raise ResultsError("Unsupported SPCFORC record after force resultants")
        record = NODE.fullmatch(text)
        if record is None:
            raise ResultsError("Malformed or unsupported SPCFORC node/force resultants record")
        node, setid, kind = int(record[2]), int(record[9]), record[4].casefold()
        if node <= 0:
            raise ResultsError("SPCFORC needs a positive printed node ID")
        if node in references and references[node] != setid:
            raise ResultsError("Unsupported SPCFORC node with changing or multiple setid references")
        references[node] = setid
        if node in current[kind]:
            raise ResultsError("Duplicate SPCFORC node/setid/record kind in one frame")
        vector = [_number(record[index]) for index in (5, 6, 7)]
        row_count += 1
        if row_count > MAX_ROWS:
            raise ResultsError("ASCII SPCFORC exceeds one million node vector rows")
        current[kind][node] = vector
        remember(raw_nodes, node, record[2])
        remember(raw_sets, node, record[9])
        if kind == requested and record[3] not in source_labels:
            if len(source_labels) >= 16:
                raise ResultsError("Too many SPCFORC vector label variants")
            source_labels.append(record[3])
    if legend:
        raise ResultsError("Truncated SPCFORC legend")
    finish()
    if not times:
        raise ResultsError("No supported ASCII SPCFORC time blocks")
    return dict(backend="ls-dyna-ascii", source_kind="ascii", source_format="spcforc", time=times,
                ids=ids, values=values,
                entity_metadata=dict(scope="per_node", id_source="printed raw node ID",
                                     id_mapping="as written; keyword/UI identity not independently certified",
                                     column_order="first force table", raw_node_id_tokens=[raw_nodes[n] for n in ids],
                                     setid=[references[n] for n in ids], raw_setid_tokens=[raw_sets[n] for n in ids],
                                     setid_interpretation="printed reference only; not a coordinate-system ID",
                                     frame="local as printed; basis unidentified; no transform",
                                     record_kind=requested, component_axis="xyz"[column], component_index=column,
                                     moment_records_available=moment_mode, node_vector_rows_validated=row_count,
                                     validity="raw_unmasked", alive_mask_available=False, deletion_validity="unknown",
                                     summary_records_validated=len(times), summary_exported=False,
                                     summary_validation="complete grammar only; no conservation calculation"),
                source_column_names=dict(time=time_labels, id=["node="], setid=["setid="], value=source_labels),
                shards=[], repeated_times_dropped=0,
                warnings=["ASCII SPCFORC local basis is unidentified; setid is only a printed reference",
                          "ASCII SPCFORC has no alive/deletion mask; raw/unmasked curves have unknown deletion validity"],
                merge="none; one explicit ASCII SPCFORC; raw node IDs joined literally; no setid or kind merge")
