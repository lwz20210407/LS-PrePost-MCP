"""I04 pytest adapter for existing acceptance scripts and their domain assertions."""

import hashlib
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILE_CASES = {"run_engineering_unit_acceptance", "run_workflow_gate_acceptance"}


@dataclass(frozen=True)
class Case:
    script: Path
    variant: str = "native"

    @property
    def id(self):
        return self.script.stem.removeprefix("run_") + "." + self.variant

    @property
    def gui(self):
        return self.variant != "file" and not (self.script.stem == "run_program_acceptance" and self.variant == "batch")


def cases():
    result = []
    for path in sorted((ROOT / "tools").glob("run_*.py")):
        if path.stem in FILE_CASES:
            result.append(Case(path, "file"))
        elif path.stem == "run_program_acceptance":
            result.extend((Case(path, "batch"), Case(path, "gui")))
        elif path.stem == "run_parameter_study_acceptance":
            result.extend((Case(path, "file"), Case(path, "gui")))
        else:
            result.append(Case(path))
    return result


def parser_schema(script):
    """Use argparse's own parser, without executing the script's acceptance body.

    A separate interpreter intercepts parse_args after imports and parser setup.
    No native entrypoint runs; this also handles loop-generated CLI arguments.
    """
    code = '''import argparse,json,runpy,sys,os
def capture(self,*args,**kwargs):
    rows=[dict(flags=a.option_strings,required=a.required,nargs=a.nargs,
               boolean=isinstance(a,(argparse._StoreTrueAction,argparse._StoreFalseAction)))
          for a in self._actions if a.dest!='help']
    print(json.dumps(rows))
    raise SystemExit(0)
argparse.ArgumentParser.parse_args=capture
sys.path.insert(0,os.path.dirname(sys.argv[1]))
runpy.run_path(sys.argv[1],run_name='__main__')
'''
    result = subprocess.run([sys.executable, "-B", "-c", code, str(script)], cwd=ROOT,
                            env=python_environment(), capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError("Cannot inspect {}: {}".format(script.name, result.stderr[-2000:]))
    return json.loads(result.stdout)


def python_environment(directory=None):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT / "src") + os.pathsep + str(ROOT))
    if directory is not None:
        temp = directory / "tmp"
        temp.mkdir()
        env.update(TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp), MPLCONFIGDIR=str(temp / "matplotlib"))
    return env


def resolve_value(value):
    if not isinstance(value, dict):
        return value
    if set(value) - {"corpus", "member"} or not isinstance(value.get("corpus"), str):
        raise ValueError("Input reference requires corpus ID and optional relative member")
    from tools.fetch_corpus import destination, entries, load_registry, resolve

    directory = os.environ.get("LSPP_CORPUS_DIR")
    if not directory:
        raise ValueError("Set LSPP_CORPUS_DIR for corpus references")
    entry = entries(load_registry()).get(value["corpus"])
    if entry is None:
        raise ValueError("Unknown corpus ID")
    path = resolve(entry, Path(directory))
    if "member" in value:
        if not path.is_dir():
            raise ValueError("A corpus member requires a directory reference")
        path = destination(path, value["member"])
        if not path.is_file():
            raise ValueError("Corpus member is not a file")
    return str(path)


def arguments(case, schema, supplied, directory, executable):
    if not isinstance(supplied, dict):
        raise ValueError("Case inputs must be an object")
    flags = {row["flags"][0]: row for row in schema}
    values = {"--" + k.replace("_", "-"): resolve_value(v) for k, v in supplied.items()}
    if set(values) - flags.keys():
        raise ValueError("Unknown case options: " + ", ".join(sorted(set(values) - flags.keys())))
    protected = {"--workspace", "--executable", "--output", "--resume", "--keep-open", "--skip-python", "--stop-file", "--hold-seconds", "--gui"}
    if set(values) & protected:
        raise ValueError("Runner owns output/lifetime/full-coverage options")
    values["--workspace"] = str(directory)
    if "--executable" in flags and case.variant != "file":
        if not executable:
            raise ValueError("Set --native-executable, LSPP_ENGINE_EXECUTABLE or LSPP_EXECUTABLE")
        values["--executable"] = str(executable)
    if "--output" in flags:
        values["--output"] = str(directory / "native-results.json")
    if case.script.stem == "run_program_acceptance" and case.variant == "gui":
        values["--gui"] = True
    missing = [flag for flag, row in flags.items() if row["required"] and flag not in values]
    if missing:
        raise ValueError("Missing case inputs: " + ", ".join(missing))
    argv = []
    for flag, value in values.items():
        if flags[flag]["boolean"]:
            if type(value) is not bool:
                raise ValueError("Boolean option requires true/false")
            if value:
                argv.append(flag)
        else:
            nargs = flags[flag]["nargs"]
            if isinstance(value, list) and nargs in (None, "?"):
                raise ValueError("Scalar CLI option cannot receive a list")
            items = value if isinstance(value, list) else [value]
            if not items or any(type(item) not in (str, int, float) for item in items):
                raise ValueError("CLI values must be scalars or nonempty scalar lists")
            if any(str(item).startswith("--") for item in items):
                raise ValueError("CLI input cannot inject another option")
            argv.extend([flag, *map(str, items)])
    return argv


