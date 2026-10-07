"""Binout databases across MPP shards (tasks.yaml Q06).

LS-DYNA MPP writes one binout per rank that has output (binout0000, binout0004, ...); size
continuations (binout%001, ...) belong to their base file and lasso opens them with it. lasso's
glob reader puts all shards into one symbol tree in file-name order, so an entry stored in two
shards keeps only the later file's copy, state directory by state directory: two ranks that
both start their state directories at d000001 lose the earlier rank's samples without notice.

Here every shard is read on its own. An entry (a database, or a branch of a nested one such as
elout/shell or jntforc/type0) found in one shard is read from that shard alone. Found in several,
the pieces are merged only when their entity metadata (``ids``, ``side``, ``*_ids``) are
identical: the time samples are united and a time stored in several pieces must carry identical
values. Anything else is refused; ``shard=`` reads one file explicitly.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from .lasso_backend import ResultsError, _lasso, backend

SHARD = re.compile(r"^binout(\d{4})?$")
FAMILY = re.compile(r"^binout(\d{4})?(%\d{2,})?$")  # a shard and its size continuations
GLOB_CHARACTERS = frozenset("*?[")
MAX_DEPTH = 4


def shards(path: str | Path) -> list[Path]:
    """Binout files beside ``path`` (a binout file or its folder): binout and binoutNNNN."""
    path = Path(path)
    folder = path if path.is_dir() else path.parent
    if not folder.is_dir():
        raise ResultsError(f"{folder} does not exist")
    found = sorted(f for f in folder.iterdir() if f.is_file() and SHARD.match(f.name))
    if not found:
        raise ResultsError(f"No binout files in {folder}")
    return found


def _open(Binout: type, file: Path) -> object:
    """lasso's Binout and Lsda treat the file name as a glob pattern (the file itself and its
    ``%NNN`` continuations), so ``case[1]/binout`` would read ``case1/binout``. Paths with glob
    characters are refused, and the files lasso actually opened must be this shard or its own
    continuations in the same folder."""
    if GLOB_CHARACTERS & set(str(file)):
        raise ResultsError(f"Binout paths containing *, ? or [ are not read (lasso treats them as glob "
                           f"patterns): {file}")
    reader = Binout(str(file))
    opened = [Path(f.name) for f in getattr(getattr(reader, "lsda", None), "files", [])]
    stray = [str(f) for f in opened if f.parent != file.parent
             or not (f.name == file.name or re.fullmatch(re.escape(file.name) + r"%\d{2,}", f.name))]
    if not opened or stray:
        raise ResultsError(f"lasso opened files other than {file.name} and its continuations: {stray}")
    return reader


def _entries(reader: object) -> dict[str, tuple[str, ...]]:
    """Levels holding variables, by path: ``{"glstat": ("glstat",), "elout/shell": ("elout", "shell"),
    "bndout/velocity/nodes": (...)}``. lasso lists a level either as subdirectories or, when it
    has metadata, as its variables; a level is descended while its first name is a directory."""
    out: dict[str, tuple[str, ...]] = {}

    def walk(location: tuple[str, ...]) -> None:
        names = list(reader.read(*location))
        if names and "time" not in names and len(location) < MAX_DEPTH \
                and isinstance(reader.read(*location, names[0]), list):
            for name in names:
                walk((*location, name))
        elif names:
            out["/".join(location)] = location

    for database in reader.read():
        walk((database,))
    return out


def catalog(path: str | Path) -> dict:
    """Shard files, each entry with the shards holding it, and the entries split over shards."""
    _, Binout, _ = _lasso()
    files = shards(path)
    where: dict[str, list[str]] = {}
    for file in files:
        for key in _entries(_open(Binout, file)):
            where.setdefault(key, []).append(file.name)
    return {"shards": [f.name for f in files], "entries": dict(sorted(where.items())),
            "split": {k: v for k, v in sorted(where.items()) if len(v) > 1}}


def _identity(names: list[str]) -> list[str]:
    return sorted(n for n in names if n == "side" or n.endswith("ids"))


def _piece(name: str, reader: object, location: tuple[str, ...], component: str) -> dict:
    names = reader.read(*location)
    if component not in names:
        raise ResultsError(f"{'/'.join(location)} has no {component!r}; available: {sorted(names)}")
    if "time" not in names:
        raise ResultsError(f"{'/'.join(location)} in {name} has no time samples")
    time = np.asarray(reader.read(*location, "time"), dtype=float).reshape(-1)
    try:
        values = np.asarray(reader.read(*location, component), dtype=float)
    except (TypeError, ValueError) as error:
        raise ResultsError(f"{component!r} is not a time series (not numeric)") from error
    if values.shape[:1] != time.shape:
        raise ResultsError(f"{component!r} is not a time series ({values.shape} values, {time.size} times)")
    identity = {key: np.asarray(reader.read(*location, key)) for key in _identity(names)}
    return {"shard": name, "time": time, "values": values, "identity": identity}


def _merge(key: str, pieces: list[dict]) -> tuple[np.ndarray, np.ndarray, int]:
    """United time samples of pieces with identical entities; equal values where times repeat."""
    first = pieces[0]["identity"]
    for piece in pieces[1:]:
        other = piece["identity"]
        if other.keys() != first.keys() or any(not np.array_equal(other[k], first[k]) for k in first):
            raise ResultsError(f"{key} is stored in shards {[p['shard'] for p in pieces]} with different "
                               "entities; read one shard with shard=")
    time = np.concatenate([p["time"] for p in pieces])
    values = np.concatenate([p["values"] for p in pieces])
    order = np.argsort(time, kind="stable")
    time, values = time[order], values[order]
    repeat = np.flatnonzero(np.diff(time) == 0) + 1
    for i in repeat:
        if not np.array_equal(values[i], values[i - 1], equal_nan=True):
            gap = float(np.nanmax(np.abs(values[i] - values[i - 1])))
            raise ResultsError(f"{key}: time {time[i]:g} is stored in several shards with different values "
                               f"(max |difference| {gap:g})")
    keep = np.ones(time.size, dtype=bool)
    keep[repeat] = False
    return time[keep], values[keep], int(repeat.size)


def read(path: str | Path, database: str, component: str, branch: str | None = None,
         shard: str | None = None) -> dict:
    """One component of a binout database (or branch, e.g. ``shell`` or ``velocity/nodes``) over
    the shard set, merged as documented."""
    _, Binout, _ = _lasso()
    files = shards(path)
    if shard is not None:
        files = [f for f in files if f.name == shard]
        if not files:
            raise ResultsError(f"No shard named {shard!r}")
    key = database if branch is None else f"{database}/{branch}"
    pieces, available = [], set()
    for file in files:
        reader = _open(Binout, file)
        entries = _entries(reader)
        available |= entries.keys()
        if key in entries:
            pieces.append(_piece(file.name, reader, entries[key], component))
    if not pieces:
        branches = sorted(k for k in available if k.startswith(database + "/"))
        hint = f"; give branch= one of {[b.split('/', 1)[1] for b in branches]}" if branches and branch is None else ""
        raise ResultsError(f"No {key!r} in the binout files{hint}; available: {sorted(available)}")
    if len(pieces) == 1:
        time, values, repeated = pieces[0]["time"], pieces[0]["values"], 0
    else:
        time, values, repeated = _merge(key, pieces)
    identity = pieces[0]["identity"]
    return {"backend": backend(), "database": database, "branch": branch, "component": component,
            "time": time.tolist(), "values": values.tolist(),
            "ids": identity["ids"].reshape(-1).tolist() if "ids" in identity else None,
            "entity_metadata": {k: v.reshape(-1).tolist() for k, v in identity.items() if k != "ids"},
            "shards": [p["shard"] for p in pieces], "repeated_times_dropped": repeated}


__all__ = ["FAMILY", "SHARD", "catalog", "read", "shards"]
