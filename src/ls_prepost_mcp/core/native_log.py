"""Shared native diagnostic parsing and request-scoped log cursors."""

import codecs
import locale
import os
import re
from dataclasses import dataclass
from pathlib import Path

NATIVE_ERROR = re.compile(
    r"^\s*(?:\*+\s*)?(?:invalid(?:\s+[A-Za-z][\w-]*){0,3}\s+command\b|error while compiling\b|error occurred in parsing script\b|syntax error\b|runtime error\b|error\s*-\s*include\s+file\s+.+\s+not\s+open\s*$|output file .+ not open\s*$)",
    re.IGNORECASE,
)


SIGNATURES = ((codecs.BOM_UTF32_LE, "utf-32-le"), (codecs.BOM_UTF32_BE, "utf-32-be"),
              (codecs.BOM_UTF8, "utf-8"), (codecs.BOM_UTF16_LE, "utf-16-le"),
              (codecs.BOM_UTF16_BE, "utf-16-be"))


def decode_with_info(value, *, encoding=None):
    """BOM, explicit hint/setting, strict UTF-8, then native locale encoding.

    Report replacement decoding rather than silently treating it as clean logs.
    locale.getencoding() ignores Python UTF-8 mode (important for Windows ACP).
    """
    if isinstance(value, str):
        return value, dict(encoding="unicode", lossy=False)
    data = value or b""
    for signature, codec in SIGNATURES:
        if data.startswith(signature):
            data, encoding = data[len(signature):], codec
            break
    chosen = encoding or os.environ.get("LSPP_NATIVE_LOG_ENCODING")
    if chosen is None:
        try:
            return data.decode("utf8"), dict(encoding="utf-8", lossy=False)
        except UnicodeDecodeError:
            chosen = locale.getencoding()
    chosen = codecs.lookup(chosen).name
    try:
        return data.decode(chosen), dict(encoding=chosen, lossy=False)
    except UnicodeError:
        return data.decode(chosen, errors="replace"), dict(encoding=chosen, lossy=True)


def decode(value, *, encoding=None):
    return decode_with_info(value, encoding=encoding)[0]


def _file_encoding(path):
    try:
        with Path(path).open("rb") as stream:
            header = stream.read(4)
    except FileNotFoundError:
        return None
    return next((codec for signature, codec in SIGNATURES if header.startswith(signature)), None)


def native_errors(text):
    lines = (line.lstrip("\ufeff") for line in text.splitlines())
    return [line.strip() for line in lines if NATIVE_ERROR.search(line)][:30]


def read_delta_bytes(path, offset=0, *, existed=False):
    """Reject a lost prefix instead of treating a replaced/truncated log as clean."""
    if type(offset) is not int or offset < 0:
        raise ValueError("Invalid native log offset")
    path = Path(path)
    if not path.exists():
        if existed or offset:
            raise ValueError("Native log disappeared during the request")
        return b""
    with path.open("rb") as stream:
        if stream.seek(0, 2) < offset:
            raise ValueError("Native log was truncated during the request")
        stream.seek(offset)
        return stream.read()


def read_delta(path, offset=0, *, existed=False):
    encoding = _file_encoding(path)
    return decode(read_delta_bytes(path, offset, existed=existed), encoding=encoding)


@dataclass(frozen=True)
class LogCursor:
    path: Path
    offset: int
    identity: tuple[int, int] | None
    encoding: str | None = None

    @classmethod
    def capture(cls, path):
        path = Path(path)
        try:
            stat = path.stat()
        except FileNotFoundError:
            return cls(path, 0, None)
        return cls(path, stat.st_size, (stat.st_dev, stat.st_ino), _file_encoding(path))

    def read_bytes(self):
        if self.identity is not None and self.path.exists():
            stat = self.path.stat()
            if self.identity != (stat.st_dev, stat.st_ino):
                raise ValueError("Native log was replaced during the request")
        return read_delta_bytes(self.path, self.offset, existed=self.identity is not None)

    def read(self):
        return self.decode_with_info(self.read_bytes())[0]

    def decode_with_info(self, data):
        return decode_with_info(data, encoding=self.encoding or _file_encoding(self.path))
