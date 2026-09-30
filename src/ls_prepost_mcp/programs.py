"""Explicit user-directed native programs and numeric macro templates.

Scripts run with LS-PrePost's normal permissions. This is an execution interface,
not a sandbox for untrusted downloaded code.
"""

import hashlib
import json
import math
import re
from pathlib import Path

from .jobs import atomic_json, check_artifact, fingerprint, now
from .native_results import stage
from .runner import execute

LANGUAGES = {"command": "cfile", "cfile": "cfile", "scl": "scl", "python": "py"}
PLACEHOLDER = re.compile(r"\{\{([A-Za-z][A-Za-z0-9_]*)\}\}")
NATIVE_ERROR = re.compile(
    r"^\s*(?:\*+\s*)?(?:invalid command\b|error while compiling\b|error occurred in parsing script\b|syntax error\b|runtime error\b)",
    re.IGNORECASE,
)
RESERVED = {
    "program.cfile",
    "program.scl",
    "program.py",
    "commands.cfile",
    "complete.scl",
    "complete.txt",
    "python-result.json",
    "bootstrap.py",
    "job.json",
    "input_data",
    "d3plot",
}


def numeric_parameters(values):
    if not isinstance(values, dict) or len(values) > 100:
        raise ValueError("Expected at most 100 named numeric parameters")
    for key, value in values.items():
        if (
            not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key)
            or type(value) not in (int, float)
            or not math.isfinite(value)
        ):
            raise ValueError("Macro parameters must be finite named numbers, not code or paths")
    return values


def native_errors(text):
    return [line.strip() for line in text.splitlines() if NATIVE_ERROR.search(line)][:30]


def render(code, parameters):
    numeric_parameters(parameters)
    names = set(PLACEHOLDER.findall(code))
    if names - parameters.keys():
        raise ValueError("Missing macro parameters: " + ", ".join(sorted(names - parameters.keys())))
    return PLACEHOLDER.sub(lambda m: repr(parameters[m[1]]), code)


def output_contract(outputs):
    outputs = [] if outputs is None else outputs
    if not isinstance(outputs, list) or len(outputs) > 50:
        raise ValueError("Expected at most 50 explicit output files")
    names = set()
    for item in outputs:
        if not isinstance(item, dict) or set(item) != {"name", "kind"}:
            raise ValueError("Outputs require name and kind")
        name = item["name"]
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", name)
            or name.endswith(".")
            or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])", name.split(".")[0])
            or name.lower() in RESERVED
            or name.lower() in names
        ):
            raise ValueError("Output must be a unique, non-reserved job-local filename")
        if item["kind"] not in ("keyword", "csv", "json", "text", "png"):
            raise ValueError("Unsupported output validation kind")
        names.add(name.lower())
    return outputs


def count_contract(counts):
    counts = {} if counts is None else counts
    if not isinstance(counts, dict) or set(counts) - {"nodes", "elements", "states"}:
        raise ValueError("Expected counts support nodes, elements and states")
    if any(type(v) is not int or v < 0 for v in counts.values()):
        raise ValueError("Expected counts must be nonnegative integers")
    return counts


def gui_command(command):
    if (
        not isinstance(command, str)
        or not command.strip()
        or len(command) > 8192
        or any(x in command for x in "\r\n\x00")
    ):
        raise ValueError("Provide one finite native command line")
    head = command.strip().split()[0].lower()
    if head in {
        "new",
        "exit",
        "quit",
        "t",
        "system",
        "syscall",
        "runpython",
        "runscript",
        "open",
        "openc",
        "setpythonhome",
    }:
        raise ValueError(
            "Use the dedicated session/open/program tool for lifecycle, file or script commands; host shell/config changes are excluded"
        )
    return command


