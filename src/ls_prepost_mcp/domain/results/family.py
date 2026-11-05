"""Literal d3plot families and the guarded boundary around the locked LASSO reader.

No result values are interpreted here. Prediction mirrors LASSO 2.0.4 discovery without
calling its helper, which stats candidates before callers can authorize them.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from ..model import access
from ..model.includes import is_network

Guard = Callable[[Path], None]
_ACTIVE: ContextVar[FamilyReader | None] = ContextVar("result_family_reader", default=None)


def _digits(text: str) -> bool:
    return bool(text) and all("0" <= character <= "9" for character in text)


def _sdk_continuation(basename: str, candidate: str) -> bool:
    """Linear mirror of the admitted fixed-length subset; never run a user regex."""
    width = len(basename)
    return (len(candidate) > width and _digits(candidate[width:])
            and all(left == "." or left == right for left, right in zip(basename, candidate[:width])))


def _checked(path: Path, guard: Guard) -> None:
    if is_network(str(path)) or PureWindowsPath(str(path)).is_reserved():
        raise ValueError("Network and device result paths are not supported")
    access.require(path)
    if guard is not access.require:
        guard(path)


def _source_path(source: str | Path) -> Path:
    raw = os.fspath(source)
    # Preserve Windows UNC/device syntax before a POSIX Path can prefix its cwd.
    # Classification must remain lexical and precede listing, stat or resolution.
    if is_network(raw) or PureWindowsPath(raw).is_reserved():
        raise ValueError("Network and device result paths are not supported")
    return Path(access.local_path_text(raw)).expanduser().absolute()


def plan_family(source: str | Path, guard: Guard = access.require) -> FamilyPlan:
    """Admit names before stat/read, and refuse SDK/literal discovery disagreements.

