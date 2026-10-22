"""P11 opt-in native save/reopen of unchanged and edited search-path trees."""
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.domain.model import preflight_includes
from ls_prepost_mcp.service import Service
from tests.test_keyword_native_snapshot_native import sha, source_tree
from tests.test_save_model_native import installation as installation

pytestmark = pytest.mark.native


@pytest.mark.parametrize("case", ["search", "relative-search", "unused-search", "edited-search"])
def test_search_path_preserved_save(installation, pytestconfig, record_property, case):
    executable, binary, config_sha = installation
    root = pytestconfig._native_root / case
    main = source_tree(root, "relative-search" if case == "relative-search" else "search")
    if case == "unused-search":
        (main.parent.parent / "empty-directory").mkdir()
        main.write_text(main.read_text().replace("\nassets\n", "\nassets\n../empty-directory\n"))
    original = preflight_includes(main)
    before = {row["path"]: sha(row["path"]) for row in original["files"]}
    service = Service(Settings(root / "work", executable, (root,), timeout=180))
    if case == "edited-search":
        edited = JobResult.model_validate(service.edit_keywords(str(main), [
            {"op": "set", "keyword": "*MAT_ELASTIC", "field": "e", "value": 200.0}]))
        assert edited.status == "succeeded", edited.error
        main = Path(edited.data["main"])
        assert len([a for a in edited.artifacts if a.metadata["modified"]]) == 1
    result = JobResult.model_validate(service.save_model(str(main)))
    identity = pytestconfig._native_identity
    jobs = []
    for observation in result.data.get("observations", {}).values():
        native = service.jobs.get(observation["job_id"])
        process = native["process"]
        jobs.append({"job_id": observation["job_id"], "status": native["status"],
                     "returncode": process["returncode"], "graphics": process["graphics"],
                     "timed_out": process["timed_out"], "nographics": "-nographics" in process["argv"]})
    saved = preflight_includes(result.data["main"]) if result.status == "succeeded" else None
    proof = {"case": case, "actual_git_revision": identity["actual_git_head"],
        "working_tree_dirty": identity["working_tree_dirty"], "git_diff_sha256": identity["git_diff_sha256"],
        "git_diff_scope": identity["git_diff_scope"], "executable": binary, "source_config_sha256": config_sha,
        "status": result.status, "error": result.error, "original_tree_sha256": original["tree_sha256"],
        "source_unchanged": before == {p: sha(p) for p in before}, "native_jobs": jobs,
        "saved_tree_ok": saved["ok"] if saved else False,
        "saved_missing_directories": [p["kind"] for p in saved["problems"] if p["kind"] == "missing_search_dir"] if saved else [],
        "expected_counts": result.data.get("expected", {}).get("counts"), "differences": result.data["differences"]}
    output = root / "verified.json"
    output.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    record_property("evidence", str(output))
    assert result.status == "succeeded", result.error
    assert proof["source_unchanged"] and proof["saved_tree_ok"] and not proof["saved_missing_directories"]
    assert proof["expected_counts"] == {"nodes": 4, "elements": 1} and not proof["differences"]
    assert len(jobs) == 2 and all(j["status"] == "succeeded" and j["returncode"] == 0
        and j["graphics"] is False and j["timed_out"] is False and j["nographics"] for j in jobs)
