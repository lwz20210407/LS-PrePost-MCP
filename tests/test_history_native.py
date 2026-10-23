"""Q05 four real history modes; readers independently compared with headless native output."""

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
from tools.fetch_corpus import entries, load_registry, plain_path, read_catalogs, resolve
from tools.public_corpus_preflight import directory_snapshot, input_tree

pytestmark = pytest.mark.native


@pytest.mark.parametrize(
    "domain,quantity",
    [
        ("node", "displacement_z"),
        ("solid", "von_mises"),
        ("part", "kinetic_energy"),
        ("global", "kinetic_energy"),
    ],
)
def test_four_history_modes_match_real_native_curves(installation, pytestconfig, domain, quantity):
    executable, binary, config_sha = installation
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        pytest.skip("Set LSPP_CORPUS_DIR to the registered external public corpus")
    corpus = plain_path(Path(location))
    registry = entries(load_registry())
    root = pytestconfig._native_root / domain
    root.mkdir()
    if domain in ("node", "solid"):
        source = plain_path(resolve(registry["solid_d3plot"], corpus))
        arrays = lb._arrays(source, state_arrays=["timesteps", "node_displacement"] if domain == "node" else ["timesteps"])
        stored = arrays["node_ids" if domain == "node" else "element_solid_ids"]
        if domain == "node":
            motion = np.asarray(arrays["node_displacement"])[:, :, 2] - np.asarray(arrays["node_coordinates"])[None, :, 2]
            peaks = np.max(np.abs(motion), axis=0)
            ranked = np.argsort(peaks)[::-1]
            first = int(ranked[0])
            assert peaks[first] > 0, "The native ID oracle needs nonzero displacement"
            second = next((int(i) for i in ranked[1:] if peaks[i] > 0
                           and np.max(np.abs(motion[:, i] - motion[:, first])) > 1e-3 * peaks[first]), None)
            assert second is not None, "Need two distinguishable nonzero curves, not a degenerate ID oracle"
            ids = [int(stored[first]), int(stored[second])]
            node_oracle = {"peaks": [float(peaks[i]) for i in (first, second)],
                           "max_curve_separation": float(np.max(np.abs(motion[:, first] - motion[:, second])))}
        else:
            ids = [int(stored[0]), int(stored[len(stored) // 2])]
        source_kind = "d3plot"
    else:
        source = (
            plain_path(
                resolve(registry["result.qd-cae__qd-cae-python.qd.cae.dyna_cpp.dyna.binout.lsda"], corpus)
            )
            / "binout"
        )
        ids = [13, 14] if domain == "part" else None
        source_kind = "binout"
    service = Service(Settings(root / "work", executable, (root, corpus / "public-results"), timeout=240))
    if source_kind == "d3plot":
        family = service._result_family(str(source))
    else:
        from ls_prepost_mcp.domain.results.mpp_shards import lasso_reads, shards

        family = [p for shard in shards(source) for p in lasso_reads(shard)]
    tree, identities = input_tree(source, family, keyword=False)
    catalog, _ = read_catalogs(load_registry(), corpus)
    for p, h in identities.items():
        assert h == catalog[p.relative_to(corpus).as_posix()]["sha256"]
    listing = directory_snapshot(family)
    result = service.extract_history(
        str(source),
        domain,
        quantity,
        ids,
        units="source_native_units",
        time_units="source_native_time",
        source_kind=source_kind,
        native_check=True,
    )
    identity = pytestconfig._native_identity
    proof = {k: identity[k] for k in ("working_tree_dirty", "git_diff_sha256", "git_diff_scope")}
    proof.update(
        domain=domain,
        entity_ids=ids,
        quantity=quantity,
        source_kind=source_kind,
        actual_git_revision=identity["actual_git_head"],
        executable=binary,
        source_config_sha256=config_sha,
        status=result["status"],
        error=result.get("error"),
        comparison=result["data"].get("native_comparison"),
        total_samples=result["data"].get("total_samples"),
        curve_count=len(result["data"].get("curves", [])),
        source_tree_sha256=tree["tree_sha256"],
        source_unchanged=all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in identities.items()),
        directory_unchanged=directory_snapshot(family) == listing,
        artifact_sha256=[a["sha256"] for a in result["artifacts"]],
    )
    if domain == "node":
        proof["nonzero_node_oracle"] = node_oracle
    jobs = []
    for directory in service.jobs.root.iterdir():
        if (directory / "job.json").is_file():
            job = json.loads((directory / "job.json").read_text(encoding="utf8"))
            if job.get("action") in ("extract_native_fields", "extract_native_binout_curve"):
                p = job.get("process", {})
                jobs.append(
                    {
                        "status": job["status"],
                        "returncode": p.get("returncode"),
                        "graphics": p.get("graphics"),
                        "timed_out": p.get("timed_out"),
                        "nographics": "-nographics" in p.get("argv", []),
                    }
                )
    proof["native_jobs"] = jobs
    (root / "verified.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf8")
    assert result["status"] == "succeeded", result.get("error")
    assert proof["source_unchanged"] and proof["directory_unchanged"]
    assert proof["curve_count"] == (len(ids) if ids else 1) and proof["total_samples"] > 0
    assert jobs and all(
        j["status"] == "succeeded"
        and j["returncode"] == 0
        and j["nographics"]
        and j["graphics"] is False
        and j["timed_out"] is False
        for j in jobs
    )