class ProgramTools:
    def prepare_native_program(
        self,
        language: str,
        code: str | None = None,
        path: str | None = None,
        parameters: dict | None = None,
        outputs: list[dict] | None = None,
        expected_counts: dict | None = None,
    ) -> dict:
        """Prepare user-directed command/cfile/SCL/application-Python source, numeric substitutions and output contracts without execution. Returns exact rendered source and its SHA256 for execution."""
        if language not in LANGUAGES or (code is None) == (path is None):
            raise ValueError("Choose command/cfile/scl/python and exactly one of code/path")
        source = self.settings.input_path(path) if path else None
        if source:
            if source.stat().st_size > 1024 * 1024:
                raise ValueError("Program exceeds 1 MiB")
            code = source.read_text(encoding="utf-8-sig")
        if (
            not isinstance(code, str)
            or not code.strip()
            or len(code.encode("utf8")) > 1024 * 1024
            or "\x00" in code
        ):
            raise ValueError("Expected nonempty source up to 1 MiB")
        if language == "command" and len(code.strip().splitlines()) != 1:
            raise ValueError("Use cfile for multiple command lines")
        params = numeric_parameters(parameters or {})
        rendered = render(code, params)
        outputs, counts = output_contract(outputs), count_contract(expected_counts)
        directory, manifest = self.jobs.create(
            "prepare_native_program", dict(language=language, parameters=params)
        )
        program = directory / ("program." + LANGUAGES[language])
        program.write_text(rendered, encoding="utf8")
        contract = dict(
            language=language,
            program=program.name,
            sha256=hashlib.sha256(program.read_bytes()).hexdigest(),
            outputs=outputs,
            expected_counts=counts,
        )
        atomic_json(directory / "contract.json", contract)
        manifest.update(
            status="prepared",
            job_directory=str(directory),
            data={**contract, "rendered_source": rendered},
            artifacts=[check_artifact(program, "text")],
            finished_at=now(),
            execution_scope="Trusted user-directed native code; normal application permissions, no security sandbox",
        )
        if source:
            manifest["source"] = fingerprint(source)
        atomic_json(directory / "job.json", manifest)
        return manifest

    def execute_native_program(
        self,
        prepared_job_id: str,
        expected_sha256: str,
        model: str | None = None,
        file_type: str = "keyword",
        graphics: bool = False,
    ) -> dict:
        """Execute the exact prepared native program in an isolated LS-PrePost process, staging model input. Requires matching source SHA256. No declared output/count contract means completed_unverified, never a validated success."""
        prepared = self.jobs.get(prepared_job_id)
        if prepared["action"] != "prepare_native_program":
            raise ValueError("Expected a prepared native program")
        prepared_dir = self.jobs.root / prepared_job_id
        contract = json.loads((prepared_dir / "contract.json").read_text(encoding="utf8"))
        language = contract["language"]
        if language not in LANGUAGES or contract["program"] != "program." + LANGUAGES[language]:
            raise ValueError("Invalid program contract")
        program = prepared_dir / contract["program"]
        content = program.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected_sha256 or contract["sha256"] != expected_sha256:
            raise ValueError("Source changed since preparation; inspect and prepare again")
        outputs, counts = output_contract(contract["outputs"]), count_contract(contract["expected_counts"])
        if file_type not in ("keyword", "d3plot"):
            raise ValueError("Unsupported input type")
        source = self.settings.input_path(model) if model else None
        if source and file_type == "keyword":
            self.settings.check_keyword_includes(source)
            if any(
                s.strip().upper().startswith("*INCLUDE")
                for s in source.read_text(errors="replace").splitlines()
            ):
                raise ValueError("Program staging requires a flattened keyword model")
        exe = self.settings.native_executable()
        directory, manifest = self.jobs.create(
            "execute_native_program",
            dict(prepared_job_id=prepared_job_id, sha256=expected_sha256, language=language),
        )
        manifest.update(
            backend="lsprepost",
            native_channel=language,
            executable=fingerprint(exe),
            job_directory=str(directory),
        )
        try:
            sources, before = (
                stage(self.settings, source, directory, file_type == "d3plot") if source else ([], [])
            )
            manifest["inputs"] = before
            (directory / contract["program"]).write_bytes(content)
            atomic_json(directory / "contract.json", contract)
            commands = ["new"]
            if source:
                commands.append(
                    'openc d3plot "d3plot"' if file_type == "d3plot" else 'open keyword "input_data"'
                )
            if language in ("command", "cfile"):
                commands.append(content.decode("utf8"))
            elif language == "scl":
                commands.append("runscript program.scl")
            else:
                wrapper = (
                    "import os,json,runpy,traceback\n"
                    "os.chdir(" + repr(str(directory)) + ")\n"
                    "reply={'ok':False}\ntry:\n"
                    "    runpy.run_path('program.py',run_name='__main__')\n"
                    "    reply['ok']=True\nexcept BaseException as e:\n"
                    "    reply.update(error=type(e).__name__+': '+str(e),traceback=traceback.format_exc())\n"
                    "json.dump(reply,open('python-result.json','w'))\n"
                )
                (directory / "bootstrap.py").write_text(wrapper, encoding="utf8")
                commands.append("runpython bootstrap.py")
            (directory / "complete.scl").write_text(
                "/*LS-SCRIPT*/\ndefine:\nvoid main(void){\nFILE *fp;\nInt n,e,s;\n"
                'n=SCLGetDataCenterInt("num_nodes");\ne=SCLGetDataCenterInt("num_elements");\n'
                's=SCLGetDataCenterInt("num_states");\nfp=fopen("complete.txt","w");\n'
                'fprintf(fp,"%d %d %d\\n",n,e,s);\nfclose(fp);\n}\nmain();\n',
                encoding="ascii",
            )
            commands += ["runscript complete.scl", "exit"]
            command_file = directory / "commands.cfile"
            command_file.write_text("\n".join(commands) + "\n", encoding="utf8")
            manifest.update(status="running", started_at=now())
            atomic_json(directory / "job.json", manifest)
            process = execute(exe, command_file, directory, timeout=self.settings.timeout, graphics=graphics)
            manifest["process"] = process
            if process["timed_out"] or process["returncode"] != 0:
                raise RuntimeError("Native program process failed or timed out")
            diagnostics = []
            for log in (directory / "lspost.msg", directory / "stdout.log", directory / "stderr.log"):
                if log.exists():
                    diagnostics.extend(native_errors(log.read_text(encoding="utf8", errors="replace")))
            if diagnostics:
                manifest["native_diagnostics"] = list(dict.fromkeys(diagnostics))
                raise RuntimeError("Native command/script diagnostics reported errors")
            if language == "python":
                reply = json.loads((directory / "python-result.json").read_text())
                if not reply.get("ok"):
                    raise RuntimeError(reply.get("error", "Embedded Python failed"))
            actual = dict(
                zip(
                    ("nodes", "elements", "states"),
                    [int(x) for x in (directory / "complete.txt").read_text().split()],
                    strict=True,
                )
            )
            if any(actual[k] != v for k, v in counts.items()):
                raise ValueError("Native model counts do not match the declared contract")
            artifacts = []
            for item in outputs:
                output = directory / item["name"]
                if output.resolve().parent != directory.resolve():
                    raise ValueError("Output escaped job directory")
                if item["kind"] == "json":
                    json.loads(output.read_text(encoding="utf8"))
                artifacts.append(check_artifact(output, item["kind"]))
            if [fingerprint(p) for p in sources] != before:
                raise RuntimeError("Original input changed during execution")
            manifest.update(
                status="succeeded" if outputs or counts else "completed_unverified",
                artifacts=artifacts,
                data=dict(
                    counts=actual,
                    declared_contract_verified=bool(outputs or counts),
                    scope="Completion plus declared file/count checks only; no proof of every command or physical validity",
                ),
            )
        except Exception as exc:
            manifest.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
        manifest.update(
            finished_at=now(),
            logs=[str(p) for p in directory.glob("*.log")] + [str(p) for p in directory.glob("lspost.*")],
        )
        atomic_json(directory / "job.json", manifest)
        return manifest

    def execute_gui_command(
        self,
        session_id: str,
        command: str,
        outputs: list[dict] | None = None,
        expected_counts: dict | None = None,
    ) -> dict:
        """Run one original LS-PrePost command through the owned GUI command-entry/cfile bridge. Record raw source, native inventory and explicit output checks; unspecified semantics remain unverified."""
        command, outputs, counts = (
            gui_command(command),
            output_contract(outputs),
            count_contract(expected_counts),
        )
        manager = self._session_manager()
        with manager.lock(session_id):
            meta = manager.read(session_id)
            if meta.get("bridge_protocol", 1) < 2:
                raise ValueError("This session predates the raw-command bridge; save a checkpoint and start a new session")
            if meta["state"] == "uncertain":
                raise ValueError("Resolve/restore the uncertain session before raw commands")
            parameters = dict(command=command, expected_counts=counts)
            log = manager.directory(session_id) / "lspost.msg"
            offset = log.stat().st_size if log.exists() else 0
            result = manager.dispatch(
                session_id, "raw_command", parameters, artifacts=[(o["name"], o["kind"]) for o in outputs]
            )
            meta = manager.read(session_id)
            meta["dirty"] = True
            if log.exists():
                with log.open("rb") as stream:
                    stream.seek(offset)
                    diagnostics = native_errors(stream.read().decode("utf8", errors="replace"))
                if diagnostics:
                    result.update(
                        status="failed",
                        error=dict(
                            message="Native command diagnostics reported errors", diagnostics=diagnostics
                        ),
                    )
                    meta["state"] = "uncertain"
            manager.save(session_id, meta)
            if result["status"] == "succeeded" and not outputs and not counts:
                result["status"] = "completed_unverified"
            result["verification_scope"] = (
                "Declared outputs/counts only; no inferred semantics for raw commands"
            )
            atomic_json(Path(result["job_directory"]) / "operation.json", result)
            manager.journal(
                session_id,
                dict(
                    action="execute_gui_command",
                    parameters=dict(command=command, outputs=outputs, expected_counts=counts),
                    result=result,
                ),
            )
            return result

    def create_native_macro(
        self,
        name: str,
        language: str,
        code: str,
        defaults: dict,
        outputs: list[dict] | None = None,
        expected_counts: dict | None = None,
    ) -> dict:
        """Save a reusable command/cfile/SCL/Python macro with numeric {{name}} parameters and explicit outputs. Does not execute or install global LS-PrePost macros."""
        if not isinstance(name, str) or not name.strip() or len(name) > 120 or language not in LANGUAGES:
            raise ValueError("Invalid macro name/language")
        if (
            not isinstance(code, str)
            or not code.strip()
            or len(code.encode("utf8")) > 1024 * 1024
            or "\x00" in code
        ):
            raise ValueError("Expected nonempty macro source up to 1 MiB")
        render(code, numeric_parameters(defaults))
        definition = dict(
            schema_version=1,
            kind="native_macro",
            name=name,
            language=language,
            code=code,
            defaults=defaults,
            outputs=output_contract(outputs),
            expected_counts=count_contract(expected_counts),
        )
        directory, manifest = self.jobs.create("create_native_macro", dict(name=name, language=language))
        atomic_json(directory / "macro.json", definition)
        manifest.update(
            status="succeeded",
            job_directory=str(directory),
            artifacts=[check_artifact(directory / "macro.json", "json")],
            finished_at=now(),
        )
        atomic_json(directory / "job.json", manifest)
        return manifest

    def run_native_macro(
        self,
        path: str,
        parameters: dict | None = None,
        model: str | None = None,
        file_type: str = "keyword",
        graphics: bool = False,
    ) -> dict:
        """Instantiate and run an explicitly selected native macro in an isolated LS-PrePost process. Retains macro identity, rendered program and full native evidence."""
        source = self.settings.input_path(path)
        macro = json.loads(source.read_text(encoding="utf8"))
        if macro.get("schema_version") != 1 or macro.get("kind") != "native_macro":
            raise ValueError("Unsupported native macro")
        parameters = numeric_parameters(parameters or {})
        if set(parameters) - macro["defaults"].keys():
            raise ValueError("Unknown macro parameters")
        prepared = self.prepare_native_program(
            macro["language"],
            code=macro["code"],
            parameters={**macro["defaults"], **parameters},
            outputs=macro["outputs"],
            expected_counts=macro["expected_counts"],
        )
        result = self.execute_native_program(
            prepared["job_id"], prepared["data"]["sha256"], model, file_type, graphics
        )
        result["macro_source"] = fingerprint(source)
        atomic_json(Path(result["job_directory"]) / "job.json", result)
        return result
