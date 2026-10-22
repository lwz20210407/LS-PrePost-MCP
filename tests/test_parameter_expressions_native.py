"""P02 opt-in native oracle for fixed/free expressions with argument commas."""
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.service import Service
from tests.test_save_model import deck
from tests.test_save_model_native import installation as installation

pytestmark = pytest.mark.native


@pytest.mark.parametrize("free", [False, True], ids=["fixed", "free"])
def test_native_expression_coordinates_and_preserved_save(installation, pytestconfig, free):
    executable, binary, config_sha = installation
    root = pytestconfig._native_root / ("free" if free else "fixed")
    main = deck(root / "source")
    expression = b"Rmaxval,max(2, min(4, 8))\r\n" if free else b"Rmaxval   max(2, min(4, 8))\r\n"
    main.write_bytes(main.read_bytes().replace(b"*KEYWORD\r\n", b"*KEYWORD\r\n*PARAMETER_EXPRESSION\r\n" + expression))
    nodes = main.parent / "nodes.k"
    nodes.write_bytes(nodes.read_bytes().replace(b"1,0,0,0", b"1,&maxval,0,0"))
    original = {p.name: p.read_bytes() for p in main.parent.iterdir()}
    parsed = KeywordDeck.load(main)
    assert not parsed.warnings
    assert next(r.definition.value for r in parsed.parameters if r.definition.name == "maxval") == 4
    service = Service(Settings(root / "work", executable, (root,), timeout=180))
    saved = service.save_model(str(main))
    observations = []
    for path in (main, Path(saved["data"]["main"])) if saved["status"] == "succeeded" else ():
        result = service.list_nodes(str(path), limit=4)
        row = next(r for r in result.get("data", {}).get("rows", []) if r[0] == 1)
        observations.append({"job_id": result["job_id"], "status": result["status"], "node_1": row})
    job_ids = [r["job_id"] for r in saved.get("data", {}).get("observations", {}).values()]
    job_ids += [r["job_id"] for r in observations]
    jobs = []
    for job_id in job_ids:
        job = service.jobs.get(job_id)
        process = job["process"]
        jobs.append({"job_id": job_id, "status": job["status"], "returncode": process["returncode"],
                     "timed_out": process["timed_out"], "graphics": process["graphics"],
                     "nographics": "-nographics" in process["argv"]})
    identity = pytestconfig._native_identity
    proof = {k: identity[k] for k in ("working_tree_dirty", "git_diff_sha256", "git_diff_scope")}
    proof.update(case="free" if free else "fixed", actual_git_revision=identity["actual_git_head"],
                 executable=binary, source_config_sha256=config_sha, status=saved["status"],
                 warnings=saved["warnings"], source_unchanged=original == {p.name: p.read_bytes() for p in main.parent.iterdir()},
                 observations=observations, native_jobs=jobs)
    (root / "verified.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf8")
    assert saved["status"] == "succeeded", saved.get("error")
    assert proof["source_unchanged"] and not saved["warnings"] and len(observations) == 2
    assert all(o["status"] == "succeeded" and o["node_1"] == [1, 4.0, 0.0, 0.0] for o in observations)
    assert len(jobs) == 4 and all(j["returncode"] == 0 and not j["timed_out"] and j["nographics"]
                                and j["graphics"] is False for j in jobs)