def verify_reports(case, directory):
    paths = [directory / "native-results.json"] if case.script.stem == "run_native_acceptance" else sorted(directory.rglob("acceptance.json"))
    if not paths:
        raise AssertionError("No fresh acceptance report")
    evidence = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf8"))
        if not isinstance(data, (dict, list)) or not data:
            raise AssertionError("Empty/invalid acceptance report")
        if isinstance(data, dict) and "status" in data and data["status"] != "succeeded":
            raise AssertionError("Acceptance report rejected: " + str(data["status"]))
        if case.script.stem == "run_native_acceptance":
            if not isinstance(data, list) or any(item.get("result", {}).get("status") != "succeeded" for item in data):
                raise AssertionError("Native inventory contains a failed or unverified case")
        evidence.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return evidence


def terminate_owned_tree(process, owner):
    import psutil

    try:
        if owner is None or not owner.is_running():
            return
        children = owner.children(recursive=True)
        for child in reversed(children):
            try:
                child.kill()  # psutil checks PID reuse against its cached creation time.
            except psutil.NoSuchProcess:
                pass
        owner.kill()
    except psutil.NoSuchProcess:
        pass
    process.wait(timeout=15)


def cleanup_sessions(directory):
    """Only session identities written inside this fresh case's output tree."""
    import psutil

    from ls_prepost_mcp.sessions import alive

    for path in directory.rglob("session.json"):
        data = json.loads(path.read_text(encoding="utf8"))
        identity = data.get("process")
        if identity and alive(identity):
            owned = psutil.Process(identity["pid"])
            if owned.create_time() != identity["create_time"]:
                continue
            owned.terminate()
            try:
                owned.wait(timeout=10)
            except psutil.TimeoutExpired:
                owned.kill()
                owned.wait(timeout=10)


