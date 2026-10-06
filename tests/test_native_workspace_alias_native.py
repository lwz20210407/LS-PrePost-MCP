"""I03/KI-049 opt-in batch path alias: save, PNG, reopen and owned cleanup."""

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from ls_prepost_mcp.service import Service
from tests.test_engine_native import native_case as native_case
from tests.test_engine_native import test_five_batch_callers_use_isolated_engine as exercise_caller
from tests.test_engine_native import (
    test_path_builders_batch_unicode_and_spaces_save_png_reopen as exercise_paths,
)

pytestmark = [pytest.mark.native, pytest.mark.skipif(os.name != "nt", reason="Windows directory junctions")]


@pytest.mark.parametrize("folder", ["ascii-workspace", "space folder", "中文 空格"])
def test_alias_batch_save_png_reopen_preserves_original_workspace(native_case, tmp_path, monkeypatch, folder):
    aliases = tmp_path / "aliases"
    aliases.mkdir()
    monkeypatch.setenv("LSPP_NATIVE_ALIAS_ROOT", str(aliases))
    exercise_paths(native_case, folder)
    assert list(aliases.iterdir()) == []
    records = [json.loads(path.read_text(encoding="utf8")) for path in (tmp_path / folder / "jobs").glob("*/job.json")]
    runs = [record for record in records if record.get("process")]
    assert len(runs) == 2 and all(record["status"] == "succeeded" for record in runs)
    for record in runs:
        config = record["process"]["configuration"]
        assert hashlib.sha256(Path(config["source"]).read_bytes()).hexdigest() == config["source_sha256"]
    if not folder.isascii():
        assert all(str(record["process"]["cwd"]).isascii() for record in runs)
        assert all(record["process"]["workspace_alias"]["target"] == record["job_directory"] for record in runs)


@pytest.mark.parametrize("caller", ["service", "scl_backend", "native_results", "native_batch", "programs"])
def test_alias_covers_batch_callers_in_unicode_workspace(native_case, tmp_path, monkeypatch, caller, pytestconfig):
    if caller == "native_batch" and not pytestconfig.getoption("--native-gui"):
        pytest.skip("native_postprocess_case includes a graphical renderer; requires an authorized --native-gui window")
    aliases = tmp_path / "aliases"
    aliases.mkdir()
    monkeypatch.setenv("LSPP_NATIVE_ALIAS_ROOT", str(aliases))
    service, source = native_case
    service = Service(replace(service.settings, workspace=tmp_path / "中文 作业"))
    exercise_caller((service, source.resolve()), caller)
    assert list(aliases.iterdir()) == []
