"""A05 negative regression: loading a native macro is not executing it."""

import json

import pytest

from ls_prepost_mcp.engine import BatchEngine, BatchJob
from tests.test_engine_native import native_case  # noqa: F401


@pytest.mark.native
def test_native_macro_load_is_unverified_without_execution_receipt(native_case):  # noqa: F811
    service, source = native_case
    directory = service.settings.workspace / "macro-load"
    directory.mkdir()
    macro = directory / "source.mac"
    macro.write_text('*macro begin A05LoadProbe\nparameter x 1\ntop\nsave keyword "macro-only.k"\n*macro end\n')
    cfile = directory / "run.cfile"
    cfile.write_text('open keyword "' + str(source / "input.k") + '"\nexit\n')
    result = BatchEngine().run(BatchJob(service.settings.executable, cfile, directory, 30, macro_file=macro))
    (directory / "evidence.json").write_text(json.dumps(result.model_dump(mode="json"), indent=2))
    assert result.status == "unverified", result
    assert result.data["returncode"] == 0
    assert not (directory / "macro-only.k").exists()


def test_macro_file_must_be_an_owned_job_file(tmp_path):
    directory = tmp_path / "job"
    directory.mkdir()
    foreign = tmp_path / "foreign.mac"
    foreign.write_text("*macro begin test\n*macro end\n")
    with pytest.raises(ValueError, match="inside the job"):
        BatchJob(tmp_path / "lsprepost4.13.exe", directory / "run.cfile", directory, 10, macro_file=foreign)