def run_case(case, argv, directory, timeout):
    import psutil

    started = time.monotonic()
    directory.mkdir(parents=True, exist_ok=False)
    env = python_environment(directory)
    try:
        with (directory / "stdout.log").open("wb") as out, (directory / "stderr.log").open("wb") as err:
            process = subprocess.Popen([sys.executable, "-B", str(case.script), *argv], cwd=ROOT, env=env,
                                       stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                owner = psutil.Process(process.pid)
                owner.create_time()  # Capture identity before waiting, not after a timeout.
            except psutil.NoSuchProcess:
                owner = None
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                terminate_owned_tree(process, owner)
                raise AssertionError("Acceptance timeout; owned process tree stopped") from None
        if code:
            raise AssertionError("Acceptance exit {}: inspect {}".format(code, directory / "stderr.log"))
        return dict(case=case.id, elapsed_seconds=time.monotonic() - started,
                    evidence=verify_reports(case, directory), script_sha256=hashlib.sha256(case.script.read_bytes()).hexdigest())
    finally:
        cleanup_sessions(directory)


def pytest_addoption(parser):
    group = parser.getgroup("lspp-native")
    group.addoption("--run-native", action="store_true", help="Run migrated acceptance scripts")
    group.addoption("--native-gui", action="store_true", help="Use the operator-approved GUI time window")
    group.addoption("--native-output", help="Fresh external directory for all acceptance evidence and reports")
    group.addoption("--native-executable", default=os.environ.get("LSPP_ENGINE_EXECUTABLE") or os.environ.get("LSPP_EXECUTABLE"))
    group.addoption("--native-fixture", default=os.environ.get("LSPP_ENGINE_FIXTURE"), help="Original synthetic engine fixture directory")
    group.addoption("--native-inputs", default=os.environ.get("LSPP_NATIVE_INPUTS"), help="External JSON mapping case IDs to CLI inputs")
    group.addoption("--native-timeout", type=float, default=600)
    group.addoption("--native-strict", action="store_true", help="Fail rather than skip unavailable GUI/inputs")
    group.addoption("--native-executable-410", help="4.10 installation for the transferred remote probes")
    group.addoption("--remote-capture", action="store_true", help="Capture all 13 UU probes in an explicitly armed window")
    group.addoption("--remote-evidence", help="Existing externally stored UU capture to verify after confirmation")
    group.addoption("--remote-confirmation", help="External operator window JSON; never infer UU status from WTS")
    group.addoption("--remote-timeout", type=float, default=2700)


DIFF_COMMAND = ["git", "-c", "core.quotepath=true", "diff", "HEAD", "--binary", "--no-ext-diff",
                "--no-color", "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/",
                "--diff-algorithm=myers", "--no-renames", "-U3", "--inter-hunk-context=0"]


def execution_identity(root=ROOT, report_directory=None):
    """Bind native evidence to actual Git HEAD and source bytes, including edits."""
    files = {}
    for folder in ("src", "tools", "tests"):
        for path in sorted((root / folder).rglob("*")):
            if path.is_file() and path.suffix in (".py", ".json", ".yaml", ".cfile", ".scl", ".mac"):
                files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ("pyproject.toml", "uv.lock"):
        if (root / name).is_file():
            files[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    head, dirty, diff_sha256, patch = None, None, None, None
    try:
        top = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=root,
                                      stderr=subprocess.DEVNULL, text=True, timeout=10).strip()
        if Path(top).resolve() == root.resolve():
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True, timeout=10).strip()
            dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, timeout=10))
            patch = subprocess.check_output(DIFF_COMMAND, cwd=root, timeout=10)
            diff_sha256 = hashlib.sha256(patch).hexdigest()
    except (OSError, subprocess.SubprocessError):
        pass
    patch_name = None
    if patch is not None and report_directory is not None:
        if Path(report_directory).resolve().is_relative_to(root.resolve()):
            raise ValueError("Working-tree patches must stay outside the repository")
        patch_name = "working-tree.patch"
        (Path(report_directory) / patch_name).write_bytes(patch)
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return dict(actual_git_head=head, working_tree_dirty=dirty, git_diff_sha256=diff_sha256,
                git_diff_command=" ".join(DIFF_COMMAND), git_diff_patch=patch_name,
                git_diff_scope=dict(base="HEAD", included="All tracked staged and unstaged changes",
                                    excluded_paths=[], untracked_included=False),
                source_snapshot_sha256=digest,
                source_files=files, python_version=sys.version,
                scope="Actual runner checkout at startup; null Git fields mean unavailable. "
                      "Git diff excludes untracked files; source_files also hashes untracked source files.")


def pytest_configure(config):
    config.addinivalue_line("markers", "gui: requires an operator-approved visible GUI window")
    config.addinivalue_line("markers", "remote: requires an operator-confirmed UU disconnection window")
    config._native_rows = {}
    config._native_root = None
    config._native_identity = None
    if config.getoption("--run-native"):
        output = config.getoption("--native-output")
        if not output:
            raise pytest.UsageError("--run-native requires a fresh --native-output directory")
        root = Path(output).resolve()
        if root.is_relative_to(ROOT):
            raise pytest.UsageError("Native evidence must be outside the repository")
        if not math.isfinite(config.getoption("--native-timeout")) or config.getoption("--native-timeout") <= 0:
            raise pytest.UsageError("Native timeout must be positive")
        if not math.isfinite(config.getoption("--remote-timeout")) or config.getoption("--remote-timeout") <= 0:
            raise pytest.UsageError("Remote timeout must be positive")
        root.mkdir(parents=True, exist_ok=False)
        config._native_root = root
        config._native_identity = execution_identity(report_directory=root)
        (root / "execution-context.json").write_text(
            json.dumps(config._native_identity, ensure_ascii=False, indent=2), encoding="utf8")
        if config.option.basetemp is None:
            config.option.basetemp = str(root / "pytest")


