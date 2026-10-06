"""Typed batch execution and the legacy manifest boundary."""

from pathlib import Path

from .core.contracts import JobResult
from .core.native_log import decode
from .engine import BatchEngine, BatchJob
from .jobs import atomic_json

__all__ = ["decode", "execute", "failure_message", "run_batch", "record_batch_result"]


def run_batch(executable: Path, cfile: Path, directory: Path, *, timeout: float,
              graphics: bool, operation: str, launch_mode="c") -> JobResult:
    return BatchEngine().run(BatchJob(executable, cfile, directory, timeout, graphics,
                                      operation=operation, launch_mode=launch_mode))


def record_batch_result(result: JobResult, manifest: dict, directory: Path) -> None:
    """Persist execution evidence, then admit the caller's domain verification.

    A clean process is still unverified. Callers must verify their own response,
    outputs and input identity before reporting success. The legacy ``process``
    projection is output compatibility only; decisions read the typed result.
    """
    if not isinstance(result, JobResult):
        raise TypeError("Batch execution must return JobResult")
    if result.job_id != manifest["job_id"] or result.operation != manifest["action"]:
        raise ValueError("Batch result belongs to a different job or operation")
    manifest["engine_result"] = result.model_dump(mode="json")
    manifest["process"] = dict(result.data, engine_status=result.status, engine_error=result.error)
    if result.data.get("diagnostics"):
        manifest["native_diagnostics"] = result.data["diagnostics"]
    atomic_json(directory / "engine-result.json", manifest["engine_result"])
    manifest.setdefault("warnings", []).extend(result.warnings)
    if result.status in ("failed", "partial") or result.error is not None:
        message = (result.error or {}).get("message")
        raise RuntimeError(message if isinstance(message, str) and message.strip()
                           else "Batch execution {}: {}".format(result.status, "; ".join(result.warnings)))
    if result.check_status in ("failed", "invalid", "missing"):
        raise RuntimeError("Batch execution checks: " + result.check_status)
    if result.stage != "execution":
        raise RuntimeError("Batch result is not execution evidence")


def failure_message(process, fallback):
    error = process.get("engine_error")
    message = error.get("message") if isinstance(error,dict) else None
    return message if isinstance(message,str) and message.strip() else fallback


def execute(executable: Path, cfile: Path, directory: Path, *, timeout: float, graphics: bool, launch_mode="c") -> dict:
    """Compatibility adapter for external users; internal callers use run_batch."""
    result = run_batch(executable, cfile, directory, timeout=timeout, graphics=graphics,
                       operation="native_batch", launch_mode=launch_mode)
    return dict(result.data, engine_status=result.status, engine_error=result.error)
