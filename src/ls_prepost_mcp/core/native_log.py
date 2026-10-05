"""Shared native diagnostic parsing and request-scoped log cursors."""

import re
from dataclasses import dataclass
from pathlib import Path

NATIVE_ERROR = re.compile(
    r"^\s*(?:\*+\s*)?(?:invalid(?:\s+[A-Za-z][\w-]*){0,3}\s+command\b|error while compiling\b|error occurred in parsing script\b|syntax error\b|runtime error\b)",
    re.IGNORECASE,
)


def decode(value):
    return value.decode("utf8", errors="replace") if isinstance(value, bytes) else (value or "")


def native_errors(text):
    return [line.strip() for line in text.splitlines() if NATIVE_ERROR.search(line)][:30]


def read_delta(path, offset=0, *, existed=False):
    """Reject a lost prefix instead of treating a replaced/truncated log as clean."""
    if type(offset) is not int or offset < 0:
        raise ValueError("Invalid native log offset")
    path = Path(path)
    if not path.exists():
        if existed or offset:
            raise ValueError("Native log disappeared during the request")
        return ""
    with path.open("rb") as stream:
        if stream.seek(0, 2) < offset:
            raise ValueError("Native log was truncated during the request")
        stream.seek(offset)
        return decode(stream.read())


@dataclass(frozen=True)
class LogCursor:
    path: Path
    offset: int
    identity: tuple[int, int] | None

    @classmethod
    def capture(cls, path):
        path = Path(path)
        try:
            stat = path.stat()
        except FileNotFoundError:
            return cls(path, 0, None)
        return cls(path, stat.st_size, (stat.st_dev, stat.st_ino))

    def read(self):
        if self.identity is not None and self.path.exists():
            stat = self.path.stat()
            if self.identity != (stat.st_dev, stat.st_ino):
                raise ValueError("Native log was replaced during the request")
        return read_delta(self.path, self.offset, existed=self.identity is not None)
