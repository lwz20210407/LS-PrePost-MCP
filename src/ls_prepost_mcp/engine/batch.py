"""One isolated, owned process per batch job."""

import subprocess
import time

from ..core.contracts import JobResult
from ..core.native_log import LogCursor, decode_with_info, native_errors
from ..native.versions import require_capability
from .environment import native_environment
from .jobs import BatchJob
from .processes import OwnedProcess


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
            env, configuration = native_environment(job.executable, job.directory, batch=True)
            process["configuration"] = configuration
            cursor = LogCursor.capture(job.directory / "lspost.msg")
            with OwnedProcess(args, cwd=job.directory, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as owned:
                proc = owned.process
                process.update(pid=proc.pid, process_isolation=owned.mechanism)
                try:
                    stdout, stderr = proc.communicate(timeout=job.timeout)
                except subprocess.TimeoutExpired:
                    process["timed_out"] = True
                    owned.stop()
                    stdout, stderr = proc.communicate(timeout=15)
                process["returncode"] = proc.returncode
            streams = (("stdout.log", stdout), ("stderr.log", stderr))
            for name, content in streams:
                (job.directory / (name + ".raw")).write_bytes(content)
            decoded = []
            process["log_decoding"] = {}
            for name, content in streams:
                text, info = decode_with_info(content)
                (job.directory / name).write_text(text, encoding="utf8")
                process["log_decoding"][name] = dict(info, raw_file=name + ".raw")
                decoded.append(text)
            log_text, log_info = cursor.decode_with_info(cursor.read_bytes())
            process["log_decoding"]["lspost.msg"] = log_info
            if any(info["lossy"] for info in process["log_decoding"].values()):
                raise UnicodeError("Native logs required replacement decoding; inspect raw bytes and LSPP_NATIVE_LOG_ENCODING")
            diagnostics = native_errors(log_text) + [error for text in decoded for error in native_errors(text)]
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
            message = str(exc)
            return JobResult(operation=job.operation, job_id=job.directory.name, status="failed",
                             backend="lsprepost", data=process,
                             warnings=getattr(exc, "__notes__", ()),
                             error=dict(type=type(exc).__name__, message=message if message.strip() else type(exc).__name__))
