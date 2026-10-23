"""Q03 serial headless native/LASSO tensor agreement; corpus stays external."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from tests.test_field_metrics import write_synthetic
from tests.test_save_model_native import installation as installation
from tools.fetch_corpus import entries, load_registry, plain_path, resolve
from tools.public_corpus_preflight import directory_snapshot, input_tree

pytestmark = pytest.mark.native

CASES = [("synthetic-solid", "solid", None, None, "mid"),
         ("synthetic-shell", "shell", None, None, "mid"),
         ("public-solid", "solid", [1], None, "mid"),
         ("public-shell-mid", "shell", [3000], 3, "mid"),
         ("public-shell-inner", "shell", [3000], 1, "inner"),
         ("public-shell-outer", "shell", [3000], 5, "outer")]


@pytest.mark.parametrize("case,family,parts,point,sampling", CASES, ids=[c[0] for c in CASES])
def test_native_tensor_agreement(installation, pytestconfig, case, family, parts, point, sampling):
    executable, binary, config_sha = installation
    root = pytestconfig._native_root / case
    root.mkdir()
    allowed = [root]
    if case.startswith("public-"):
        location = os.environ.get("LSPP_CORPUS_DIR")
        if not location:
            pytest.skip("Set LSPP_CORPUS_DIR for public solid/shell cross-check")
        corpus = plain_path(Path(location))
        source = plain_path(resolve(entries(load_registry())["solid_d3plot" if family == "solid" else "shell_d3plot"], corpus))
        allowed.append(corpus / "public-results")
    else:
        folder = root / "source"
        folder.mkdir()
        source = write_synthetic(folder / "d3plot")
    service = Service(Settings(root / "jobs", executable, tuple(allowed), timeout=180))
    paths = service._result_family(str(source))
    tree, identities = input_tree(source, paths, keyword=False)
    listing = directory_snapshot(paths)
    result = service.extract_field(str(source), family, "stress", state="last", mask="all", units="source_native_units",
                                   part_ids=parts, output_format="both", stored_point=point,
                                   native_check=True, native_sampling=sampling)
    identity = pytestconfig._native_identity
    proof = {k: identity[k] for k in ("working_tree_dirty", "git_diff_sha256", "git_diff_scope")}
    proof.update(case=case, actual_git_revision=identity["actual_git_head"], executable=binary,
                 source_config_sha256=config_sha, status=result["status"], error=result.get("error"),
                 family=family, sampling=result["data"].get("sampling"),
                 shape=result["data"].get("shape"), state=result["data"].get("state"), time=result["data"].get("time"),
                 comparison=result["data"].get("native_comparison"),
                 source_unchanged=all(hashlib.sha256(p.read_bytes()).hexdigest()==v for p,v in identities.items()),
                 directory_unchanged=directory_snapshot(paths)==listing, source_tree_sha256=tree["tree_sha256"],
                 artifact_sha256=[a["sha256"] for a in result["artifacts"]])
    native_jobs=[]
    for directory in service.jobs.root.iterdir():
        manifest=directory / "job.json"
        if manifest.is_file():
            job=json.loads(manifest.read_text(encoding="utf8"))
            if job.get("action") == "extract_native_fields":
                process=job.get("process", {})
                native_jobs.append({"status":job["status"],"returncode":process.get("returncode"),
                                    "nographics":"-nographics" in process.get("argv", []),
                                    "graphics":process.get("graphics"),"timed_out":process.get("timed_out")})
    proof["native_jobs"]=native_jobs
    (root / "verified.json").write_text(json.dumps(proof, indent=2)+"\n", encoding="utf8")
    assert result["status"] == "succeeded", result.get("error")
    assert proof["source_unchanged"] and proof["directory_unchanged"]
    assert len(result["artifacts"]) == 2 and proof["comparison"]["entities"] == proof["shape"][0]
    assert len(native_jobs) == 1 and native_jobs[0]["returncode"] == 0 and native_jobs[0]["nographics"]
