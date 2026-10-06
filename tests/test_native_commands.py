"""I03 grammar goldens, rejection cases and embedded bundle compatibility."""

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from ls_prepost_mcp.native import commands as nc
from ls_prepost_mcp.native import versions as nv
from ls_prepost_mcp.native.bundle import stage_bridge


@pytest.mark.parametrize("builder,args,expected", [
    (nc.selection, ("clear",), "genselect clear"),
    (nc.selection, ("whole",), "genselect whole"),
    (nc.selection, ("adjacent",), "genselect adjacent"),
    (nc.selection, ("reverse",), "genselect reverse"),
    (nc.selection_target, ("node",), "genselect target node"),
    (nc.selection_target, ("element",), "genselect target element"),
    (nc.selection_add, ("node", 91), "genselect node add node 91"),
    (nc.selection_add, ("shell", 305), "genselect shell add shell 305"),
    (nc.selection_add, ("shell", 7, "part"), "genselect shell add part 7"),
    (nc.selection_buffer, ("save", 0), "genselect save 0"),
    (nc.selection_buffer, ("load", 2), "genselect load 2"),
    (nc.selection_transfer, (0,), "genselect transfer 0"),
    (nc.selection_propagation, (True,), "genselect propagate on"),
    (nc.selection_propagation, (False, True), "genselect propagate adaptive off"),
    (nc.selection_surface, (False,), "genselect 3dsurf off"),
    (nc.feature_angle, (45.0,), "genselect propagate featang 45.0"),
    (nc.animation, ("stop",), "anim stop"),
    (nc.animation, ("first", 1), "anim first 1"),
    (nc.animation, ("last", 3), "anim last 3"),
    (nc.animation, ("incr", 2), "anim incr 2"),
    (nc.animation, ("forward",), "anim forward"),
    (nc.animation, ("backward",), "anim backward"),
    (nc.animation, ("cycle",), "anim cycle"),
    (nc.animation, ("start",), "anim start"),
    (nc.state, (3,), "state 3"),
    (nc.fringe, (9,), "fringe 9"),
    (nc.plot_fringe, (), "pfringe"),
    (nc.averaging, ("minmax",), "range avgfrng minmax"),
    (nc.averaging, ("nodal",), "range avgfrng nodal"),
    (nc.averaging, ("none",), "range avgfrng none"),
    (nc.reverse_signs, (False,), "range reversesigns off"),
    (nc.fringe_bounds, (-1.25, 2.5), "range userdef -1.25 2.5;"),
])
def test_native_command_goldens(builder, args, expected):
    assert builder(*args) == expected


@pytest.mark.parametrize("builder,args", [
    (nc.selection_target, ("node\nexit",)),
    (nc.selection_target, ("node/0",)),
    (nc.selection_add, ("node", True)),
    (nc.selection_add, ("node", "11")),
    (nc.selection_add, ("node", 0)),
    (nc.selection_add, ("node", 11, "shell")),
    (nc.selection_buffer, ("load", -1)),
    (nc.selection_buffer, ("load", 10)),
    (nc.selection_buffer, ("save", True)),
    (nc.selection_propagation, ("off",)),
    (nc.feature_angle, (float("nan"),)),
    (nc.feature_angle, (181,)),
    (nc.animation, ("last", 0)),
    (nc.animation, ("stop", 1)),
    (nc.animation, ("forward\nexit",)),
    (nc.state, (False,)),
    (nc.fringe, (1.0,)),
    (nc.averaging, ("minmax;exit",)),
    (nc.fringe_bounds, (0, float("inf"))),
    (nc.fringe_bounds, (2, 1)),
])
def test_command_rejects_ambiguous_or_injectable_arguments(builder, args):
    with pytest.raises(ValueError):
        builder(*args)


def test_command_grammar_is_not_reintroduced_in_domain_modules():
    root = Path(nc.__file__).parents[1]
    pattern = re.compile(r"(?:^|\n)(?:genselect |anim |fringe (?:$|\d)|pfringe$|range (?:avgfrng|reversesigns|userdef) |open(?:c)? (?:keyword|d3plot|command|xydata) |print png |movie MP4/H264 |runpython |runscript |save keyword |import keyword |(?:xyplot (?:\d+|\{[^}]*\}) )?savefile xypair |modelcheck writetofile )")
    offenders = []
    for source in root.rglob("*.py"):
        if source == Path(nc.__file__) or source.name == "recording_compiler.py":
            continue  # The recorder parses grammar, it does not generate commands.
        tree = ast.parse(source.read_text(encoding="utf8"))
        parser_tokens = {id(arg) for call in ast.walk(tree) if isinstance(call, ast.Call)
                         and isinstance(call.func, ast.Attribute) and call.func.attr in ("startswith", "endswith")
                         for arg in call.args}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and pattern.search(node.value):
                if id(node) not in parser_tokens:
                    offenders.append((source.name, node.lineno))
    assert offenders == []


