"""Optional confinement of every path the keyword engine stats or reads for an Include tree.

Callers that serve untrusted decks (the M3 MCP tools) run engine calls inside ``confined(check)``;
``check(path)`` raises :class:`OutsideRoots` for a path that may not be touched. The engine calls
:func:`require` before it stats or reads an include candidate, an include file, an opaque target
or a search directory, so neither the deck, nor an edit that adds an ``*INCLUDE``, nor the reload
after saving can reach other files or contact a UNC host. Without an active guard nothing changes.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path


class OutsideRoots(PermissionError):
    """A path that the active guard does not allow."""


_GUARD: ContextVar[Callable[[Path], None] | None] = ContextVar("keyword_engine_guard", default=None)


@contextmanager
def confined(check: Callable[[Path], None]) -> Iterator[None]:
    token = _GUARD.set(check)
    try:
        yield
    finally:
        _GUARD.reset(token)


def require(path: str | Path) -> None:
    """Raise :class:`OutsideRoots` when a guard is active and refuses ``path`` (no filesystem access
    happens before the guard has accepted the path)."""
    check = _GUARD.get()
    if check is not None:
        check(Path(path))


def active() -> bool:
    return _GUARD.get() is not None


__all__ = ["OutsideRoots", "active", "confined", "require"]
