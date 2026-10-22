"""P11 opt-in serial headless copy/reopen of standalone, Include and edited decks."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.domain.model import preflight_includes
from ls_prepost_mcp.engine.environment import locate_config
from ls_prepost_mcp.native.versions import profile
from ls_prepost_mcp.service import Service
from tests.test_save_model import deck
from tools.fetch_corpus import entries, load_registry, plain_path, resolve

pytestmark = pytest.mark.native


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@pytest.fixture(scope="module")
def installation(pytestconfig):
    if not pytestconfig.getoption("--run-native"):
        pytest.skip("P11 native save requires explicit --run-native")
    unavailable = pytest.fail if pytestconfig.getoption("--native-strict") else pytest.skip
    executable = pytestconfig.getoption("--native-executable")
    if not executable:
        unavailable("Set --native-executable for P11 headless save/reopen")
    pytest.importorskip("ansys.dyna.core")
    executable = Path(executable)
    config = locate_config(executable, os.environ)
    if config is None:
        unavailable("An initialized LS-PrePost configuration is required")
    identity = pytestconfig._native_identity
    assert identity["actual_git_head"] and identity["working_tree_dirty"] is False
    binary_sha, config_sha = sha(executable), sha(config)
    yield executable, {"name": executable.name, "version": profile(executable)["version"],
                       "sha256": binary_sha}, config_sha
    assert sha(executable) == binary_sha and sha(config) == config_sha


@pytest.mark.parametrize("case", ["standalone", "empty", "include", "edited", "public-include", "public-edited", "mismatch"])
def test_native_save_and_reopen(installation, pytestconfig, record_property, case):
    executable, binary, config_sha = installation
    root = pytestconfig._native_root / case
    root.mkdir(parents=True, exist_ok=True)
    allowed = [root]
    corpus_id = None
    if case.startswith("public-"):
        location = os.environ.get("LSPP_CORPUS_DIR")
        if not location:
            pytest.skip("Set LSPP_CORPUS_DIR for registered include_contact")
        corpus_id = "include_contact"
        corpus_root = Path(location)
        allowed.append(corpus_root)
        main = plain_path(resolve(entries(load_registry())[corpus_id], corpus_root))
    else:
        main = deck(root / "source")
        if case in ("standalone", "empty"):
            main.write_bytes(b"*KEYWORD\n" + (main.parent / "nodes.k").read_bytes()
                             + (main.parent / "mesh.k").read_bytes()
                             + (b"*INCLUDE\n$ disabled alternative\n" if case == "empty" else b"") + b"*END\n")
    service = Service(Settings(root / "work", executable, tuple(allowed), timeout=180))
    original = main
    original_hash = sha(main)
    original_tree = preflight_includes(main)
    source_hashes = {f["path"]: sha(f["path"]) for f in original_tree["files"]}
    modified_files = None
    if case in ("edited", "public-edited"):
        edit = ({"op": "set", "keyword": "*CONTROL_TERMINATION", "field": "endtim", "value": 6.0}
                if case == "public-edited" else {"op": "set", "keyword": "*MAT_ELASTIC", "field": "e", "value": 200.0})
        edited = JobResult.model_validate(service.edit_keywords(str(main), [edit]))
        assert edited.status == "succeeded", edited.error
        main = Path(edited.data["main"])
        modified_files = [Path(a.path).name for a in edited.artifacts if a.metadata["modified"]]
        assert len(modified_files) == 1
        if case == "edited":
            assert "200" in (main.parent / "mesh.k").read_text()
    result = JobResult.model_validate(service.save_model(str(main), **(
        {"expected_counts": {"nodes": 5, "elements": 1}} if case == "mismatch" else {})))
    jobs = []
    for phase, item in result.data.get("observations", {}).items():
        job = service.jobs.get(item["job_id"])
        process = job.get("process", {})
        jobs.append({"phase": phase, "job_id": item["job_id"], "status": job["status"],
                     "returncode": process.get("returncode"), "timed_out": process.get("timed_out"),
                     "graphics": process.get("graphics"), "nographics": "-nographics" in process.get("argv", [])})
    identity = pytestconfig._native_identity
    proof = {"case": case, "corpus_id": corpus_id, "actual_git_revision": identity["actual_git_head"],
             "working_tree_dirty": identity["working_tree_dirty"], "git_diff_sha256": identity["git_diff_sha256"],
             "git_diff_scope": identity["git_diff_scope"], "executable": binary, "source_config_sha256": config_sha,
             "status": result.status, "error": result.error, "expected": result.data.get("expected"),
             "differences": result.data["differences"], "observations": result.data.get("observations"),
             "saved_files": result.data.get("saved_files"), "native_jobs": jobs,
             "original_main_unchanged": sha(original) == original_hash,
             "original_tree_unchanged": source_hashes == {p: sha(p) for p in source_hashes},
             "modified_files_before_save": modified_files,
             "source_tree_sha256": original_tree["tree_sha256"],
             "artifact_sha256": [a.sha256 for a in result.artifacts]}
    proof["expected_result"] = "failed" if case == "mismatch" else "succeeded"
    output = root / "verified.json"
    output.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    record_property("evidence", str(output))
    if case == "mismatch":
        assert result.status == "failed" and result.data["differences"] and not result.artifacts
        assert len(jobs) == 1 and jobs[0]["status"] == "succeeded" and proof["original_tree_unchanged"]
        return
    assert result.status == "succeeded", result.error
    assert result.check_status == "passed" and proof["original_main_unchanged"] and proof["original_tree_unchanged"]
    assert len(jobs) == 2
    assert all(j["status"] == "succeeded" and j["returncode"] == 0 and j["timed_out"] is False
               and j["graphics"] is False and j["nographics"] for j in jobs)
    assert result.data["observations"]["before_save"]["counts"] == result.data["observations"]["after_reopen"]["counts"]
    assert all(sha(a.path) == a.sha256 for a in result.artifacts)