@pytest.fixture(scope="session")
def native_inputs(pytestconfig):
    path = pytestconfig.getoption("--native-inputs")
    data = json.loads(Path(path).read_text(encoding="utf8")) if path else {}
    if not isinstance(data, dict) or set(data) - {case.id for case in cases()}:
        raise pytest.UsageError("Native inputs must map known case IDs to argument objects")
    return data


@pytest.fixture
def acceptance_case(request, pytestconfig):
    case = request.param
    if not pytestconfig.getoption("--run-native"):
        pytest.skip("Native acceptance is opt-in via --run-native")
    unavailable = pytest.fail if pytestconfig.getoption("--native-strict") else pytest.skip
    if case.gui and not pytestconfig.getoption("--native-gui"):
        unavailable("Requires an operator-approved --native-gui window")
    native_inputs = request.getfixturevalue("native_inputs")
    # Acceptance scripts create their own UUID trees. Keep our prefix short so
    # atomic request files stay below the native Windows path limit.
    directory = pytestconfig._native_root / hashlib.sha256(case.id.encode()).hexdigest()[:8]
    schema = parser_schema(case.script)
    try:
        argv = arguments(case, schema, native_inputs.get(case.id, {}), directory,
                         pytestconfig.getoption("--native-executable"))
    except ValueError as exc:
        unavailable(str(exc))
    return case, argv, directory


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if item.get_closest_marker("native") is None:
        return
    rows = item.config._native_rows
    if report.when == "call" or report.failed or report.skipped:
        previous = rows.get(item.nodeid)
        if previous is None or previous["status"] != "failed":
            properties = dict(report.user_properties)
            evidence_only = properties.get("native_scope") == "evidence_only" and (report.passed or getattr(report, "wasxfail", None))
            status = "evidence_only" if evidence_only else report.outcome
            rows[item.nodeid] = dict(status=status, reason=str(report.longrepr) if report.failed or report.skipped else "",
                                    duration=report.duration, evidence=properties.get("native_evidence"),
                                    native_lane_statuses=properties.get("native_lane_statuses"))


def pytest_sessionfinish(session, exitstatus):
    root = session.config._native_root
    if root is None:
        return
    rows = session.config._native_rows
    for item in session.items:
        if item.get_closest_marker("native") is not None:
            rows.setdefault(item.nodeid, dict(status="not_run", reason="Interrupted before result", duration=0))
    identity = {key: value for key, value in session.config._native_identity.items() if key != "source_files"}
    (root / "report.json").write_text(json.dumps(dict(exit_status=int(exitstatus), execution_context=identity,
        cases=rows), ensure_ascii=False, indent=2), encoding="utf8")
    lines = ["# LS-PrePost native regression", "", "Existing acceptance assertions, fresh reports and exact script hashes; skipped cases are not passes.",
             "", "Actual Git revision: `{}`".format(identity["actual_git_head"] or "unavailable"),
             "", "Working tree dirty: `{}`".format(identity["working_tree_dirty"]),
             "", "Git diff SHA256 (`{}`): `{}`".format(identity["git_diff_command"], identity["git_diff_sha256"] or "unavailable"),
             "", "Diff scope: all tracked staged/unstaged changes against HEAD; no path exclusions; untracked files excluded.",
             "", "Raw patch: {}".format("[working-tree.patch](working-tree.patch)" if identity["git_diff_patch"] else "unavailable"),
             "", "Source snapshot SHA256: `{}`".format(identity["source_snapshot_sha256"]),
             "", "Identity captured at pytest startup; untracked source hashes are in [execution-context.json](execution-context.json).",
             "", "| Case | Result | Seconds | Execution / PNG / MP4 | Evidence | Detail |", "|---|---|---:|---|---|---|"]
    for name, row in sorted(rows.items()):
        detail = row["reason"].replace("|", "\\|").replace("\n", "<br>")
        evidence = "[verified.json](<{}>)".format(row["evidence"]) if row.get("evidence") else ""
        lanes = row.get("native_lane_statuses") or {}
        lane_text = " / ".join(lanes.get(key, "—") for key in ("execution", "png", "mp4"))
        lines.append("| {} | {} | {:.2f} | {} | {} | {} |".format(name, row["status"], row["duration"], lane_text, evidence, detail))
    (root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf8")
