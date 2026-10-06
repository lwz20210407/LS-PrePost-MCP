"""Include keywords: classification, file names and path resolution."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .text import body, is_blank

PATH_KEYWORDS = ("*INCLUDE_PATH", "*INCLUDE_PATH_RELATIVE")
# Keywords whose first card is a keyword file that we parse recursively.
RECURSIVE = ("*INCLUDE", "*INCLUDE_TRANSFORM", "*INCLUDE_AUTO_OFFSET")
# Include variants whose target is not a plain keyword deck (or needs special semantics).
OPAQUE_PREFIXES = ("*INCLUDE_BINARY", "*INCLUDE_NASTRAN", "*INCLUDE_STAMPED", "*INCLUDE_COMPENSATION",
                   "*INCLUDE_MULTISCALE", "*INCLUDE_UNITCELL", "*INCLUDE_COSIM")


def classify(keyword: str) -> str | None:
    """Return ``path``, ``file``, ``opaque`` or None for non-include keywords."""
    if not keyword.startswith("*INCLUDE"):
        return None
    if keyword in PATH_KEYWORDS:
        return "path"
    if keyword in RECURSIVE:
        return "file"
    return "opaque"


def _join_continued(lines: list[tuple[int, str]]) -> list[tuple[str, list[int]]]:
    """Join file names continued with a trailing `` +`` onto following lines."""
    names: list[tuple[str, list[int]]] = []
    pending, indices = "", []
    for index, line in lines:
        text = body(line).rstrip()
        indices.append(index)
        if text.endswith(" +"):
            pending += text[:-2].strip()
            continue
        names.append((pending + text.strip(), indices))
        pending, indices = "", []
    if pending:
        names.append((pending, indices))
    return names


def file_names(keyword: str, data: list[tuple[int, str]]) -> list[tuple[str, list[int]]]:
    """Return ``(name, data_line_indices)`` for each file referenced by an include block."""
    lines = [(i, line) for i, line in data if not is_blank(line)]
    kind = classify(keyword)
    if kind == "path":
        return [(body(line).strip(), [i]) for i, line in lines]
    names = _join_continued(lines)
    if keyword == "*INCLUDE":
        return names
    return names[:1]  # TRANSFORM / AUTO_OFFSET / opaque: only card 1 is a file name


@dataclass
class Resolution:
    """Outcome of resolving one include file name."""

    path: Path | None
    rule: str
    candidates: list[str] = field(default_factory=list)

    @property
    def ambiguous(self) -> bool:
        return len(set(self.candidates)) > 1


def identity(path: Path) -> str:
    """Case- and separator-normalized absolute path used to detect the same file."""
    return os.path.normcase(os.path.abspath(path))


def resolve(name: str, including_dir: Path, main_dir: Path, search_dirs: list[Path]) -> Resolution:
    """Resolve an include name.

    Order: absolute path; relative to the including file; relative to the main deck;
    each ``*INCLUDE_PATH`` directory in reading order. Every existing candidate is
    reported so that ambiguous layouts can be flagged instead of silently guessed.
    """
    target = Path(name)
    if target.is_absolute():
        return Resolution(target if target.is_file() else None, "absolute",
                          [identity(target)] if target.is_file() else [])
    ordered = [("including_dir", including_dir), ("main_dir", main_dir)]
    ordered += [("include_path", d) for d in search_dirs]
    found: list[tuple[str, Path]] = []
    for rule, directory in ordered:
        candidate = directory / target
        if candidate.is_file() and identity(candidate) not in {identity(p) for _, p in found}:
            found.append((rule, candidate))
    if not found:
        return Resolution(None, "missing", [])
    rule, chosen = found[0]
    return Resolution(chosen, rule, [identity(p) for _, p in found])
