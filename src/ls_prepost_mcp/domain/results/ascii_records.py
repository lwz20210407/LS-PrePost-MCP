"""Bounded raw text and scalar-field lexing; no numeric or GLSTAT block policy."""
from __future__ import annotations

from dataclasses import dataclass


class RecordTooLong(ValueError):
    """A caller-specified character bound was exceeded."""


def bounded_lines(path, *, max_record_chars: int, encoding: str, errors: str):
    """Yield raw lines, including blanks/newlines, with caller-owned decoding policy."""
    if type(max_record_chars) is not int or max_record_chars < 1:
        raise ValueError("max_record_chars must be a positive integer")
    with open(path, encoding=encoding, errors=errors) as stream:
        while line := stream.readline(max_record_chars + 1):
            if len(line) > max_record_chars:
                raise RecordTooLong("ASCII record exceeds the caller's character bound")
            yield line


@dataclass(frozen=True, slots=True)
class ScalarField:
    raw_label: str
    value_token: str
    suffix: str
    separator: str
    separator_width: int


def tokenize_scalar(line: str, *, separators: str = ".", minimum_dots: int = 1,
                    require_dot_space: bool = True,
                    label_characters: frozenset[str] | None = None) -> ScalarField | None:
    """Choose the rightmost admissible separator, retaining a raw token and suffix.

    The label alphabet and separator grammar are explicit caller choices. With
    the historical energy-label alphabet, the first separator is the only
    admissible one; unrestricted dotted labels retain punctuation in their name.
    No token is converted to a number and suffixes (including wall IDs) stay raw.
    """
    text = line.rstrip("\r\n")
    start = len(text) - len(text.lstrip())
    first_bad = len(text)
    if label_characters is not None:
        first_bad = next((i for i in range(start, len(text)) if text[i] not in label_characters), len(text))
    best = None
    index = start
    while index < len(text):
        separator = text[index]
        if separator not in separators:
            index += 1
            continue
        begin = index
        index += 1
        if separator == ".":
            while index < len(text) and text[index] == ".":
                index += 1
            if index - begin < minimum_dots:
                continue
            if require_dot_space and (index == len(text) or not text[index].isspace()):
                continue
        label_end = begin
        while label_end > start and text[label_end - 1].isspace():
            label_end -= 1
        if label_characters is not None and (label_end == start or first_bad < label_end):
            continue
        value_start = index
        while value_start < len(text) and text[value_start].isspace():
            value_start += 1
        if value_start < len(text):
            best = (label_end, value_start, separator, index - begin)
        elif separator == "." and not require_dot_space and index - begin > minimum_dots:
            # Preserve the legacy separator-without-space grammar: its final
            # dot can be an opaque value token. A known numeric field then fails
            # in the upper reader rather than silently disappearing as "missing".
            best = (label_end, index - 1, separator, index - begin - 1)
    if best is None:
        return None
    label_end, value_start, separator, width = best
    value_end = value_start
    while value_end < len(text) and not text[value_end].isspace():
        value_end += 1
    return ScalarField(text[start:label_end], text[value_start:value_end], text[value_end:], separator, width)
