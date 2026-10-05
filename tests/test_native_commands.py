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
    pattern = re.compile(r"^(?:genselect |anim |fringe (?:$|\d)|pfringe$|range (?:avgfrng|reversesigns|userdef) )")
    offenders = []
    for source in root.rglob("*.py"):
        if source == Path(nc.__file__) or source.name == "recording_compiler.py":
            continue  # The recorder parses grammar, it does not generate commands.
        for node in ast.walk(ast.parse(source.read_text(encoding="utf8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and pattern.match(node.value):
                offenders.append((source.name, node.lineno))
    assert offenders == []


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
