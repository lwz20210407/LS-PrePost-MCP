"""Q01 opt-in headless comparison on registered public result families."""
import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.engine.environment import locate_config
from ls_prepost_mcp.native.versions import profile
from ls_prepost_mcp.service import Service
from tools.fetch_corpus import entries, load_registry, plain_path, resolve

pytestmark = pytest.mark.native
CASES = [
    ("projectile", "result.ansys__example-data.result_files.d3plot_projectile", 16),
    ("shell", "shell_d3plot", 7),
    ("bolt", "result.hu-shuhan__editOpeniGame.test.Format_Validation_Test.lsdyna.Bolt_B_Explicit", 102),
]


def _sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@pytest.fixture(scope="module")
def native_overview(pytestconfig):
    if not pytestconfig.getoption("--run-native"):
        pytest.skip("Native overview comparison requires explicit --run-native")
    unavailable = pytest.fail if pytestconfig.getoption("--native-strict") else pytest.skip
    location = os.environ.get("LSPP_CORPUS_DIR")
    executable = pytestconfig.getoption("--native-executable")
    if not location or not executable:
        unavailable("Set LSPP_CORPUS_DIR and --native-executable for the public headless comparison")
    pytest.importorskip("lasso.dyna")
    executable = Path(executable)
    config = locate_config(executable, os.environ)
    if config is None:
        unavailable("An initialized LS-PrePost configuration is required")
    identity = pytestconfig._native_identity
    assert identity["actual_git_head"] and identity["working_tree_dirty"] is False
    installation = profile(executable)
    binary_sha, config_sha = _sha(executable), _sha(config)
    yield Path(location), executable, dict(name=executable.name, sha256=binary_sha,
        version=installation.get("version"), file_version=installation.get("file_version")), config_sha
    assert _sha(executable) == binary_sha
    assert _sha(config) == config_sha


@pytest.mark.parametrize("name,corpus_id,states", CASES, ids=[case[0] for case in CASES])
def test_public_inventory_agrees_with_native_batch(native_overview, pytestconfig, record_property,
                                                  name, corpus_id, states):
    root, executable, executable_identity, config_sha = native_overview
    source = plain_path(resolve(entries(load_registry())[corpus_id], root))
    if source.is_dir():
        source = source / "d3plot"
    family = sorted(p for p in source.parent.iterdir() if p.is_file()
                    and re.fullmatch(re.escape(source.name) + r"\d*", p.name))
    assert family and source in family
    before = {p.name: _sha(p) for p in family}
    listing = sorted(p.name for p in source.parent.iterdir())
    directory = pytestconfig._native_root / name
    service = Service(Settings(directory, executable, (root,), timeout=120))
    result = JobResult.model_validate(service.result_info(str(source), native_check=True))
    checks = {check.name: check.status for check in result.checks}
    data = result.data
    native = data.get("lsprepost", {})
    identity = pytestconfig._native_identity
    evidence = dict(corpus_id=corpus_id, actual_git_revision=identity["actual_git_head"],
        working_tree_dirty=identity["working_tree_dirty"], git_diff_sha256=identity["git_diff_sha256"],
        git_diff_scope=identity["git_diff_scope"], native_run=True, graphics=False,
        executable=executable_identity, source_config_sha256=config_sha,
        source_sha256=before, source_unchanged=before == {p.name: _sha(p) for p in family},
        directory_unchanged=listing == sorted(p.name for p in source.parent.iterdir()),
        result_info_job_id=result.job_id, native_job_id=native.get("job_id"),
        status=result.status, checks=checks, reader_backend=data.get("lasso_backend"),
        states=data.get("states"), native_states=native.get("states"), comparison=data.get("comparison"),
        reader_times=data.get("times"), native_times=native.get("times"))
    directory.mkdir(parents=True, exist_ok=True)
    proof = directory / "verified.json"
    proof.write_text(json.dumps(evidence, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    record_property("native_evidence", str(proof))
    assert result.status == "succeeded", result.error
    assert data["states"] == native["states"] == states
    assert checks["backends_agree"] == "passed"
    assert data["comparison"]["state_counts_equal"] and data["comparison"]["times_equal"]
    assert result.job_id and native["job_id"]
    assert evidence["source_unchanged"] and evidence["directory_unchanged"]
