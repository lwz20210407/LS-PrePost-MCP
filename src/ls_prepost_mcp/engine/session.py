"""Finite correlated requests in an existing process; never spawn or replay."""

import json
import time

from ..core.contracts import JobResult
from ..core.native_log import LogCursor, decode, native_errors
from .jobs import SessionJob


class SessionEngine:
    def run(self, job: SessionJob) -> JobResult:
        complete = job.directory / "complete.json"
        submitted = False
        try:
            if complete.exists():
                raise ValueError("Refusing stale completion before submission")
            cursor = LogCursor.capture(job.log) if job.log is not None else None
            submitted = True  # Even a failed send may have reached the native process.
            job.submit()
            deadline = time.monotonic() + job.timeout
            while True:
                if complete.exists():
                    reply = json.loads(complete.read_text(encoding="utf8"))
                    if not isinstance(reply, dict) or reply.get("job_id") != job.directory.name:
                        raise RuntimeError("Native response correlation mismatch")
                    if type(reply.get("ok")) is not bool:
                        raise ValueError("Native response success flag is not Boolean")
                    if cursor:
                        raw_log = cursor.read_bytes()
                        (job.directory / "native-session.log").write_bytes(raw_log)
                        (job.directory / "native-session-log.json").write_text(
                            json.dumps(dict(source=str(cursor.path), offset=cursor.offset)), encoding="utf8")
                    diagnostics = native_errors(decode(raw_log)) if cursor else []
                    if diagnostics:
                        reply = dict(reply, ok=False, error=dict(type="NativeDiagnostics", message="; ".join(diagnostics)))
                    if job.verify is not None:
                        result = JobResult.model_validate(job.verify(reply))
                        if result.operation != job.operation or result.job_id != job.directory.name:
                            raise ValueError("Session verifier returned a different job identity")
                        return result
                    return JobResult(operation=job.operation, job_id=job.directory.name,
                                     status="unverified" if reply["ok"] else "failed", backend="lsprepost",
                                     data=reply, error=None if reply["ok"] else reply.get("error"))
                if not job.is_alive():
                    raise RuntimeError("Owned LS-PrePost exited before completion; inspect native logs before recovery")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Native operation outcome uncertain; inspect session or restore checkpoint")
                time.sleep(0.05)
        except Exception as exc:
            return JobResult(operation=job.operation, job_id=job.directory.name, backend="lsprepost",
                             status="unverified" if submitted else "failed",
                             data=dict(submitted=submitted, replayed=False),
                             error=dict(type=type(exc).__name__, message=str(exc)))
