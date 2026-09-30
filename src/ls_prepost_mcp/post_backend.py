"""Bounded, explicit result selection with user IDs and stored slot semantics."""
import csv
import math
import re
from importlib.metadata import version
from pathlib import Path

from .jobs import fingerprint


def ids(values, name, maximum=100000):
    if not values or len(values) > maximum or any(type(x) is not int or not 1 <= x <= 2_000_000_000 for x in values):
        raise ValueError(f"{name} requires 1..{maximum} positive integers")
    if len(set(values)) != len(values):
        raise ValueError(f"Duplicate {name}")
    return values


def selected_database(path, states, fields):
    import numpy as np
    from lasso.dyna import D3plot
    if version("lasso-python") != "2.0.4":
        raise RuntimeError("Result layout is verified against LASSO 2.0.4")
    ids(states, "states", 10000)
    # Read only time metadata first, then only selected states/fields.
    meta = D3plot(str(path), state_array_filter=["timesteps"], buffered_reading=True)
    times = np.asarray(meta.arrays["timesteps"])
    if max(states) > len(times):
        raise ValueError("State outside database")
    selected = sorted(states)
    db = D3plot(str(path), state_filter={s-1 for s in selected},
                state_array_filter=[*fields, "timesteps"], buffered_reading=True)
    if not np.array_equal(db.arrays["timesteps"], times[[s-1 for s in selected]]):
        raise ValueError("Reader state selection did not match requested time mapping")
    return db, {s: i for i, s in enumerate(selected)}


def result_ids(arrays, domain, count):
    import numpy as np
    key = ("element_" if domain in ("shell", "solid", "tshell", "beam") else "") + domain
    values = np.asarray(arrays[key + "_ids"])
    if values.ndim != 1 or len(set(map(int, values))) != len(values):
        raise ValueError("Invalid/duplicate user IDs")
    if domain == "shell" and count != len(values):
        # Rigid MAT_020 shells have geometry IDs but no stress records.
        parts = np.asarray(arrays["element_shell_part_indexes"])
        materials = np.asarray(arrays["part_material_type"])
        if parts.shape != values.shape or np.any(parts < 0) or np.any(parts >= len(materials)):
            raise ValueError("Cannot map nonrigid shell results")
        values = values[materials[parts] != 20]
    if len(values) != count:
        raise ValueError("Result entity axis cannot be aligned with user IDs")
    return values


def write_csv(path, header, rows, nullable=()):
    count = 0
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            if len(row) != len(header):
                raise ValueError("Result row width mismatch")
            for key, value in zip(header, row):
                if value is None and key in nullable:
                    continue
                if value is None or not math.isfinite(float(value)):
                    raise ValueError("Nonfinite result: " + key)
            writer.writerow(row)
            count += 1
            if count > 1000000:
                raise ValueError("Export exceeds one million rows")
    if count == 0:
        raise ValueError("Empty result export")
    # Validate the saved representation as well as the computed data.
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for key, val in row.items():
                if val == "" and key in nullable:
                    continue
                if not math.isfinite(float(val)):
                    raise ValueError("Invalid saved result")
    return {**fingerprint(path), "kind": "csv", "validated": True, "row_count": count,
            "nullable_columns": sorted(nullable), "null_encoding": "empty field"}


def field_domain(field):
    from lasso.dyna import ArrayType
    if field not in ArrayType.get_state_array_names() or field == "timesteps":
        raise ValueError("Field must be a LASSO state array")
    for domain in ("shell", "solid", "tshell", "beam"):
        if field.startswith("element_" + domain + "_"):
            return domain
    for domain in ("node", "part", "global"):
        if field.startswith(domain + "_"):
            return domain
    raise ValueError("Field domain not supported for ID-safe extraction")


def binout_tokens(branch):
    parts = branch.split("/") if branch else []
    if any(not re.fullmatch(r"[A-Za-z0-9_]+", p) for p in parts):
        raise ValueError("Use slash-separated binout branch names")
    return parts


def ascii_table(path: Path, delimiter, skip_rows, columns):
    """Strict explicit numeric columns; no guessed LS-DYNA ASCII block layouts."""
    if delimiter not in ("whitespace", "comma", "tab") or type(skip_rows) is not int or not 0 <= skip_rows <= 10000:
        raise ValueError("Invalid delimiter/header row count")
    if path.stat().st_size > 256*1024*1024:
        raise ValueError("ASCII input exceeds 256 MiB")
    if not columns or any(type(c) is not int or c < 1 for c in columns):
        raise ValueError("Columns are 1-based positive integers")
    rows = []
    with path.open(encoding="utf-8-sig", errors="strict") as f:
        for line_number, line in enumerate(f, 1):
            if line_number <= skip_rows or not line.strip() or line.lstrip().startswith(("$", "#")):
                continue
            parts = line.split() if delimiter == "whitespace" else next(csv.reader([line], delimiter="," if delimiter == "comma" else "\t"))
            try:
                row = [float(parts[c-1].replace("D", "E").replace("d", "e")) for c in columns]
            except (IndexError, ValueError) as exc:
                raise ValueError(f"Invalid numeric ASCII row {line_number}; block-formatted solver files need a format-specific reader") from exc
            if not all(math.isfinite(x) for x in row):
                raise ValueError(f"Nonfinite ASCII row {line_number}")
            rows.append(row)
            if len(rows) > 1000000:
                raise ValueError("ASCII table exceeds one million rows")
    if not rows:
        raise ValueError("No numeric rows")
    return rows