@pytest.mark.parametrize("path", ["job with spaces/model.k", "目录/模型.k", r"C:\目录 空格\模型.k"])
def test_path_builders_have_one_quoted_grammar(path, tmp_path):
    quoted = '"' + path.replace("\\", "/") + '"'
    assert nc.quoted_path(path) == quoted
    assert nc.quoted_path(path, "native") == '"' + path + '"'
    assert nc.open_model(path) == "open keyword " + quoted
    assert nc.open_model(path, "d3plot", openc=True) == "openc d3plot " + quoted
    assert nc.save_keyword(path) == "save keyword " + quoted
    assert nc.import_keyword(path) == "import keyword " + quoted
    assert nc.open_xydata(path) == "open xydata " + quoted
    assert nc.save_xypair(path, 3) == "xyplot 3 savefile xypair " + quoted + " 1 all"
    assert nc.modelcheck_report(path) == "modelcheck writetofile " + quoted
    assert nc.print_png(path) == "print png " + quoted + ' opaque enlisted "OGL1x1"'
    assert nc.movie(path, 640, 480, 5) == 'movie MP4/H264 640x480 "' + path + '" 5'
    assert nc.run_script(path, "scl") == 'runscript "' + path + '"'
    assert nc.run_script(path, "python") == "runpython " + quoted
    assert nc.run_script(path, "cfile") == "openc command " + quoted + " nodialog"
    target = tmp_path / "commands.cfile"
    nc.write_cfile(target, [nc.open_model(path), "exit"])
    assert target.read_bytes() == (nc.open_model(path)+"\nexit\n").encode("utf8")


@pytest.mark.parametrize("path", ['semi;colon.k', 'a"quote.k', "a\nexit", "a\rname", "a\x00name", "a\tname"])
def test_every_path_builder_rejects_ambiguous_characters(path):
    calls = [lambda: nc.quoted_path(path), lambda: nc.open_model(path), lambda: nc.save_keyword(path),
             lambda: nc.print_png(path), lambda: nc.movie(path,640,480,5),
             lambda: nc.run_script(path,"scl"), lambda: nc.run_script(path,"python"), lambda: nc.run_script(path,"cfile"),
             lambda: nc.import_keyword(path), lambda: nc.open_xydata(path), lambda: nc.save_xypair(path),
             lambda: nc.modelcheck_report(path)]
    for call in calls:
        with pytest.raises(ValueError):
            call()


def test_generated_cfile_writes_use_the_shared_encoding_writer():
    root = Path(nc.__file__).parents[1]
    offenders = []
    for source in root.rglob("*.py"):
        if source == Path(nc.__file__):
            continue
        for call in ast.walk(ast.parse(source.read_text(encoding="utf8"))):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute) or call.func.attr != "write_text":
                continue
            destination = ast.unparse(call.func.value)
            if ".cfile" in destination or destination in {"cfile", "command_file", "close_script", "commands"}:
                offenders.append((source.name, call.lineno))
    assert not offenders


def test_generated_scl_writers_use_shared_encoding():
    root = Path(nc.__file__).parents[1]
    offenders = []
    for source in root.rglob("*.py"):
        if source == Path(nc.__file__):
            continue
        tree = ast.parse(source.read_text(encoding="utf8"))
        for scope in ast.walk(tree):
            if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            scl_names = {target.id for node in ast.walk(scope) if isinstance(node, ast.Assign)
                         and any(isinstance(v, ast.Constant) and isinstance(v.value, str)
                                 and v.value.endswith(".scl") for v in ast.walk(node.value))
                         for target in node.targets if isinstance(target, ast.Name)}
            for node in ast.walk(scope):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "write_text":
                    value = node.func.value
                    if (isinstance(value, ast.Name) and value.id in scl_names or
                            any(isinstance(v, ast.Constant) and isinstance(v.value, str)
                                and v.value.endswith(".scl") for v in ast.walk(value))):
                        offenders.append((source.name, node.lineno))
    assert not offenders