LASSO stats every directory entry before testing its regex, so even nonmatching entries
must pass the active root/link guard. This intentionally refuses an unrelated escaping
link in the directory rather than silently allowing the SDK to follow it for metadata.
"""
    source = _source_path(source)
    _checked(source, guard)
    _checked(source.parent, guard)
    if any(character in source.name for character in r"^$*+?{}[]\|()"):
        raise ValueError("Result family basename contains unsupported SDK regex operators")
    if any(ord(character) < 32 or ord(character) == 127 for character in source.name):
        raise ValueError("Result family basename contains unsupported control characters")
    entries = [source.parent / name for name in sorted(os.listdir(source.parent))]
    # Authorize all names before any is_file follows a link, including unrelated entries.
    for candidate in entries:
        _checked(candidate, guard)
        if any(ord(character) < 32 or ord(character) == 127 for character in candidate.name):
            raise ValueError("Result directory contains unsupported control-character names")
    if not source.is_file():
        raise ValueError("Result family main input must be a regular file")
    predicted, expected = [], []
    for candidate in entries:
        _checked(candidate, guard)
        if candidate.is_file():
            if _sdk_continuation(source.name, candidate.name):
                predicted.append(candidate)
            if candidate.name.startswith(source.name) and _digits(candidate.name[len(source.name):]):
                expected.append(candidate)
    if set(predicted) != set(expected):
        raise ValueError("Result family SDK discovery differs from the literal numeric continuation family")
    return FamilyPlan(source, (source, *expected), guard)


@dataclass(frozen=True)
class FamilyPlan:
    source: Path
    paths: tuple[Path, ...]
    guard: Guard

    def same_membership(self) -> None:
        current = plan_family(self.source, self.guard)
        if current.paths != self.paths:
            raise ValueError("Result family membership changed during extraction")

    def capture(self, *, hash_contents: bool = True) -> FamilySnapshot:
        record = _fingerprint if hash_contents else _stat_record
        records = tuple(record(path, self.guard) for path in self.paths)
        self.same_membership()
        return FamilySnapshot(self, records, hash_contents)


def _stat_record(path: Path, guard: Guard) -> dict:
    _checked(path, guard)
    target = str(path.resolve(strict=True))
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Result family contains a non-regular file")
    return dict(path=str(path), resolved_path=target, size_bytes=info.st_size, mtime_ns=info.st_mtime_ns,
                inode=info.st_ino, device=info.st_dev)


def _fingerprint(path: Path, guard: Guard) -> dict:
    """Stream every size; never silently downgrade large continuations to size/mtime."""
    _checked(path, guard)
    target = str(path.resolve(strict=True))
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("Result family contains a non-regular file")
    keys = ("st_size", "st_mtime_ns", "st_ino", "st_dev")
    digest = hashlib.sha256()
    # Raw reads cannot prefetch beyond the initial byte budget. A growing input
    # must not keep a streaming hash chasing EOF indefinitely.
    with path.open("rb", buffering=0) as stream:
        opened = os.fstat(stream.fileno())
        if any(getattr(before, key) != getattr(opened, key) for key in keys):
            raise ValueError("Result family input identity changed between stat and open")
        remaining = before.st_size
        while remaining:
            block = stream.read(min(1024 * 1024, remaining))
            if not block:
                raise ValueError("Result family input was truncated while hashing")
            remaining -= len(block)
            digest.update(block)
        if stream.read(1):
            raise ValueError("Result family input grew while hashing")
        closed = os.fstat(stream.fileno())
        if any(getattr(opened, key) != getattr(closed, key) for key in keys):
            raise ValueError("Result family open input changed while hashing")
    _checked(path, guard)
    after = path.stat()
    if any(getattr(before, key) != getattr(after, key) for key in keys) or str(path.resolve(strict=True)) != target:
        raise ValueError("Result family input changed while hashing")
    return dict(path=str(path), resolved_path=target, size_bytes=after.st_size, mtime_ns=after.st_mtime_ns,
                inode=after.st_ino, device=after.st_dev, sha256=digest.hexdigest())


@dataclass(frozen=True)
class FamilySnapshot:
    plan: FamilyPlan
    records: tuple[dict, ...]
    hashed: bool = True

    def verify(self) -> None:
        self.plan.same_membership()
        record = _fingerprint if self.hashed else _stat_record
        current = tuple(record(path, self.plan.guard) for path in self.plan.paths)
        self.plan.same_membership()
        if current != self.records:
            raise ValueError("Result family changed: input identity changed during extraction")


class FamilyReader:
    def __init__(self, snapshot: FamilySnapshot):
        self.snapshot = snapshot

    def open(self, *, constructor=None, **options):
        if not self.snapshot.hashed:
            fields = options.get("state_array_filter")
            if (not isinstance(fields, (list, tuple, set)) or not fields
                    or {str(getattr(field, "value", field)) for field in fields} - {"timesteps", "global_timesteps"}
                    or set(options) - {"state_array_filter", "buffered_reading"}):
                raise ValueError("Internal state admission permits only timestep metadata; result reads require SHA identity")
        if constructor is None:
            from lasso.dyna import D3plot

            constructor = D3plot
        self.snapshot.plan.same_membership()
        database = constructor(str(self.snapshot.plan.source), **options)
        self.snapshot.plan.same_membership()
        return database


@contextmanager
def _reading_scope(source, guard, snapshot, *, hash_contents):
    source = _source_path(source)
    if snapshot is not None and snapshot.plan.source != source:
        raise ValueError("Result family snapshot belongs to a different source")
    active = _ACTIVE.get()
    if active is not None and active.snapshot.plan.source == source:
        if hash_contents and not active.snapshot.hashed:
            raise ValueError("A metadata admission reader cannot be reused for a strong result operation")
        if snapshot is not None and snapshot.records != active.snapshot.records:
            raise ValueError("Result family active snapshot differs from the requested identity")
        def combined(candidate):
            active.snapshot.plan.guard(candidate)
            if guard is not access.require and guard is not active.snapshot.plan.guard:
                guard(candidate)

        admitted = plan_family(source, combined)
        if admitted.paths != active.snapshot.plan.paths:
            raise ValueError("Result family membership changed during extraction")
        nested = FamilyReader(FamilySnapshot(admitted, active.snapshot.records, active.snapshot.hashed))
        token = _ACTIVE.set(nested)
        try:
            yield nested
        except BaseException as primary:
            try:
                admitted.same_membership()
            except Exception as identity_error:
                primary.add_note("Result family verification also failed: " + str(identity_error))
            raise
        else:
            admitted.same_membership()
        finally:
            _ACTIVE.reset(token)
        return
    if snapshot is not None:
        original = snapshot

        def combined(candidate):
            original.plan.guard(candidate)
            if guard is not access.require and guard is not original.plan.guard:
                guard(candidate)

        admitted = plan_family(source, combined)
        if admitted.paths != original.plan.paths:
            raise ValueError("Result family membership changed during extraction")
        snapshot = FamilySnapshot(admitted, original.records, original.hashed)
    else:
        snapshot = plan_family(source, guard).capture(hash_contents=hash_contents)
    reader = FamilyReader(snapshot)
    token = _ACTIVE.set(reader)
    try:
        yield reader
    except BaseException as primary:
        try:
            snapshot.verify()
        except Exception as identity_error:
            primary.add_note("Result family verification also failed: " + str(identity_error))
        raise
    else:
        snapshot.verify()
    finally:
        _ACTIVE.reset(token)


@contextmanager
def reading_family(source: str | Path, *, guard: Guard = access.require,
                   snapshot: FamilySnapshot | None = None) -> Iterator[FamilyReader]:
    """One before/after SHA pass for any number of SDK reads in the operation scope."""
    if snapshot is not None and not snapshot.hashed:
        raise ValueError("A metadata admission snapshot cannot certify a result operation")
    with _reading_scope(source, guard, snapshot, hash_contents=True) as reader:
        yield reader


@contextmanager
def _state_admission(source):
    """Internal only: state budget admission, never result/CSV evidence or force data."""
    with _reading_scope(source, access.require, None, hash_contents=False) as reader:
        yield reader


def open_d3plot(source: str | Path, *, constructor=None, guard: Guard = access.require, **options):
    """Guard a standalone SDK construction; operation callers can share reading_family."""
    with reading_family(source, guard=guard) as reader:
        return reader.open(constructor=constructor, **options)
