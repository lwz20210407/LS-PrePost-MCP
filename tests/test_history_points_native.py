"""Q05 explicit reader slots and independently chosen native layers, all saved states."""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.results import lasso_backend as lb
from ls_prepost_mcp.service import Service
from tests.test_save_model_native import installation as installation
from tools.fetch_corpus import entries, load_registry, plain_path, resolve
from tools.public_corpus_preflight import directory_snapshot, input_tree

pytestmark = pytest.mark.native


@pytest.mark.parametrize("point,layer,expected", [(1, "mid", "succeeded"), (2, "inner", "succeeded"),
                                               (5, "outer", "succeeded"), (3, "mid", "failed")])
def test_shell_history_slots_match_explicit_native_layers(installation, pytestconfig, point, layer, expected):
    executable, binary, config_sha = installation
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        pytest.skip("Set LSPP_CORPUS_DIR for the registered shell result")
    corpus = plain_path(Path(location))
    source = plain_path(resolve(entries(load_registry())["shell_d3plot"], corpus))
    root = pytestconfig._native_root / f"shell-point-{point}-{layer}"
    root.mkdir()
    service = Service(Settings(root / "work", executable, (root, corpus / "public-results"), timeout=240))
    family = service._result_family(str(source))
    tree, identities = input_tree(source, family, keyword=False)
    listing = directory_snapshot(family)
    arrays = lb._arrays(source, state_arrays=["timesteps", "element_shell_stress"])
    stress = np.asarray(arrays["element_shell_stress"])
    difference = np.max(np.abs(stress[:, :, 0, 0] - stress[:, :, 2, 0]), axis=0)
    chosen = np.argsort(difference)[-2:]
    assert len(chosen) == 2 and min(difference[chosen]) > 0, "Need two nondegenerate bending/layer curves"
    ids = [int(arrays["element_shell_ids"][i]) for i in chosen]
    result = service.extract_history(str(source), "shell", "sxx", ids, units="source_native_stress",
        time_units="source_native_time", stored_point=point, native_sampling=layer, native_check=True)
    context = pytestconfig._native_identity
    jobs = []
    for file in service.jobs.root.glob("*/job.json"):
        job = json.loads(file.read_text(encoding="utf8"))
        if job["action"] == "extract_native_fields":
            process = job["process"]
            jobs.append({key: process.get(key) for key in ("returncode", "timed_out", "graphics")}
                        | {"nographics": "-nographics" in process.get("argv", [])})
    proof = dict(actual_git_revision=context["actual_git_head"], working_tree_dirty=context["working_tree_dirty"],
        git_diff_sha256=context["git_diff_sha256"], git_diff_scope=context["git_diff_scope"],
        case=f"shell-point-{point}-{layer}", corpus_id="shell_d3plot", executable=binary, source_config_sha256=config_sha,
        expected_status=expected, status=result["status"], error=result.get("error"), stored_point=point,
        native_sampling=layer, entity_ids=ids, layer_discrimination_nonzero=True,
        sampling=[c.get("sampling_spec") for c in result["data"].get("curves", [])],
        comparison=result["data"].get("native_comparison"), total_samples=result["data"].get("total_samples"),
        native_jobs=jobs, source_tree_sha256=tree["tree_sha256"],
        source_unchanged=all(hashlib.sha256(p.read_bytes()).hexdigest() == sha for p, sha in identities.items()),
        directory_unchanged=directory_snapshot(family) == listing,
        artifact_sha256=[a["sha256"] for a in result["artifacts"]])
    (root / "verified.json").write_text(json.dumps(proof, separators=(",", ":"))+"\n", encoding="utf8")
    assert result["status"] == expected, result.get("error")
    assert proof["source_unchanged"] and proof["directory_unchanged"]
    assert len(jobs) == 1 and jobs[0] == dict(returncode=0, timed_out=False, graphics=False, nographics=True)
    if expected == "failed":
        assert "disagreement" in result["error"]["message"] and not result["artifacts"]
    else:
        assert all(s["index"] == point and s["native_layer_equivalence"] == "not inferred" for s in proof["sampling"])
        assert result["data"]["native_comparison"]["native_sampling"] == layer
