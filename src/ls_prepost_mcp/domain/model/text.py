"""Byte-preserving line handling for LS-DYNA keyword files.

Files are decoded as latin-1, which maps every byte to one code point, so
untouched lines are written back byte for byte regardless of the original
encoding (ASCII, UTF-8, GBK comments, ...).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CODEC = "latin-1"
_LINE = re.compile(r"[^\r\n]*(?:\r\n|\n|\r)|[^\r\n]+\Z")
_FORMAT_FLAGS = "+-%"


def decode(data: bytes) -> str:
    """Decode file bytes losslessly."""
    return data.decode(CODEC)


def encode(text: str) -> bytes:
    """Encode text produced by :func:`decode` back to the identical bytes."""
    return text.encode(CODEC)


def split_lines(text: str) -> list[str]:
    """Split text into lines that keep their own line endings (LF, CRLF or CR)."""
    return _LINE.findall(text)


def body(line: str) -> str:
    """Return the line without its line ending."""
    return line.rstrip("\r\n")


def ending(line: str) -> str:
    """Return the line ending of ``line`` (may be empty for the last line)."""
    return line[len(body(line)):]


def is_comment(line: str) -> bool:
    return line.startswith("$")


def is_keyword(line: str) -> bool:
    return line.startswith("*")


def is_blank(line: str) -> bool:
    return not body(line).strip()


@dataclass(frozen=True)
class KeywordLine:
    """Parsed keyword line, e.g. ``*MAT_ELASTIC_TITLE`` or ``*NODE +``."""

    name: str
    flag: str
    extra: str

    @property
    def long_format(self) -> bool:
        return self.flag == "+"

    @property
    def i10_format(self) -> bool:
        return self.flag == "%"


def parse_keyword_line(line: str) -> KeywordLine:
    """Split a keyword line into upper-case name, format flag and trailing text."""
    text = body(line).strip()
    match = re.match(r"(\*[^\s,]*)(.*)", text)
    if match is None:
        raise ValueError(f"Not a keyword line: {line!r}")
    token, extra = match.group(1), match.group(2).strip()
    flag = ""
    if len(token) > 1 and token[-1] in _FORMAT_FLAGS:
        flag, token = token[-1], token[:-1]
    return KeywordLine(token.upper(), flag, extra)


def deck_format(extra: str) -> str:
    """Return the global format declared on ``*KEYWORD`` (standard, long or i10)."""
    upper = extra.upper().replace(" ", "")
    if "LONG=Y" in upper:
        return "long"
    if "I10=Y" in upper:
        return "i10"
    return "standard"
