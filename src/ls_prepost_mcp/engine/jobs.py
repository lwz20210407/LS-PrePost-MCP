"""Explicit execution requests, independent of MCP and Service."""

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar

from ..core.contracts import JobResult
from ..native.commands import quoted_path


def check_timeout(timeout):
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Execution timeout must be finite and positive")


@dataclass(frozen=True)
class BatchJob:
    executable: Path
    cfile: Path
    directory: Path
    timeout: float
    graphics: bool = False
    operation: str = "native_batch"
    verify: Callable[[dict], JobResult] | None = None
    macro_file: Path | None = None

    def __post_init__(self):
        check_timeout(self.timeout)
        if type(self.graphics) is not bool:
            raise ValueError("graphics must be Boolean")
        for name in ("executable", "cfile", "directory"):
            object.__setattr__(self, name, Path(getattr(self, name)).resolve())
        if not self.cfile.is_relative_to(self.directory):
            raise ValueError("Command file must belong to the job directory")
        if self.macro_file is not None:
            # Validate native grammar, retaining a raw argv element: subprocess
            # quotes it for the OS; literal quotes would change the m= value.
            quoted_path(self.macro_file)
            object.__setattr__(self, "macro_file", Path(self.macro_file).resolve())
            if not self.macro_file.is_relative_to(self.directory) or not self.macro_file.is_file():
                raise ValueError("Native macro file must exist inside the job directory")


@dataclass(frozen=True)
class SessionJob:
    operation: str
    directory: Path
    timeout: float
    submit: Callable[[], None]
    is_alive: Callable[[], bool]
    verify: Callable[[dict], JobResult] | None = None
    log: Path | None = None

    def __post_init__(self):
        check_timeout(self.timeout)
        object.__setattr__(self, "directory", Path(self.directory).resolve())


Job = TypeVar("Job", contravariant=True)


class Engine(Protocol[Job]):
    def run(self, job: Job) -> JobResult: ...
