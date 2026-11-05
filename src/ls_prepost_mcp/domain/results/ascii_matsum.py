"""Q06 MATSUM adapter over the shared Q12 material-record parser.

Accept complete time blocks with the explicitly written core energy fields;
missing requested data is unknown and rejected, never replaced with zero.
"""
from pathlib import Path

from .energy_readers import read_ascii_matsum_details
from .lasso_backend import ResultsError

MAX_BYTES = 256 * 1024 * 1024
MAX_RECORD_CHARS = 16_384
MAX_ROWS = 1_000_000
COMPONENTS = {"kinetic_energy": "kinen", "internal_energy": "inten", "hourglass_energy": "hgeng",
              "eroded_internal_energy": "eroded_ie", "eroded_kinetic_energy": "eroded_ke"}
CORE = frozenset(("kinetic_energy", "internal_energy", "hourglass_energy"))


def validate_size(path):
    if Path(path).stat().st_size > MAX_BYTES:
        raise ResultsError("ASCII MATSUM input exceeds 256 MiB")


def read(path, component):
    """Return one stored named component, with exact mat.# IDs and no merge/fill."""
    if component not in COMPONENTS:
        raise ResultsError(f"MATSUM component must be one of {list(COMPONENTS)}")
    validate_size(path)
    details = read_ascii_matsum_details(path, max_record_chars=MAX_RECORD_CHARS)
    if details["issues"]:
        raise ResultsError(details["issues"][0])
    blocks = details["blocks"]
    if not blocks:
        raise ResultsError("No supported ASCII MATSUM time blocks")
    ids = blocks[0]["ids"]
    times = []
    required = CORE | {component}
    for block in blocks:
        if not block["ids"]:
            raise ResultsError("Empty MATSUM time block; incomplete input")
        if len(set(block["ids"])) != len(block["ids"]):
            raise ResultsError("Duplicate MATSUM part identifier in one time block")
        if set(block["ids"]) != set(ids):
            raise ResultsError("MATSUM part membership changes between time blocks")
        if times and block["time"] <= times[-1]:
            raise ResultsError("MATSUM times must be strictly increasing; no duplicate records")
        if len(times) >= MAX_ROWS or (len(times) + 1) * len(ids) > MAX_ROWS:
            raise ResultsError("ASCII MATSUM exceeds one million part rows")
        for row in block["rows"]:
            missing = required - row.keys()
            if missing:
                raise ResultsError(f"MATSUM missing fields (unknown, not zero): {sorted(missing)}")
        times.append(block["time"])
    parts = details["parts"]
    if any(parts[pid]["time"] != times for pid in ids):
        raise ResultsError("MATSUM part time axes do not align")
    values = [[parts[pid][component][state] for pid in ids] for state in range(len(times))]
    labels = details["source_column_names"]
    return {"backend": "ls-dyna-ascii", "source_format": "matsum", "source_kind": "ascii",
            "time": times, "ids": ids, "values": values,
            "entity_metadata": {"scope": "per_part", "id_source": "literal mat.# identifier",
                                "id_mapping": "as written; no model/material-ID join",
                                "column_order": "first time block"},
            "source_column_names": {"time": labels["time"], "id": labels["id"], "value": labels[component]},
            "shards": [], "repeated_times_dropped": 0, "warnings": [],
            "merge": "none; one explicit ASCII MATSUM; parts joined by written mat.# ID"}