@pytest.mark.parametrize("identifier", [True, False, 0, -1, "1", 1.5])
def test_xypair_plot_window_is_a_positive_integer(identifier):
    with pytest.raises(ValueError):
        nc.save_xypair("curve.xy", identifier)


def test_scl_writer_uses_bom_free_utf8_and_lf(tmp_path):
    path = tmp_path / "生成 脚本.scl"
    nc.write_scl(path, "/* 中文注释 */\r\ndefine:\rmain();\n")
    assert path.read_bytes() == "/* 中文注释 */\ndefine:\nmain();\n".encode("utf8")


def test_prepared_scl_uses_shared_writer_and_matching_identity(tmp_path):
    import hashlib

    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.service import Service

    service = Service(Settings(tmp_path))
    result = service.prepare_native_program("scl", code="/* 中文 */\r\nmain();\r\n")
    path = Path(result["job_directory"]) / "program.scl"
    assert path.read_bytes() == "/* 中文 */\nmain();\n".encode("utf8")
    assert result["data"]["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_staged_bridge_loads_without_the_host_package(tmp_path):
    bridge = stage_bridge(tmp_path)
    for filename in ("bridge.py", "native_commands.py", "native_versions.py"):
        ast.parse((tmp_path / filename).read_text(encoding="utf8"), feature_version=(3, 6))
    program = "import json,runpy; b=runpy.run_path({!r}); print(json.dumps([b['nc'].selection_add('node',91),b['nv'].profile(version='4.10')['policy']]))".format(str(bridge))
    result = subprocess.run([sys.executable, "-I", "-B", "-c", program], cwd=tmp_path,
                            capture_output=True, text=True, check=True, timeout=15)
    assert json.loads(result.stdout) == ["genselect node add node 91", "regression_subset"]


def test_runtime_version_comparisons_stay_in_capability_table():
    offenders = []
    for source in Path(nc.__file__).parents[1].rglob("*.py"):
        if source == Path(nv.__file__):
            continue
        for node in ast.walk(ast.parse(source.read_text(encoding="utf8"))):
            if isinstance(node, ast.Compare):
                expression = ast.unparse(node)
                if any(token in expression for token in ("version_info", "version('lasso-python')", "client_version")):
                    offenders.append((source.name, node.lineno))
    assert offenders == []


@pytest.mark.parametrize("path,expected", [
    ("/installed/lsprepost4.13.exe", "4.13"),
    ("/Ansys/LS-PrePost-2026R1[4.13]/lsprepost.exe", "4.13"),
    (r"C:\LSTC\LS-PrePost 4.10\lsprepost4.10_x64.exe", "4.10"),
    ("/lspp", None),
])
def test_installation_hint_is_explicitly_not_runtime_verification(path, expected):
    assert nv.installation_version(path) == expected
    assert nv.profile(path)["runtime_verified"] is False


def test_version_policy_blocks_excluded_and_unverified_queue_profiles_before_launch(tmp_path, monkeypatch):
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.sessions import Sessions

    for label in ("4.11", "4.11.1"):
        with pytest.raises(ValueError, match="excluded"):
            nv.require_installation(version=label)
    exe = tmp_path / "lsprepost4.10.exe"
    exe.touch()
    monkeypatch.setattr("ls_prepost_mcp.sessions.subprocess.Popen", lambda *a, **kw: pytest.fail("Must not launch"))
    with pytest.raises(ValueError, match="KI-048"):
        Sessions(Settings(tmp_path, exe)).start(transport="queue")
    assert not (tmp_path / "sessions").exists()
    assert nv.require_capability(exe, "batch")["policy"] == "regression_subset"
    assert nv.require_installation(version="4.8")["policy"] == "best_effort"
    assert nv.require_capability("lsprepost4.13.exe", "queue_model_identity")


def test_vector_abi_and_reader_dependencies_keep_existing_fail_closed_policy():
    with pytest.raises(RuntimeError, match="cross-checks"):
        nv.require_vector_abi((3, 9))
    nv.require_vector_abi((3, 10))
    assert nv.dependency_supported("lasso-python", "2.0.4")
    assert not nv.dependency_supported("lasso-python", "2.1.0")
    assert nv.dependency_supported("ansys-dpf-core", "0.16.1")
