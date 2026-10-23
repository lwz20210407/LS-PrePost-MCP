"""Q06 force curves compared with independent headless native ASCII/XYPlot exports."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from tests.test_save_model_native import installation as installation
from tools.fetch_corpus import entries, load_registry, plain_path, read_catalogs, resolve
from tools.public_corpus_preflight import directory_snapshot

pytestmark = pytest.mark.native
CASES = [
    (database, component, False)
    for database in ("rcforc", "secforc")
    for component in ("x_force", "y_force", "z_force")
] + [("secforc", "z_force", True)]
IDS = [f"{d}-{c}" + ("-wrong-component" if wrong else "") for d, c, wrong in CASES]


@pytest.mark.parametrize("database,component,wrong", CASES, ids=IDS)
def test_public_named_forces_match_native_and_reject_wrong_component(
    installation, pytestconfig, monkeypatch, database, component, wrong
):
    executable, binary, config_sha = installation
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        pytest.skip("Set LSPP_CORPUS_DIR to registered external force files")
    corpus = plain_path(Path(location))
    corpus_id = (
        "result.lsdyna-ansys-com__lspp-mini-tutorials.rcforc"
        if database == "rcforc"
        else "result.pranavduraisamy__helmet-fit-bayes-opt.bo-runs.run0.pendulum"
    )
    source = plain_path(resolve(entries(load_registry())[corpus_id], corpus) / database)
    case = f"{database}-{component}" + ("-wrong-component" if wrong else "")
    root = pytestconfig._native_root / case
    root.mkdir()
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    catalog, _ = read_catalogs(load_registry(), corpus)
    assert before == catalog[source.relative_to(corpus).as_posix()]["sha256"]
    listing = directory_snapshot([source])
    service = Service(Settings(root / "work", executable, (root, corpus / "public-results"), timeout=120))
    if wrong:
        original = service.extract_native_ascii_curve

        def other_axis(path, database, code, units, **kwargs):
            return original(path, database, 1, units, **kwargs)

        monkeypatch.setattr(service, "extract_native_ascii_curve", other_axis)
    result = service.extract_database(
        str(source),
        database,
        component,
        "source_native_force",
        entity_ids=[1],
        time_units="source_native_time",
        native_check=True,
    )
    identity = pytestconfig._native_identity
    proof = {k: identity[k] for k in ("working_tree_dirty", "git_diff_sha256", "git_diff_scope")}
    proof.update(
        case=case,
        corpus_id=corpus_id,
        actual_git_revision=identity["actual_git_head"],
        executable=binary,
        source_config_sha256=config_sha,
        source_sha256=before,
        status=result["status"],
        expected_status="failed" if wrong else "succeeded",
        error=result.get("error"),
        backend=result["backend"],
        database=database,
        component=component,
        comparison=result.get("data", {}).get("native_comparison"),
        source_unchanged=hashlib.sha256(source.read_bytes()).hexdigest() == before,
        directory_unchanged=directory_snapshot([source]) == listing,
        artifact_sha256=[a["sha256"] for a in result["artifacts"]],
    )
    if wrong and proof["error"]:
        proof["error"] = {"type": proof["error"]["type"], "message": proof["error"]["message"]}
    jobs = []
    for path in service.jobs.root.glob("*/job.json"):
        job = json.loads(path.read_text(encoding="utf8"))
        if job["action"] == "extract_native_ascii_curve":
            p = job.get("process", {})
            jobs.append(
                dict(
                    status=job["status"],
                    returncode=p.get("returncode"),
                    graphics=p.get("graphics"),
                    nographics="-nographics" in p.get("argv", []),
                    timed_out=p.get("timed_out"),
                )
            )
    proof["native_jobs"] = jobs
    (root / "verified.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf8")
    assert proof["status"] == proof["expected_status"], result.get("error")
    assert proof["source_unchanged"] and proof["directory_unchanged"]
    assert proof["backend"] == "ls-dyna-ascii"
    assert jobs and all(
        j["status"] == "succeeded"
        and j["returncode"] == 0
        and j["nographics"]
        and j["graphics"] is False
        and j["timed_out"] is False
        for j in jobs
    )
    if wrong:
        assert "disagree" in result["error"]["message"] and not result["artifacts"]
    else:
        curves = proof["comparison"]["curves"]
        assert len(curves) == (2 if database == "rcforc" else 1)
        assert {c["side"] for c in curves} == ({0, 1} if database == "rcforc" else {None})
        assert all(c["samples"] == (121 if database == "rcforc" else 250) for c in curves)
