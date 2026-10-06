"""Explicit user-directed native programs and numeric macro templates.

Scripts run with LS-PrePost's normal permissions. This is an execution interface,
not a sandbox for untrusted downloaded code.
"""

import hashlib
import json
import math
import re
from pathlib import Path

from .core.native_log import native_errors, read_delta
from .jobs import atomic_json, check_artifact, fingerprint, now
from .native import commands as nc
from .native_results import stage
from .program_bundle import (
    capture_dependencies,
    checked_dependencies,
    identity,
    python_wrapper,
    validate_script_references,
    write_dependencies,
)
from .runner import execute, failure_message

LANGUAGES = {"command": "cfile", "cfile": "cfile", "scl": "scl", "python": "py"}
PLACEHOLDER = re.compile(r"\{\{([A-Za-z][A-Za-z0-9_]*)\}\}")
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
    "contract.json",
    "macro.json",
    "source.mac",
    "bound.mac",
    "cwd.py",
    "gui-python.py",
    "before.json",
    "after.json",
    "commands.json",
    "native.log",
    "stdout.log",
    "stderr.log",
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
            or name.lower().startswith("lspost.")
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
        dependencies: list[dict] | None = None,
        macro_name: str | None = None,
    ) -> dict:
        """Prepare command/cfile/SCL/application-Python or native macro source without execution. language=macro binds one *macro block (macro_name required for multiple blocks), literal numeric parameter defaults and &name/(n/e/p) user IDs into an explicit cfile; retains source.mac and native-editable bound.mac. Interactive/unresolved picks are rejected. Dependencies {path,name} are frozen. Returns reviewed rendered source and execution SHA256; no global macro installation."""
        if language not in {*LANGUAGES, "macro"} or (code is None) == (path is None):
            raise ValueError("Choose command/cfile/scl/python/macro and exactly one of code/path")
        if language != "macro" and macro_name is not None:
            raise ValueError("macro_name only applies to native macro source")
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
        native_macro = None
        if language == "macro":
            from .native_macros import compile_macro

            rendered, bound_macro, native_macro = compile_macro(code, params, macro_name)
            language = "cfile"
        else:
            rendered = render(code, params)
        outputs, counts = output_contract(outputs), count_contract(expected_counts)
        captured = capture_dependencies(self.settings, dependencies, outputs)
        graph = validate_script_references(rendered.encode("utf8"), language, captured)
        directory, manifest = self.jobs.create(
            "prepare_native_program", dict(language=language, parameters=params)
        )
        program = directory / ("program." + LANGUAGES[language])
        if language in ("command", "cfile"):
            nc.write_cfile(program, rendered)
        elif language == "scl":
            nc.write_scl(program, rendered)
        else:
            program.write_text(rendered, encoding="utf8")
        if native_macro is not None:
            (directory / "source.mac").write_text(code, encoding="utf8")
            (directory / "bound.mac").write_text(bound_macro, encoding="utf8")
            native_macro["source_text_sha256"] = hashlib.sha256(code.encode("utf8")).hexdigest()
        write_dependencies(directory, captured)
        contract = dict(
            language=language,
            program=program.name,
            source_sha256=hashlib.sha256(program.read_bytes()).hexdigest(),
            dependencies=[item for item, _ in captured],
            script_references=graph,
            outputs=outputs,
            expected_counts=counts,
        )
        contract["sha256"] = identity(program.read_bytes(), contract)
        if native_macro is not None:
            contract["native_macro"] = native_macro
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
        if native_macro is not None:
            manifest["artifacts"].extend(check_artifact(directory / name, "text") for name in ("source.mac", "bound.mac"))
        atomic_json(directory / "job.json", manifest)
        return manifest

    def execute_native_program(
        self,
        prepared_job_id: str,
        expected_sha256: str,
        model: str | None = None,
        file_type: str = "keyword",
        graphics: bool = False,
        session_id: str | None = None,
    ) -> dict:
        """Execute a verified prepared source/dependency bundle. Without session_id, use an isolated native process and optional staged model; with session_id, use the current owned GUI and omit model. GUI scripts must retain its model context; keyword baseline is checkpointed, raw effects invalidate cached selections/fringes. Requires the prepared execution SHA256. No declared output/count contract means completed_unverified."""
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
        if identity(content, contract) != expected_sha256 or contract["sha256"] != expected_sha256:
            raise ValueError("Source changed since preparation; inspect and prepare again")
        outputs, counts = output_contract(contract["outputs"]), count_contract(contract["expected_counts"])
        captured = checked_dependencies(prepared_dir, contract)
        validate_script_references(content, language, captured)
        if session_id is not None:
            if model is not None:
                raise ValueError("GUI programs use the current model; open it separately and omit model")
            from .gui_programs import execute_prepared

            return execute_prepared(self, session_id, prepared_job_id, expected_sha256, contract, content, captured)
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
            write_dependencies(directory, captured)
            atomic_json(directory / "contract.json", contract)
            commands = ["new"]
            if source:
                commands.append(
                    nc.open_model("d3plot", "d3plot", openc=True) if file_type == "d3plot" else nc.open_model("input_data")
                )
            if language in ("command", "cfile"):
                commands.append(content.decode("utf8"))
            elif language == "scl":
                commands.append(nc.run_script("program.scl", "scl"))
            else:
                wrapper = python_wrapper(directory, [item["name"] for item, _ in captured])
                (directory / "bootstrap.py").write_text(wrapper, encoding="utf8")
                commands.append(nc.run_script("bootstrap.py"))
            nc.write_scl(directory / "complete.scl",
                "/*LS-SCRIPT*/\ndefine:\nvoid main(void){\nFILE *fp;\nInt n,e,s;\n"
                'n=SCLGetDataCenterInt("num_nodes");\ne=SCLGetDataCenterInt("num_elements");\n'
                's=SCLGetDataCenterInt("num_states");\nfp=fopen("complete.txt","w");\n'
                'fprintf(fp,"%d %d %d\\n",n,e,s);\nfclose(fp);\n}\nmain();\n',
            )
            commands += [nc.run_script("complete.scl", "scl"), "exit"]
            command_file = directory / "commands.cfile"
            nc.write_cfile(command_file, commands)
            manifest.update(status="running", started_at=now())
            atomic_json(directory / "job.json", manifest)
            process = execute(exe, command_file, directory, timeout=self.settings.timeout, graphics=graphics)
            manifest["process"] = process
            if process.get("engine_status") == "failed" or process["timed_out"] or process["returncode"] != 0:
                raise RuntimeError(failure_message(process, "Native program process failed or timed out"))
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
            checked_dependencies(directory, contract)
            manifest.update(
                status="succeeded" if outputs or counts else "completed_unverified",
                artifacts=artifacts,
                data=dict(
                    counts=actual,
                    dependency_count=len(captured),
                    bundle_sha256=expected_sha256,
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
            if meta.get("managed_fringe") is not None:
                meta["managed_fringe"]["status"] = "changed_by_raw_command"
            if log.exists():
                diagnostics = native_errors(read_delta(log, offset, existed=True))
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
        dependencies: list[dict] | None = None,
    ) -> dict:
        """Save a command/cfile/SCL/Python macro with numeric {{name}} entry parameters, explicit outputs and frozen dependency assets. Does not execute or install global LS-PrePost menu/shortcut macros."""
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
        captured = capture_dependencies(self.settings, dependencies, definition["outputs"])
        write_dependencies(directory / "assets", captured)
        definition["dependencies"] = [item for item, _ in captured]
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
        session_id: str | None = None,
    ) -> dict:
        """Instantiate a selected macro with its frozen assets and numeric entry parameters; use an isolated native process or an explicit current GUI session_id. Retains macro/bundle identities and native evidence. GUI recordings retain the macro parameter call rather than expanding its internal execution steps."""
        source = self.settings.input_path(path)
        macro = json.loads(source.read_text(encoding="utf8"))
        if macro.get("schema_version") != 1 or macro.get("kind") != "native_macro":
            raise ValueError("Unsupported native macro")
        parameters = numeric_parameters(parameters or {})
        if set(parameters) - macro["defaults"].keys():
            raise ValueError("Unknown macro parameters")
        checked_dependencies(source.parent / "assets", macro)
        prepared = self.prepare_native_program(
            macro["language"],
            code=macro["code"],
            parameters={**macro["defaults"], **parameters},
            outputs=macro["outputs"],
            expected_counts=macro["expected_counts"],
            dependencies=[dict(path=str(source.parent / "assets" / item["name"]), name=item["name"])
                          for item in macro.get("dependencies", [])],
        )
        if session_id is not None:
            if model is not None:
                raise ValueError("GUI macros use the current model; omit model")
            from .gui_programs import execute_prepared

            folder = self.jobs.root / prepared["job_id"]
            contract = json.loads((folder / "contract.json").read_text(encoding="utf8"))
            result = execute_prepared(self, session_id, prepared["job_id"], prepared["data"]["sha256"], contract,
                (folder / contract["program"]).read_bytes(), checked_dependencies(folder, contract),
                journal_action="run_native_macro", journal_parameters=dict(path=path, parameters=parameters))
        else:
            result = self.execute_native_program(
                prepared["job_id"], prepared["data"]["sha256"], model, file_type, graphics
            )
        result["macro_source"] = fingerprint(source)
        atomic_json(Path(result["job_directory"]) / "job.json", result)
        return result
