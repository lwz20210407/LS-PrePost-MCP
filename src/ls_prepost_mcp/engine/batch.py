"""One isolated, owned process per batch job."""

import os
import subprocess
import time

from ..core.contracts import JobResult
from ..core.native_log import LogCursor, decode, native_errors
from ..native.versions import require_capability
from .environment import native_environment
from .jobs import BatchJob


class BatchEngine:
    def run(self, job: BatchJob) -> JobResult:
        start = time.monotonic()
        args = [str(job.executable), job.launch_mode + "=" + str(job.cfile)]
        if job.launch_mode == "c":
            args.append("w=1024x768" if job.graphics else "-nographics")
        if job.macro_file is not None:
            args.append("m=" + str(job.macro_file))
        process = dict(returncode=None, timed_out=False, pid=None, argv=args,
                       cwd=str(job.directory), graphics=job.graphics, launch_mode=job.launch_mode)
        try:
            process["capabilities"] = require_capability(job.executable, "batch")
            env, configuration = native_environment(job.executable, job.directory)
            process["configuration"] = configuration
            cursor = LogCursor.capture(job.directory / "lspost.msg")
            proc = subprocess.Popen(args, cwd=job.directory, env=env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            process["pid"] = proc.pid
            try:
                stdout, stderr = proc.communicate(timeout=job.timeout)
            except subprocess.TimeoutExpired:
                process["timed_out"] = True
                try:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                       capture_output=True, check=False, timeout=15,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                except (OSError, subprocess.SubprocessError) as exc:
                    process["termination_warning"] = str(exc)
                finally:
                    # Always reap the direct child, including taskkill failures.
                    proc.kill()
                    stdout, stderr = proc.communicate(timeout=15)
            process["returncode"] = proc.returncode
            for name, content in (("stdout.log", stdout), ("stderr.log", stderr)):
                (job.directory / name).write_text(decode(content), encoding="utf8")
            diagnostics = native_errors(cursor.read()) + native_errors(decode(stdout)) + native_errors(decode(stderr))
            process["diagnostics"] = diagnostics
            process["elapsed_seconds"] = round(time.monotonic() - start, 3)
            if process["timed_out"] or proc.returncode != 0 or diagnostics:
                raise RuntimeError("Native batch failed: timeout={}, returncode={}, diagnostics={}".format(
                    process["timed_out"], proc.returncode, diagnostics))
            if job.verify is not None:
                result = JobResult.model_validate(job.verify(process))
                if result.operation != job.operation or result.job_id != job.directory.name:
                    raise ValueError("Batch verifier returned a different job identity")
                return result
            return JobResult(operation=job.operation, job_id=job.directory.name, status="unverified",
                             backend="lsprepost", data=process,
                             scope="Process completed; domain outputs require caller verification")
        except Exception as exc:
            process["elapsed_seconds"] = round(time.monotonic() - start, 3)
            return JobResult(operation=job.operation, job_id=job.directory.name, status="failed",
                             backend="lsprepost", data=process,
                             error=dict(type=type(exc).__name__, message=str(exc)))
