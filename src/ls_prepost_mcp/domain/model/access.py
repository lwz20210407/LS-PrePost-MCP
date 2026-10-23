"""Optional confinement of every path the keyword engine stats or reads for an Include tree.

Callers that serve untrusted decks (the M3 MCP tools) run engine calls inside ``confined(check)``;
``check(path)`` raises :class:`OutsideRoots` for a path that may not be touched. The engine calls
:func:`require` before it stats or reads an include candidate, an include file, an opaque target
or a search directory, so neither the deck, nor an edit that adds an ``*INCLUDE``, nor the reload
after saving can reach other files or contact a UNC host. Without an active guard nothing changes.
"""
from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path


class OutsideRoots(PermissionError):
    """A path that the active guard does not allow."""


_GUARD: ContextVar[Callable[[Path], None] | None] = ContextVar("keyword_engine_guard", default=None)


@contextmanager
def confined(check: Callable[[Path], None]) -> Iterator[None]:
    previous = _GUARD.get()
    if previous is not None and previous is not check:
        def combined(path: Path) -> None:
            previous(path)
            check(path)
        active_check = combined
    else:
        active_check = check
    token = _GUARD.set(active_check)
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


_EXTENDED_DRIVE = re.compile(r"^[\\/]{2}\?[\\/][A-Za-z]:[\\/]")


def local_path_text(text: str) -> str:
    r"""An extended-length drive path (``\\?\C:\...``, either separator) without its prefix.

    Every other ``\\?\`` or ``\\.\`` form (``UNC``, ``GLOBALROOT\Device\Mup``, devices) is returned
    unchanged, so :func:`is_network` refuses it before anything resolves it.
    """
    return text[4:] if _EXTENDED_DRIVE.match(text) else text



def root_guard(roots: tuple[Path, ...]) -> Callable[[Path], None]:
    """Refuse a UNC or device name, or a path outside ``roots``, before the engine stats or reads it.

    The test is lexical first, so a refused path is not probed (its existence is not revealed);
    an existing path inside a root must also resolve inside one (links and junctions).
    """
    from .includes import is_network

    local_roots = [Path(local_path_text(str(root))) for root in roots
                   if not is_network(local_path_text(str(root)))]
    bases = {Path(os.path.abspath(root)) for root in local_roots}
    for root in local_roots:
        try:
            bases.add(root.resolve())
        except OSError:
            continue

    def check(path: Path) -> None:
        text = local_path_text(str(path))
        if is_network(text):
            raise OutsideRoots(f"Network path {str(path)!r} is not followed")
        lexical = Path(os.path.normpath(os.path.abspath(text)))
        if not any(lexical.is_relative_to(base) for base in bases):
            raise OutsideRoots(f"{str(path)!r} is outside the allowed roots")
        if os.path.lexists(lexical) and not any(lexical.resolve().is_relative_to(base) for base in bases):
            raise OutsideRoots(f"{str(path)!r} leads outside the allowed roots")

    return check



__all__ = ["OutsideRoots", "active", "confined", "require", "root_guard", "local_path_text"]
