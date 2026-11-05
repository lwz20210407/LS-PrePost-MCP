"""P1-5: independent R11 solver geometry, not an LS-PrePost parameter echo."""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from ls_prepost_mcp.engine.processes import OwnedProcess

pytestmark = pytest.mark.native


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@pytest.fixture(scope="module")
def solver(pytestconfig):
    if not pytestconfig.getoption("--run-native"):
        pytest.skip("Solver evidence requires explicit --run-native")
    executable = os.environ.get("LSPP_SOLVER_EXECUTABLE")
    if not executable:
        pytest.skip("Set LSPP_SOLVER_EXECUTABLE to the licensed R11 SMP double executable")
    pytest.importorskip("lasso.dyna")
    binary = Path(executable)
    assert binary.is_file()
    identity = pytestconfig._native_identity
    assert identity["actual_git_head"] and not identity["working_tree_dirty"]
    original = sha(binary)
    yield binary, original
    assert sha(binary) == original


@pytest.mark.parametrize("free", [False, True], ids=["fixed", "free"])
def test_solver_reads_function_commas_as_expression_content(solver, pytestconfig, free):
    from lasso.dyna import ArrayType

    from ls_prepost_mcp.domain.results import lasso_backend as lb

    binary, binary_sha = solver
    root = pytestconfig._native_root / ("free" if free else "fixed")
    source_dir = root / "input"
    source_dir.mkdir(parents=True)
    main = source_dir / "main.k"
    name = "Rmaxval," if free else "Rmaxval   "
    main.write_text("*KEYWORD\n*PARAMETER_EXPRESSION\n" + name + "max(2, min(4, 8))\n"
        "*CONTROL_TERMINATION\n0.001\n*DATABASE_BINARY_D3PLOT\n0.001\n"
        "*NODE\n1,&maxval,0,0\n2,5,0,0\n3,5,1,0\n4,&maxval,1,0\n"
        "*ELEMENT_SHELL\n1,1,1,2,3,4\n*PART\nshell\n1,1,1\n"
        "*SECTION_SHELL\n1,2\n0.1,0.1,0.1,0.1\n*MAT_ELASTIC\n1,1,100,0.3\n*END\n",
        encoding="ascii", newline="\n")
    before = sha(main)
    env = dict(os.environ, LSTC_LICENSE="ANSYS", OMP_NUM_THREADS="1")
    timeout = False
    with OwnedProcess([str(binary), "i=input/main.k", "ncpu=1", "memory=20m"], cwd=root, env=env,
                      stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        try:
            stdout, stderr = process.process.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            timeout = True
            process.stop()
            stdout, stderr = process.process.communicate(timeout=15)
        returncode = process.process.returncode
    (root / "solver-stdout.log.raw").write_bytes(stdout)
    (root / "solver-stderr.log.raw").write_bytes(stderr)
    text = (stdout + stderr).decode("utf-8", errors="replace")
    for path in [root / "d3hsp", root / "messag", root / "mes0000"]:
        if path.is_file():
            text += path.read_text(encoding="utf-8", errors="replace")
    proof = {"case": "free" if free else "fixed", "actual_git_revision": pytestconfig._native_identity["actual_git_head"],
        "working_tree_dirty": pytestconfig._native_identity["working_tree_dirty"],
        "git_diff_sha256": pytestconfig._native_identity["git_diff_sha256"],
        "solver": {"name": binary.name, "sha256": binary_sha}, "license_mode": "ANSYS", "ncpu": 1,
        "memory": "20m", "returncode": returncode, "timed_out": timeout,
        "normal_termination": bool(re.search(r"(?<![A-Za-z])n\s*o\s*r\s*m\s*a\s*l\s+t\s*e\s*r\s*m\s*i\s*n\s*a\s*t\s*i\s*o\s*n(?![A-Za-z])", text, re.I)),
        "source_sha256": before,
        "source_unchanged": sha(main) == before and sorted(p.name for p in source_dir.iterdir()) == ["main.k"]}
    if not timeout and returncode == 0 and proof["normal_termination"] and (root / "d3plot").is_file():
        arrays = lb._arrays(root / "d3plot", state_arrays=[ArrayType.timesteps])
        proof["node_ids"] = arrays[ArrayType.node_ids].tolist()
        proof["node_coordinates"] = arrays[ArrayType.node_coordinates].tolist()
        proof["d3plot_sha256"] = sha(root / "d3plot")
    (root / "verified.json").write_text(json.dumps(proof, separators=(",", ":")) + "\n", encoding="utf-8")
    assert returncode == 0 and not timeout and proof["normal_termination"], "R11 did not terminate normally"
    assert proof["source_unchanged"]
    assert proof["node_ids"] == [1, 2, 3, 4]
    assert proof["node_coordinates"] == [[4., 0., 0.], [5., 0., 0.], [5., 1., 0.], [4., 1., 0.]]
