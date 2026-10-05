"""A01 unified script entrypoint using the shared execution backends."""

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import StrictInt

from .core.contracts import Artifact, JobResult
from .core.native_log import native_errors
from .core.script_parameters import cfile_diagnostics, render_cfile
from .core.script_request import ScriptDependency, ScriptOutput, ScriptRequest
from .jobs import atomic_json, fingerprint
from .native import commands as nc
from .outcomes import normalize_outcome
from .programs import count_contract, output_contract


def log_result(path, directory, *, source=None, offset=0):
    raw = path.read_bytes()
    try:
        text, lossy = raw.decode("utf8"), False
    except UnicodeDecodeError:
        text, lossy = raw.decode("utf8", errors="replace"), True
    target = directory / "native-echo.log"
    target.write_bytes(raw)
    identity = fingerprint(target)
    artifact = Artifact(path=str(target), kind="native_log", sha256=identity["sha256"],
                        size_bytes=identity["size"], verification="verified",
                        metadata=dict(source=source or str(path), offset=offset, decoding_lossy=lossy))
    return dict(source=source or str(path), offset=offset, text=text if len(text) <= 32768 else None,
                full_text_path=str(target), inline_omitted=len(text) > 32768,
                errors=native_errors(text), decoding_lossy=lossy), artifact


