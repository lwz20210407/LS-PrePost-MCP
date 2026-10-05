"""Keyword deck: include tree, parameters, named/positional edits and byte-preserving save."""
from __future__ import annotations

import logging
import math
import os
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from . import lists, persist, references, scope
from .blocks import Block, SourceFile, make_blocks
from .fields import FieldError, FieldSlot, format_value, is_free_format, parse_number, read_text, write_text
from .includes import Resolution, classify, file_names, identity, resolve
from .parameters import reference
from .schema import FieldInfo, Layout, Unsupported, block_format
from .schema import layout as block_layout
from .scope import ParameterRecord
from .text import deck_format, ending

logger = logging.getLogger(__name__)
_STRUCTURAL = ("*INCLUDE", "*PARAMETER", "*KEYWORD")


@dataclass
class IncludeRef:
    parent: SourceFile
    block: Block
    kind: str  # "file" | "path" | "opaque"
    name: str
    resolution: Resolution | None = None
    child: SourceFile | None = None
    cycle: bool = False
    repeated: bool = False


@dataclass
class FieldValue:
    name: str
    raw: str
    value: object
    parameter: str | None
    card: str
    line: int  # 1-based line number in the file


@dataclass
class Change:
    path: Path
    keyword: str
    line: int
    description: str
    before: str
    after: str
    exact: bool = True


