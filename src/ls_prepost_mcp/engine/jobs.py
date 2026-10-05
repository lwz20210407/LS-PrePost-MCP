"""Explicit execution requests, independent of MCP and Service."""

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar

from ..core.contracts import JobResult


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
    launch_mode: str = "c"

    def __post_init__(self):
        check_timeout(self.timeout)
        if type(self.graphics) is not bool:
            raise ValueError("graphics must be Boolean")
        if self.launch_mode not in ("c", "runc") or self.launch_mode == "runc" and self.graphics:
            raise ValueError("Choose c or runc; runc has no visible graphics mode")
        for name in ("executable", "cfile", "directory"):
            object.__setattr__(self, name, Path(getattr(self, name)).resolve())
        if not self.cfile.is_relative_to(self.directory):
            raise ValueError("Command file must belong to the job directory")
        if self.macro_file is not None:
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
