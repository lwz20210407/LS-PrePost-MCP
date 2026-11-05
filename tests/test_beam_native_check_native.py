"""Q05 opt-in product native_check on the two frozen small public beam families."""

import csv
import json
import os
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.engine.environment import locate_config
from ls_prepost_mcp.service import Service
from tests.test_beam_axial_native import CASES, sha, source_directory_bytes
from tests.test_save_model_native import installation as installation
from tools.fetch_corpus import entries, load_registry, plain_path, resolve
from tools.public_corpus_preflight import directory_snapshot

pytestmark = pytest.mark.native


@pytest.mark.parametrize("label,corpus_id,beam_count,state_count,entity_ids,expected_family", CASES,
                         ids=["beamip", "ansys-beam"])
def test_beam_axial_product_native_check(installation, pytestconfig, label, corpus_id, beam_count,
                                         state_count, entity_ids, expected_family):
    executable, binary, config_sha = installation
    assert binary["version"] == "4.13", "This product comparison is admitted only for 4.13"
    if label != "beamip" and not getattr(pytestconfig, "_beam_native_product_seed_passed", False):
        pytest.skip("The two-state named beamip comparison must pass before the larger case")
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        unavailable = pytest.fail if pytestconfig.getoption("--native-strict") else pytest.skip
        unavailable("Set LSPP_CORPUS_DIR for the frozen small public beam families")
    dyna = pytest.importorskip("lasso.dyna")
    corpus = plain_path(Path(location))
    source = plain_path(resolve(entries(load_registry())[corpus_id], corpus)) / "d3plot"
    root = pytestconfig._native_root / label
    root.mkdir()
    service = Service(Settings(root, executable, (corpus,), timeout=60))
    family = service._result_family(str(source))
    before = {p.name: sha(p) for p in family}
    assert before == expected_family
    listing, directory_bytes = directory_snapshot(family), source_directory_bytes(family)
    config = locate_config(executable, os.environ)
    assert config is not None and sha(config) == config_sha
    kind = dyna.ArrayType
    reference = dyna.D3plot(str(source), state_array_filter=[kind.global_timesteps,
        kind.element_beam_axial_force, kind.element_beam_is_alive])
    stored_ids = list(reference.arrays[kind.element_beam_ids])
    assert len(stored_ids) == beam_count
    raw = reference.arrays[kind.element_beam_axial_force]
    times = reference.arrays[kind.global_timesteps]
    assert raw.shape == (state_count, beam_count) and any(np.any(raw[:, stored_ids.index(uid)]) for uid in entity_ids)
    identity = pytestconfig._native_identity
    proof = dict(actual_git_revision=identity["actual_git_head"], working_tree_dirty=identity["working_tree_dirty"],
        git_diff_sha256=identity["git_diff_sha256"], git_diff_scope=identity["git_diff_scope"],
        corpus_id=corpus_id, executable=binary, source_config_sha256=config_sha, graphics=False,
        original_family_sha256=before, entity_ids=entity_ids, state_count=state_count,
        native_sampling="default", ipt="binding default; semantics not independently identified",
        coordinate_frame="as stored", status="failed")
    try:
        result = service.extract_history(str(source), "beam", "axial_force", entity_ids,
            units="caller_force_units", time_units="caller_time_units", native_check=True,
            native_sampling="default")
        proof["result"] = result
        assert result["status"] == "succeeded", result.get("error")
        comparison = result["data"]["native_comparison"]
        assert comparison["native_sampling"] == "default" and comparison["ipt"] == proof["ipt"]
        assert comparison["coordinate_frame"] == "as stored"
        child = service.jobs.get(comparison["job_ids"][0])
        assert child["native_channel"] == "embedded_python" and all(child["native_identity_checks"].values())
        assert child["data"]["native_marker"]["beam_count"] == beam_count
        for uid, artifact in zip(entity_ids, result["artifacts"]):
            with Path(artifact["path"]).open(newline="", encoding="utf8") as stream:
                rows = list(csv.DictReader(stream))
            np.testing.assert_array_equal([float(row["value"]) for row in rows], raw[:, stored_ids.index(uid)])
            np.testing.assert_array_equal([float(row["time"]) for row in rows], times)
        proof.update(status="passed", total_samples=state_count*len(entity_ids), native_comparison=comparison,
                     native_identity_checks=child["native_identity_checks"])
    except Exception as error:
        proof["error"] = dict(type=type(error).__name__, message=str(error))
        raise
    finally:
        guards = dict(input_family_unchanged=lambda: {p.name: sha(p) for p in service._result_family(str(source))} == before,
                      source_directory_unchanged=lambda: directory_snapshot(family) == listing
                        and source_directory_bytes(family) == directory_bytes,
                      configuration_unchanged=lambda: sha(config) == config_sha,
                      binary_unchanged=lambda: sha(executable) == binary["sha256"])
        for name, check in guards.items():
            try:
                proof[name] = bool(check())
            except Exception as guard_error:
                proof[name] = False
                proof.setdefault("guard_errors", {})[name] = str(guard_error)
        if not all(proof[name] for name in guards):
            proof["status"] = "failed"
        (root / "comparison.json").write_text(json.dumps(proof, separators=(",", ":")) + "\n", encoding="utf8")
        if "error" not in proof:
            assert all(proof[name] for name in guards)
    if label == "beamip":
        pytestconfig._beam_native_product_seed_passed = True
