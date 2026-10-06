"""I01 review regression: user files cannot replace engine execution evidence."""

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


@pytest.mark.parametrize("name", ["engine-result.json", "ENGINE-RESULT.JSON"])
@pytest.mark.parametrize("role", ["output", "dependency"])
def test_engine_result_name_is_rejected_during_preparation(tmp_path, name, role):
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    arguments = {}
    if role == "output":
        arguments["outputs"] = [dict(name=name, kind="json")]
    else:
        source = tmp_path / name
        source.write_text('{"user_payload": 42}', encoding="utf8")
        arguments["dependencies"] = [dict(path=str(source), name=name)]
    with pytest.raises(ValueError, match="reserved"):
        service.prepare_native_program("command", code="top", **arguments)
    assert not (tmp_path / "work" / "jobs").exists()
