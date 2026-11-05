"""Limited Q06 GLSTAT L2: one registered 101-state input, two named quantities, 4.13 only."""
import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.engine.environment import locate_config
from ls_prepost_mcp.native.versions import profile
from ls_prepost_mcp.service import Service
from tools.fetch_corpus import entries, load_registry, plain_path, read_catalogs, resolve
from tools.public_corpus_preflight import directory_snapshot

pytestmark = pytest.mark.native
CORPUS_ID = "result.NaudeConradie__Masters-Project.Models.Old.Other.LSDyna_Unit_Cell_Corner.Steel_Explicit"
# Pinned only after the full-record observations on this registered source and
# 4.13 binary: code 1 uniquely matched kinetic, code 2 uniquely matched internal.
# This is not a general UI-number mapping for arbitrary versions/quantities.
CASES = [("kinetic_energy", 1), ("internal_energy", 2)]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@pytest.fixture(scope="module")
def installation(pytestconfig):
    """Use the existing opt-in/config identity contract without optional reader dependencies."""
    if not pytestconfig.getoption("--run-native"):
        pytest.skip("GLSTAT native export requires explicit --run-native")
    unavailable = pytest.fail if pytestconfig.getoption("--native-strict") else pytest.skip
    selected = pytestconfig.getoption("--native-executable")
    if not selected:
        unavailable("Set --native-executable for the registered headless GLSTAT regression")
    executable = Path(selected)
    config = locate_config(executable, os.environ)
    if config is None:
        unavailable("An initialized LS-PrePost configuration is required")
    identity = pytestconfig._native_identity
    assert identity["actual_git_head"] and identity["working_tree_dirty"] is False
    binary_sha, config_sha = digest(executable), digest(config)
    yield executable, {"name": executable.name, "version": profile(executable)["version"],
                       "sha256": binary_sha}, config_sha
    assert digest(executable) == binary_sha and digest(config) == config_sha


def csv_values(artifact, value_column):
    path = Path(artifact["path"])
    assert digest(path) == artifact["sha256"]
    with path.open(newline="", encoding="utf8") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ["time", value_column]
        rows = np.asarray([(float(row["time"]), float(row[value_column])) for row in reader])
    assert digest(path) == artifact["sha256"]
    assert rows.ndim == 2 and rows.shape[1] == 2 and np.isfinite(rows).all()
    return rows


@pytest.mark.parametrize("component,native_code", CASES, ids=[name for name, _ in CASES])
def test_registered_glstat_named_quantities_match_413_full_record(
    installation, pytestconfig, component, native_code
):
    executable, binary, config_sha = installation
    if binary["version"] != "4.13":
        pytest.fail("This GLSTAT regression is registered for 4.13 only; other versions require a separate plan")
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        unavailable = pytest.fail if pytestconfig.getoption("--native-strict") else pytest.skip
        unavailable("Set LSPP_CORPUS_DIR to the existing registered GLSTAT corpus")
    corpus = plain_path(Path(location))
    registry = load_registry()
    source = plain_path(resolve(entries(registry)[CORPUS_ID], corpus) / "glstat")
    before = digest(source)
    catalog, _ = read_catalogs(registry, corpus)
    assert before == catalog[source.relative_to(corpus).as_posix()]["sha256"]
    listing = directory_snapshot([source])
    root = pytestconfig._native_root / f"glstat-{component}-413"
    root.mkdir()
    service = Service(Settings(root / "work", executable, (root, corpus / "public-results"), timeout=60))
    reader = service.extract_database(str(source), "glstat", component, "source_model_energy",
                                      time_units="source_model_time")
    assert reader["status"] == "succeeded", reader.get("error")
    assert reader["backend"] == "ls-dyna-ascii" and reader["data"]["source_kind"] == "ascii"
    assert reader["data"]["ids"] is None and reader["data"]["source_sha256"] == before
    expected = csv_values(reader["artifacts"][0], component)
    assert expected.shape == (101, 2)
    native = service.extract_native_ascii_curve(str(source), "glstat", native_code, "source_model_energy")
    jobs = []
    for path in service.jobs.root.glob("*/job.json"):
        job = json.loads(path.read_text(encoding="utf8"))
        if job["action"] == "extract_native_ascii_curve":
            process = job.get("process", {})
            jobs.append(dict(status=job["status"], returncode=process.get("returncode"),
                             pid=process.get("pid"),
                             graphics=process.get("graphics"), timed_out=process.get("timed_out"),
                             nographics="-nographics" in process.get("argv", []),
                             input_sha256=[item.get("sha256") for item in job.get("inputs", [])],
                             same_source_path=(len(job.get("inputs", [])) == 1
                                and Path(job["inputs"][0]["path"]).resolve() == source.resolve()),
                             configuration_sha256=process.get("configuration", {}).get("source_sha256")))
    proof = dict(corpus_id=CORPUS_ID, member="glstat", component=component, native_component_code=native_code,
                 component_scope="Only this registered source and recorded 4.13 binary; not a universal UI mapping",
                 actual_git_revision=pytestconfig._native_identity["actual_git_head"],
                 working_tree_dirty=pytestconfig._native_identity["working_tree_dirty"],
                 git_diff_sha256=pytestconfig._native_identity["git_diff_sha256"],
                 git_diff_scope=pytestconfig._native_identity["git_diff_scope"],
                 executable=binary, source_config_sha256=config_sha, source_sha256=before,
                 input_family=[dict(member="glstat", sha256=before, size_bytes=source.stat().st_size)],
                 input_family_scope="One explicitly registered ASCII file; no sibling substitution",
                 native_status=native.get("status"), error=native.get("error"), native_jobs=jobs,
                 native_attempted=True, native_executed=any(j["pid"] is not None for j in jobs), full_record=True,
                 tolerances=dict(time=dict(rtol=1e-6, atol=0),
                                 value=dict(rtol=2e-5, atol=1e-6*float(np.max(np.abs(expected[:, 1]))))))
    if native.get("status") == "succeeded":
        assert native["data"]["entity_id"] is None and native["data"]["component_code"] == native_code
        observed = csv_values(next(a for a in native["artifacts"] if a["kind"] == "csv"), "value")
        proof["shape_agrees"] = observed.shape == expected.shape
        proof["samples"] = len(observed)
        if proof["shape_agrees"]:
            proof.update(time_agrees=bool(np.allclose(observed[:, 0], expected[:, 0], rtol=1e-6, atol=0)),
                         values_agree=bool(np.allclose(observed[:, 1], expected[:, 1], rtol=2e-5,
                                                       atol=proof["tolerances"]["value"]["atol"])),
                         max_time_error=float(np.max(np.abs(observed[:, 0]-expected[:, 0]))),
                         max_value_error=float(np.max(np.abs(observed[:, 1]-expected[:, 1]))))
    proof["source_unchanged"] = digest(source) == before
    proof["source_directory_unchanged"] = directory_snapshot([source]) == listing
    (root / "verified.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf8")
    assert proof["native_status"] == "succeeded", proof["error"]
    assert proof.get("shape_agrees") and proof.get("time_agrees") and proof.get("values_agree"), proof
    assert proof["source_unchanged"] and proof["source_directory_unchanged"]
    assert len(jobs) == 1 and all(j["status"] == "succeeded" and j["returncode"] == 0
                                and j["graphics"] is False and j["nographics"]
                                and j["timed_out"] is False and j["input_sha256"] == [before]
                                and j["same_source_path"] and j["configuration_sha256"] == config_sha for j in jobs)
