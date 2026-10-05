"""Keyword files split into raw blocks that join back to the original bytes."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from .text import KeywordLine, decode, encode, is_comment, is_keyword, parse_keyword_line, split_lines


@dataclass(eq=False)
class Block:
    """A keyword line plus its following lines, or a preamble / post-``*END`` region.

    ``lines`` keep their original line endings. Field positions refer to indices
    into ``lines`` (index 0 is the keyword line for keyword blocks).
    """

    lines: list[str]
    kind: str  # "preamble" | "keyword" | "after_end"
    keyword: KeywordLine | None = None
    file: SourceFile | None = field(default=None, repr=False)

    @property
    def name(self) -> str:
        return self.keyword.name if self.keyword else ""

    def data(self) -> list[tuple[int, str]]:
        """Non-comment lines after the keyword line as ``(line_index, line)``.

        Blank lines are kept: LS-DYNA reads a blank line as a card with default values.
        """
        if self.kind != "keyword":
            return []
        return [(i, line) for i, line in enumerate(self.lines) if i > 0 and not is_comment(line)]

    def text(self) -> str:
        return "".join(self.lines)

    @property
    def line_number(self) -> int:
        """1-based line number of the first line of this block in its file."""
        if self.file is None:
            return 1
        return self.file.line_number_of(self)


def parse_blocks(text: str) -> list[Block]:
    """Split file text into blocks. ``"".join`` of all block lines equals ``text``."""
    blocks: list[Block] = []
    current: list[str] = []
    kind, keyword = "preamble", None
    for line in split_lines(text):
        if kind != "after_end" and is_keyword(line):
            if current:
                blocks.append(Block(current, kind, keyword))
            keyword, current, kind = parse_keyword_line(line), [line], "keyword"
            if keyword.name == "*END":
                blocks.append(Block(current, kind, keyword))
                current, kind, keyword = [], "after_end", None
            continue
        current.append(line)
    if current:
        blocks.append(Block(current, kind, keyword))
    return blocks


@dataclass(eq=False)
class SourceFile:
    """One keyword file on disk with its parsed blocks and modification state."""

    path: Path
    original: bytes
    blocks: list[Block]
    modified: bool = False
    _index: dict[int, int] = field(default_factory=dict, repr=False, compare=False)
    _starts: list[int] = field(default_factory=list, repr=False, compare=False)
    _valid: int = field(default=-1, repr=False, compare=False)
    _newline: str = field(default="", repr=False, compare=False)

    def invalidate_line_numbers(self, block: Block | None = None) -> None:
        """Forget cached line numbers after ``block`` (or all) gained or lost lines.

        The first line of a block does not depend on its own length: only later blocks reset.
        """
        position = self._index.get(id(block)) if block is not None else None
        if position is None or position >= len(self.blocks) or self.blocks[position] is not block:
            self._index.clear()
            self._valid = -1
        else:
            self._valid = min(self._valid, position)

    def line_number_of(self, block: Block) -> int:
        """1-based first line of ``block``; computed incrementally and cached."""
        position = self._index.get(id(block))
        if position is None or position >= len(self.blocks) or self.blocks[position] is not block:
            self._index = {id(item): n for n, item in enumerate(self.blocks)}  # blocks inserted/removed
            self._valid = -1
            position = self._index.get(id(block))
            if position is None:
                raise LookupError("Block is no longer part of its file")
        if position > self._valid:
            if self._valid < 0:
                self._starts, self._valid = [1], 0
            del self._starts[self._valid + 1:]
            for n in range(self._valid, position):
                self._starts.append(self._starts[n] + len(self.blocks[n].lines))
            self._valid = position
        return self._starts[position]

    @classmethod
    def read(cls, path: Path) -> SourceFile:
        data = path.read_bytes()
        source = cls(path=path, original=data, blocks=parse_blocks(decode(data)))
        for block in source.blocks:
            block.file = source
        return source

    @property
    def original_sha256(self) -> str:
        return hashlib.sha256(self.original).hexdigest()

    def text(self) -> str:
        return "".join(block.text() for block in self.blocks)

    def data(self) -> bytes:
        return encode(self.text())

    def encoding(self) -> str | None:
        """Text encoding of the original bytes: ascii, utf-8 or gbk; None when unknown."""
        cached = getattr(self, "_encoding", "")
        if cached != "":
            return cached
        found = None
        for name in ("ascii", "utf-8", "gbk"):
            try:
                self.original.decode(name)
            except UnicodeDecodeError:
                continue
            found = name
            break
        self._encoding = found
        return found

    def to_text(self, value: str) -> str:
        """Map a real string to the byte-per-character text form of this file."""
        if value.isascii():
            return value
        encoding = self.encoding()
        if encoding == "ascii":
            encoding = "utf-8"
        if encoding is None:
            raise ValueError(f"Cannot write non-ASCII text into {self.path}: file encoding is unknown")
        return value.encode(encoding).decode("latin-1")

    def from_text(self, text: str) -> str:
        """Readable string for a field of this file (UTF-8/GBK decoded when known)."""
        if text.isascii():
            return text
        encoding = self.encoding() or "latin-1"
        return text.encode("latin-1").decode(encoding, errors="replace")

    def newline(self) -> str:
        """Dominant line ending of the original file (used for inserted text)."""
        if not self._newline:
            crlf = self.original.count(b"\r\n")
            lf = self.original.count(b"\n") - crlf
            self._newline = "\r\n" if crlf > lf else "\n"
        return self._newline

    def keyword_blocks(self) -> list[Block]:
        return [b for b in self.blocks if b.kind == "keyword"]


def make_blocks(text: str, newline: str) -> list[Block]:
    """Parse new keyword text for insertion, normalizing its line endings to ``newline``."""
    lines = [line.rstrip("\r\n") for line in split_lines(text)]
    normalized = "".join(line + newline for line in lines)
    blocks = parse_blocks(normalized)
    if not blocks or any(b.kind != "keyword" for b in blocks):
        raise ValueError("Inserted text must consist of complete keyword blocks starting with '*'")
    if any(b.name in ("*END", "*KEYWORD") for b in blocks):
        raise ValueError("Inserted text must not contain *KEYWORD or *END")
    return blocks