class ScriptTools:
    def run_script(self, language: Literal["command", "cfile", "scl", "python"], code: str,
                   context: Literal["batch", "session"] = "batch", session_id: str | None = None,
                   model: str | None = None, file_type: Literal["keyword", "d3plot"] = "keyword",
                   outputs: list[ScriptOutput] | None = None, expected_counts: dict[str, int] | None = None,
                   capture_model: bool = False, initial_node_ids: list[StrictInt] | None = None,
                   parameters: dict | None = None, dependencies: list[ScriptDependency] | None = None,
                   launch_mode: Literal["c", "runc"] = "c") -> dict:
        """Run native command/cfile/SCL/embedded Python in batch or the specified session. Return JobResult, request-scoped native log and checked outputs. Python receives PARAMETERS as JSON data and frozen dependency files; arrays return NPZ paths/shape/dtype. Scripts use native permissions."""
        request = ScriptRequest(language=language, code=code, context=context, session_id=session_id, model=model,
                                file_type=file_type, outputs=outputs or [], expected_counts=expected_counts or {},
                                capture_model=capture_model, initial_node_ids=initial_node_ids, parameters=parameters or {},
                                dependencies=dependencies or [], launch_mode=launch_mode)
        declared = output_contract([value.model_dump() for value in request.outputs])
        counts = count_contract(request.expected_counts)
        opened = re.fullmatch(r'\s*(?:open|openc)\s+(keyword|d3plot)\s+(.+?)(?:\s+nodialog)?\s*', code, re.I)
        if context == "session" and opened and (declared or initial_node_ids is not None or capture_model):
            raise ValueError("Open command cannot declare output files, an initial selection or a snapshot")
        rendered = render_cfile(code, request.parameters) if language == "cfile" else code
        if language in ("cfile", "scl", "python"):
            prepared = self.prepare_native_program(language, code=rendered, outputs=declared, expected_counts=counts,
                                                   script_parameters=request.parameters if language == "python" else None,
                                                   dependencies=[d.model_dump() for d in request.dependencies])
            result = self.execute_native_program(prepared["job_id"], prepared["data"]["sha256"], model=model,
                                                 file_type=file_type, session_id=session_id,
                                                 allow_owned_output_context=context == "session" and language == "cfile",
                                                 launch_mode=launch_mode)
            directory = Path(result["job_directory"])
            if context == "session":
                native_dir = Path(result.get("native_request", {}).get("job_directory", directory))
                log = native_dir / "native-session.log"
                metadata = native_dir / "native-session-log.json"
                log_meta = json.loads(metadata.read_text(encoding="utf8")) if metadata.is_file() else {}
            else:
                log, log_meta = directory / "lspost.msg", {}
        elif context == "batch":
            setup = [] if initial_node_ids is None else [nc.selection("clear"), nc.selection_target("node"),
                                                       *[nc.selection_add("node", uid) for uid in initial_node_ids]]
            prepared = self.prepare_native_program("cfile" if setup else language, code="\n".join([*setup, code]), outputs=declared, expected_counts=counts)
            result = self.execute_native_program(prepared["job_id"], prepared["data"]["sha256"], model=model,
                                                 file_type=file_type, graphics=False, capture_model=capture_model,
                                                 inspect_selection=True, launch_mode=launch_mode)
            directory = Path(result["job_directory"])
            log = directory / "lspost.msg"
            log_meta = {}
        else:
            if opened:
                source = opened[2].strip().strip('"')
                result = self.open_in_gui_session(session_id, source, opened[1].lower(), discard=True)
                result["command_staging"] = "Input bytes are staged by the managed open operation; native echo records the actual path"
                if result.get("status") == "succeeded" and any(result["data"]["counts"].get(k) != v for k, v in counts.items()):
                    result.update(status="failed", error=dict(message="Native counts differ from the declared command contract"))
            else:
                result = self.execute_gui_command(session_id, code, outputs=declared, expected_counts=counts,
                                                  initial_node_ids=initial_node_ids, capture_model=capture_model)
            directory = Path(result["job_directory"])
            log = directory / "native-session.log"
            metadata = directory / "native-session-log.json"
            log_meta = json.loads(metadata.read_text(encoding="utf8")) if metadata.is_file() else {}
        normalized = normalize_outcome("run_script", result)
        try:
            echo, artifact = log_result(log, directory, **log_meta)
            status, error = normalized.status, normalized.error
            if echo["errors"]:
                status, error = "failed", dict(type="NativeDiagnostics", message="Native command reported errors", raw=echo["errors"])
            extra = {}
            if language == "cfile":
                text = log.read_text(encoding="utf8", errors="replace")
                extra = dict(rendered_source=rendered, diagnostics=cfile_diagnostics(result.get("executed_source", rendered), text))
            elif language == "scl":
                text = log.read_text(encoding="utf8", errors="replace")
                diagnostics = []
                for message in native_errors(text):
                    match = re.search(r"\bline\s*(?:number\s*)?[:=]?\s*(\d+)", message, re.I)
                    diagnostics.append(dict(line=int(match[1]) if match else None, message=message))
                extra = dict(diagnostics=diagnostics)
            elif language == "python":
                reply_file = directory / "python-result.json"
                if reply_file.is_file():
                    reply = json.loads(reply_file.read_text(encoding="utf8"))
                    extra = dict(python_result=reply)
                    if not reply.get("ok"):
                        status, error = "failed", dict(type="EmbeddedPythonError", message=reply.get("error", "Python failed"),
                                                       traceback=reply.get("traceback"))
            outcome = JobResult(operation="run_script", job_id=normalized.job_id or result.get("request_id"),
                                status=status, backend="lsprepost", artifacts=normalized.artifacts,
                                evidence=(*normalized.evidence, artifact), error=error,
                                data=dict(**normalized.data, language=language, context=context,
                                          requested_source=code, native_echo=echo,
                                          command_staging=result.get("command_staging"), **extra),
                                scope="Native completion and explicit file/count contracts; raw command semantics remain caller-verified")
        except (OSError, ValueError) as exc:
            outcome = JobResult(operation="run_script", status="failed" if normalized.status == "failed" else "unverified",
                                job_id=normalized.job_id or result.get("request_id"), backend="lsprepost", artifacts=normalized.artifacts,
                                error=normalized.error or dict(type=type(exc).__name__, message=str(exc)),
                                data={**normalized.data, "context": context, "language": language,
                                      "native_echo_error": str(exc)})
        atomic_json(directory / "script-result.json", outcome.model_dump(mode="json"))
        return outcome.model_dump(mode="json")
