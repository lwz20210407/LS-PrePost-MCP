"""Legacy process envelope adapter; all batch execution uses BatchEngine."""

from pathlib import Path

from .core.native_log import decode
from .engine import BatchEngine, BatchJob

__all__ = ["decode", "execute", "failure_message"]


def failure_message(process, fallback):
    error = process.get("engine_error")
    message = error.get("message") if isinstance(error,dict) else None
    return message if isinstance(message,str) and message.strip() else fallback


def execute(executable: Path, cfile: Path, directory: Path, *, timeout: float, graphics: bool) -> dict:
    result = BatchEngine().run(BatchJob(executable, cfile, directory, timeout, graphics))
    return dict(result.data, engine_status=result.status, engine_error=result.error)
