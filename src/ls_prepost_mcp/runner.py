"""Legacy process envelope adapter; all batch execution uses BatchEngine."""

from pathlib import Path

from .core.native_log import decode
from .engine import BatchEngine, BatchJob

__all__ = ["decode", "execute"]


def execute(executable: Path, cfile: Path, directory: Path, *, timeout: float, graphics: bool, launch_mode="c") -> dict:
    result = BatchEngine().run(BatchJob(executable, cfile, directory, timeout, graphics, launch_mode=launch_mode))
    return dict(result.data, engine_status=result.status, engine_error=result.error)
