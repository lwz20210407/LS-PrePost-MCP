"""I01 explicit opt-in real native reads of owned Include snapshots; no GUI."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model import preflight_includes
from ls_prepost_mcp.engine.environment import locate_config
from ls_prepost_mcp.native.versions import profile
from ls_prepost_mcp.service import Service

pytestmark = pytest.mark.native
NODES = b"*NODE\n1,0,0,0\n2,1,0,0\n3,1,1,0\n4,0,1,0\n"
MESH = (b"*ELEMENT_SHELL\n1,1,1,2,3,4\n*PART\nsnapshot plate\n1,1,1\n"
        b"*SECTION_SHELL\n1,2\n1,1,1,1\n*MAT_ELASTIC\n1,1,100,0.3\n")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@pytest.fixture(scope="module")
def installation(pytestconfig):
    if not pytestconfig.getoption("--run-native"):
        pytest.skip("Owned Include snapshots require explicit --run-native")
    executable = pytestconfig.getoption("--native-executable")
    unavailable = pytest.fail if pytestconfig.getoption("--native-strict") else pytest.skip
    if not executable:
        unavailable("Set --native-executable")
    executable = Path(executable)
    config = locate_config(executable, os.environ)
    if config is None:
        unavailable("An initialized lsppconf is required")
    assert pytestconfig._native_identity["working_tree_dirty"] is False
    binary_sha, config_sha = sha(executable), sha(config)
    yield executable, {"name": executable.name, "sha256": binary_sha, "version": profile(executable)["version"]}, config_sha
    assert sha(executable) == binary_sha and sha(config) == config_sha


def source_tree(root, case):
    source = root / ("输入 模型" if case.startswith("unicode") else "source")
    source.mkdir(parents=True)
    names = ("节点.k", "网格.k") if case.startswith("unicode") else ("nodes.k", "mesh.k")
    data = source / "assets" if case in ("search", "relative-search", "scl-search") else source
    data.mkdir(exist_ok=True)
    (data / names[0]).write_bytes(NODES)
    (data / names[1]).write_bytes(MESH)
    prefix = ("*INCLUDE_PATH_RELATIVE\nassets\n" if case == "relative-search" else
              "*INCLUDE_PATH\nassets\n" if case in ("search", "scl-search") else "")
    filename = "主 模型.k" if case.startswith("unicode") else "main.k"
    main = source / filename
    refs = [str(data / name) if case == "absolute" else name for name in names]
    text = "*KEYWORD\n" + prefix + "*INCLUDE\n" + "\n".join(refs) + "\n*END\n"
    main.write_bytes(text.encode("gbk" if case == "unicode-gbk" else "utf-8"))
    return main


@pytest.mark.parametrize("case", ["plain", "search", "relative-search", "unicode-utf8", "unicode-gbk",
                                  "absolute", "unicode-workspace", "scl-search"])
def test_real_native_snapshot(installation, pytestconfig, monkeypatch, record_property, case):
    executable, binary, config_sha = installation
    root = pytestconfig._native_root / case
    main = source_tree(root, case)
    report = preflight_includes(main)
    assert report["ok"] and len(report["files"]) == 3
    before = {f["path"]: sha(f["path"]) for f in report["files"]}
    listings = {str(Path(p).parent): sorted(x.name for x in Path(p).parent.iterdir()) for p in before}
    aliases = root / "aliases"
    aliases.mkdir()
    monkeypatch.setenv("LSPP_NATIVE_ALIAS_ROOT", str(aliases))
    workspace = root / ("中文 作业" if case == "unicode-workspace" else "work")
    service = Service(Settings(workspace, executable, (root,), timeout=120))
    result = (service._native("scl_probe", {}, str(main)) if case == "scl-search"
              else service.inspect_model(str(main)))
    process = result.get("process", {})
    tree = result.get("input_tree", {})
    identity = pytestconfig._native_identity
    value = (result.get("data") or {}).get("scl_nodes") if case == "scl-search" else (
        result.get("data") or {}).get("counts", {}).get("nodes")
    proof = {"case": case, "actual_git_revision": identity["actual_git_head"],
        "working_tree_dirty": identity["working_tree_dirty"], "git_diff_sha256": identity["git_diff_sha256"],
        "git_diff_scope": identity["git_diff_scope"], "executable": binary, "source_config_sha256": config_sha,
        "status": result["status"], "error": result.get("error"), "job_id": result["job_id"],
        "nodes": value, "elements": (result.get("data") or {}).get("counts", {}).get("elements"),
        "source_tree_sha256": report["tree_sha256"],
        "source_tree_sha256_version": report["tree_sha256_version"],
        "source_unchanged": before == {p: sha(p) for p in before},
        "directory_unchanged": all(v == sorted(x.name for x in Path(p).iterdir()) for p, v in listings.items()),
        "snapshot_mode": tree.get("mode"), "snapshot_files": len(tree.get("files", [])),
        "cleanup_removed": len(tree.get("cleanup", {}).get("removed", [])),
        "cleanup_retained": len(tree.get("cleanup", {}).get("retained", [])),
        "process": {k: process.get(k) for k in ("pid", "returncode", "timed_out", "graphics")},
        "nographics": "-nographics" in process.get("argv", []),
        "ascii_cwd": str(process.get("cwd", "")).isascii()}
    output = root / "verified.json"
    output.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    record_property("evidence", str(output))
    assert result["status"] == "succeeded", result.get("error")
    assert value == 4 and proof["source_unchanged"] and proof["directory_unchanged"]
    assert proof["snapshot_files"] == proof["cleanup_removed"] == 3 and proof["cleanup_retained"] == 0
    assert proof["nographics"] and proof["ascii_cwd"] and proof["process"]["graphics"] is False
    assert proof["process"]["returncode"] == 0 and proof["process"]["timed_out"] is False
    assert list(aliases.iterdir()) == []