class KeywordDeck:
    """An LS-DYNA keyword deck loaded with all include files, editable without reformatting."""

    def __init__(self, main: SourceFile, search_dirs: list[Path], max_files: int = 5000) -> None:
        self.main = main
        self.main_dir = main.path.parent
        self.files: dict[str, SourceFile] = {identity(main.path): main}
        self.max_files = max_files
        self.base_search_dirs = list(search_dirs)
        self.changes: list[Change] = []
        self._rebuild()

    @classmethod
    def load(cls, path: str | os.PathLike[str], include_paths: tuple[str, ...] = (), max_files: int = 5000) -> KeywordDeck:
        """Load ``path`` and every include file it references (read-only on disk)."""
        return cls(SourceFile.read(Path(path)), [Path(p) for p in include_paths], max_files)

    # ------------------------------------------------------------------ structure
    def _rebuild(self) -> None:
        self.includes: list[IncludeRef] = []
        self.search_dirs = list(self.base_search_dirs)
        self.warnings: list[str] = []
        self.format = "standard"
        self._parents: dict[str, str] = {}
        self._walk(self.main, [identity(self.main.path)])
        self._evaluate_parameters()

    def _where(self, block: Block) -> str:
        return f"{block.file.path}:{block.line_number}" if block.file else "?"

    def _walk(self, source: SourceFile, stack: list[str]) -> None:
        for block in source.keyword_blocks():
            if block.name == "*KEYWORD" and source is self.main:
                self.format = deck_format(block.keyword.extra if block.keyword else "")
            kind = classify(block.name)
            if kind is None:
                continue
            for name, _ in file_names(block.name, block.data()):
                if kind == "path":
                    directory = Path(name)
                    self.search_dirs.append(directory if directory.is_absolute() else self.main_dir / directory)
                    self.includes.append(IncludeRef(source, block, kind, name))
                    continue
                result = resolve(name, source.path.parent, self.main_dir, self.search_dirs)
                ref = IncludeRef(source, block, kind, name, result)
                self.includes.append(ref)
                if result.ambiguous:
                    self.warnings.append(f"Ambiguous include {name!r} at {self._where(block)}: {result.candidates}")
                if result.path is None:
                    self.warnings.append(f"Missing include {name!r} at {self._where(block)}")
                    continue
                if kind == "opaque":
                    continue
                key = identity(result.path)
                if key in stack:
                    ref.cycle = True
                    self.warnings.append(f"Include cycle via {name!r} at {self._where(block)}")
                    continue
                child = self.files.get(key)
                if child is not None and key in self._parents:
                    ref.child, ref.repeated = child, True
                    self.warnings.append(f"{name!r} is included more than once; LS-DYNA reads it each time")
                    continue
                if child is None:
                    if len(self.files) >= self.max_files:
                        raise ValueError(f"More than {self.max_files} include files")
                    child = SourceFile.read(result.path)
                    self.files[key] = child
                ref.child = child
                self._parents[key] = identity(source.path)
                self._walk(child, stack + [key])

    def iter_blocks(self, source: SourceFile | None = None, _stack: list[str] | None = None) -> Iterator[Block]:
        """Keyword blocks in LS-DYNA reading order, include files expanded in place."""
        source = source or self.main
        stack = _stack or [identity(source.path)]
        by_block: dict[int, list[IncludeRef]] = {}
        for ref in self.includes:
            if ref.parent is source:
                by_block.setdefault(id(ref.block), []).append(ref)
        for block in source.keyword_blocks():
            yield block
            for ref in by_block.get(id(block), []):
                if ref.child is None or ref.cycle or ref.kind != "file":
                    continue
                key = identity(ref.child.path)
                if key not in stack:
                    yield from self.iter_blocks(ref.child, stack + [key])

    def blocks(self, pattern: str | None = None) -> list[Block]:
        """Blocks matching ``pattern``.

        ``*SECTION_SHELL`` also matches its ``_TITLE`` / ``_ID`` / ``_MPP`` variants;
        a trailing ``*`` (``*MAT_*``) is a prefix match.
        """
        result = []
        for block in self.iter_blocks():
            if pattern is None or _matches(block.name, pattern.upper()):
                result.append(block)
        return result

    def include_tree(self) -> dict:
        """Nested include structure with resolution rule and problems for each reference."""
        def node(source: SourceFile, stack: list[str]) -> list[dict]:
            entries = []
            for ref in self.includes:
                if ref.parent is not source:
                    continue
                res = ref.resolution
                entry = {"name": ref.name, "kind": ref.kind, "keyword": ref.block.name, "line": ref.block.line_number,
                         "path": str(ref.child.path) if ref.child else (str(res.path) if res and res.path else None),
                         "rule": res.rule if res else None, "missing": bool(res and res.path is None),
                         "ambiguous": bool(res and res.ambiguous), "cycle": ref.cycle, "repeated": ref.repeated}
                if ref.child and not ref.cycle and not ref.repeated:
                    key = identity(ref.child.path)
                    entry["includes"] = node(ref.child, stack + [key])
                entries.append(entry)
            return entries
        return {"path": str(self.main.path), "includes": node(self.main, [identity(self.main.path)])}

    def summary(self) -> dict:
        names = Counter(block.name for block in self.iter_blocks())
        return {"main": str(self.main.path), "files": len(self.files), "format": self.format,
                "keyword_blocks": sum(names.values()), "keywords": dict(sorted(names.items())),
                "parameters": len(self.parameters), "warnings": list(self.warnings)}

    # ------------------------------------------------------------------ parameters
    def _evaluate_parameters(self) -> None:
        self._scopes = scope.evaluate(self)
        self.parameters: list[ParameterRecord] = self._scopes.records

    def lookup(self, block: Block) -> dict[str, object]:
        """Parameter values visible to ``block`` (lower-case names)."""
        return {k: v for k, v in self._scopes.visible(identity(block.file.path)).items() if v is not None}

    def set_parameter(self, name: str, value: object, file: str | None = None) -> Change:
        """Change a ``*PARAMETER`` value or ``*PARAMETER_EXPRESSION`` text; dependents re-evaluate."""
        return scope.set_parameter(self, name, value, file)

    # ------------------------------------------------------------------ fields
    def layout(self, block: Block) -> Layout:
        return block_layout(block, self.lookup(block), self.format)

    def _value(self, block: Block, info: FieldInfo) -> FieldValue:
        raw = read_text(block.lines[info.slot.line], info.slot)
        stripped, parameter, value = raw.strip(), None, None
        ref = reference(stripped)
        if ref:
            parameter = ref[1]
            value = self.lookup(block).get(parameter.lower())
            if isinstance(value, (int, float)) and ref[0]:
                value = -value
        elif not stripped:
            value = info.default
        elif info.kind == "str":
            value = stripped
        else:
            value = parse_number(stripped)
        return FieldValue(info.name, raw, value, parameter, info.card, block.line_number + info.slot.line)

    def get(self, block: Block, name: str, card: str | None = None, row: int | None = None) -> FieldValue:
        """Read one named field. Table keywords (``*NODE``, ``*PART``) need ``row``."""
        return self._value(block, self.layout(block).lookup(name, card, row))

    def fields(self, block: Block, row: int | None = None) -> list[FieldValue]:
        lay = self.layout(block)
        pool = lay.rows[row] if lay.key and row is not None else lay.fields
        if lay.key and row is None:
            pool = [info for infos in lay.rows.values() for info in infos]
        return [self._value(block, info) for info in pool]

    def find(self, pattern: str, **criteria: object) -> list[tuple[Block, int | None]]:
        """Blocks (and rows for table keywords) whose named fields equal ``criteria``."""
        found: list[tuple[Block, int | None]] = []
        for block in self.blocks(pattern):
            if not criteria:
                found.append((block, None))
                continue
            try:
                lay = self.layout(block)
            except Unsupported as error:
                logger.debug("find skipped %s: %s", self._where(block), error)
                continue
            groups = ([(None, lay.fields)] if lay.fields else []) + (list(lay.rows.items()) if lay.key else [])
            for row, infos in groups:
                by_name = {info.name: info for info in infos}
                if all(k.lower() in by_name and _equal(self._value(block, by_name[k.lower()]).value, v)
                       for k, v in criteria.items()):
                    found.append((block, row))
        return found

    def set(self, block: Block, name: str, value: object, card: str | None = None, row: int | None = None) -> Change:
        """Write one named field; only that field's columns change. Verified by re-reading."""
        lay = self.layout(block)
        info = lay.lookup(name, card, row)
        width = info.slot.width if info.slot.token is None else 40
        ref = reference(value) if isinstance(value, str) else None
        if ref:
            if ref[1].lower() not in self.lookup(block):
                raise FieldError(f"Undefined parameter {ref[1]!r}")
            text, exact = value.strip(), True
        else:
            text, exact = format_value(str(value) if info.kind == "str" else value, width, info.kind)
        index = info.slot.line
        before = block.lines[index]
        block.lines[index] = write_text(before, info.slot, text, "left" if info.kind == "str" else "right")
        check_row = int(value) if lay.key and name.lower() == lay.key and not ref else row
        try:
            written = self.get(block, name, card, check_row).raw.strip()
        except (Unsupported, KeyError, FieldError) as error:
            block.lines[index] = before
            raise FieldError(f"Edit of {name!r} failed verification: {error}") from error
        if written != text.strip():
            block.lines[index] = before
            raise FieldError(f"Edit of {name!r} failed verification: read back {written!r}")
        return self._record(block, index, f"{name}={text}", before, exact)

    def set_position(self, block: Block, data_index: int, text: str, *, field_index: int | None = None,
                     offset: int | None = None, width: int = 10, align: str = "right") -> Change:
        """Positional edit for any keyword: ``data_index``-th non-comment line, field by index or columns."""
        data = block.data()
        if not 0 <= data_index < len(data):
            raise IndexError(f"{block.name} has {len(data)} data lines")
        index, line = data[data_index]
        if is_free_format(line):
            if field_index is None:
                raise FieldError("Comma-separated line: give field_index")
            slot = FieldSlot(index, 0, width, field_index)
        else:
            start = offset if offset is not None else (field_index or 0) * width
            slot = FieldSlot(index, start, width)
        before = line
        block.lines[index] = write_text(line, slot, text, align)
        return self._record(block, index, f"data line {data_index} -> {text!r}", before, True)

    # ------------------------------------------------------------------ lists and curves
    def members(self, block: Block) -> list[int]:
        """Member IDs of a ``*SET_*_LIST`` style block (header fields via :meth:`get`)."""
        if not lists.is_list_set(block.name):
            raise Unsupported(f"{block.name} is not a list set")
        return lists.members(block, self._long(block))

    def set_members(self, block: Block, ids: list[int]) -> Change:
        """Replace all members; header, title and comments are kept."""
        if not lists.is_list_set(block.name):
            raise Unsupported(f"{block.name} is not a list set")
        saved = list(block.lines)
        long = self._long(block)
        removed, added = lists.write_members(block, list(ids), long=long)
        if lists.members(block, long) != list(ids):
            block.lines[:] = saved
            raise FieldError("Member list failed verification after writing")
        return self._record_lines(block, f"members -> {len(ids)} IDs", removed, added)

    def _long(self, block: Block) -> bool:
        return block_format(block, self.format) == "long"

    def points(self, block: Block) -> list[tuple[float, float]]:
        """``(a, o)`` points of a ``*DEFINE_CURVE`` block."""
        if not lists.is_curve(block.name):
            raise Unsupported(f"{block.name} is not *DEFINE_CURVE")
        return lists.points(block)

    def set_points(self, block: Block, pairs: list[tuple[float, float]]) -> Change:
        """Replace all curve points (20-character fields); header and title are kept."""
        if not lists.is_curve(block.name):
            raise Unsupported(f"{block.name} is not *DEFINE_CURVE")
        saved = list(block.lines)
        removed, added = lists.write_points(block, [(float(a), float(o)) for a, o in pairs])
        read = lists.points(block)
        if len(read) != len(pairs) or any(not (math.isclose(a, x, rel_tol=1e-6, abs_tol=1e-30) and
                                               math.isclose(o, y, rel_tol=1e-6, abs_tol=1e-30))
                                          for (a, o), (x, y) in zip(read, pairs)):
            block.lines[:] = saved
            raise FieldError("Curve points failed verification after writing")
        return self._record_lines(block, f"points -> {len(pairs)}", removed, added)

    def _record_lines(self, block: Block, description: str, removed: list[str], added: list[str]) -> Change:
        block.file.modified = True
        change = Change(block.file.path, block.name, block.line_number, description, "".join(removed), "".join(added))
        self.changes.append(change)
        return change

    # ------------------------------------------------------------------ blocks
    def insert(self, text: str, *, file: SourceFile | None = None, before: Block | None = None,
               after: Block | None = None) -> list[Block]:
        """Insert keyword blocks; default position is just before ``*END`` of the target file."""
        anchor = before or after
        target = anchor.file if anchor else (file or self.main)
        newline = target.newline()
        new = make_blocks(text, newline)
        if before is not None:
            position = target.blocks.index(before)
        elif after is not None:
            position = target.blocks.index(after) + 1
        else:
            ends = [i for i, b in enumerate(target.blocks) if b.name == "*END"]
            position = ends[0] if ends else len(target.blocks)
        if position > 0:
            previous = target.blocks[position - 1]
            if previous.lines and not ending(previous.lines[-1]):
                previous.lines[-1] += newline
        for block in new:
            block.file = target
        target.blocks[position:position] = new
        for block in new:
            self._record(block, 0, f"inserted {block.name}", "", True)
        if any(b.name.startswith(_STRUCTURAL) for b in new):
            self._rebuild()
        return new

    def references(self, include_mesh: bool = True) -> references.ReferenceReport:
        """Defined IDs, references, dangling/duplicate/unused IDs across the whole deck."""
        return references.collect(self, include_mesh)

    def delete(self, block: Block, force: bool = False) -> Change:
        """Remove a block; refuses when IDs it defines are still referenced (unless ``force``)."""
        if not force:
            references.check_delete(self, block)
        source = block.file
        line = block.line_number
        source.blocks.remove(block)
        source.modified = True
        change = Change(source.path, block.name, line, f"deleted {block.name}", block.text(), "")
        self.changes.append(change)
        if block.name.startswith(_STRUCTURAL):
            self._rebuild()
        return change

    def replace(self, block: Block, text: str) -> list[Block]:
        new = self.insert(text, before=block)
        self.delete(block)
        return new

    def _record(self, block: Block, index: int, description: str, before: str, exact: bool) -> Change:
        block.file.modified = True
        change = Change(block.file.path, block.name, block.line_number + index, description,
                        before, block.lines[index], exact)
        self.changes.append(change)
        if block.name.startswith(_STRUCTURAL) and description != f"inserted {block.name}":
            self._rebuild()
        return change

    # ------------------------------------------------------------------ output
    def modified_files(self) -> list[SourceFile]:
        return persist.modified_files(self)

    def diff(self) -> str:
        return persist.diff(self)

    def save_as(self, out_dir: str | os.PathLike[str], overwrite: bool = False) -> dict:
        """Write to a new directory keeping relative layout; untouched files are copied verbatim."""
        return persist.save_as(self, out_dir, overwrite)

    def save_in_place(self, backup_suffix: str = ".orig") -> dict:
        """Overwrite only edited files after writing ``<name><backup_suffix>`` backups."""
        return persist.save_in_place(self, backup_suffix)


_OPTION_SUFFIXES = {"TITLE", "ID", "MPP", "ID_MPP", "MPP_ID"}


def _matches(name: str, pattern: str) -> bool:
    if pattern.endswith("*") and len(pattern) > 1:
        return name.startswith(pattern[:-1])
    if name == pattern:
        return True
    return name.startswith(pattern + "_") and name[len(pattern) + 1:] in _OPTION_SUFFIXES


def _equal(actual: object, expected: object) -> bool:
    if isinstance(expected, str) or isinstance(actual, str):
        return str(actual).strip().lower() == str(expected).strip().lower()
    if actual is None or expected is None:
        return actual is expected
    return math.isclose(float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-30)
