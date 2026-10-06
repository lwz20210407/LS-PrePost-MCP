"""I01: 4.10 must not certify a model after failing to open a relative INCLUDE."""
import hashlib
import json

import pytest

from ls_prepost_mcp.native.versions import installation_version
from tests.test_engine_native import native_case as native_case

pytestmark = pytest.mark.native


@pytest.mark.parametrize("absolute", [False, True], ids=["relative-fails", "absolute-loads"])
def test_native_include_open_failure_is_not_success(native_case, tmp_path, absolute):
    service, fixture = native_case
    if installation_version(service.settings.executable) != "4.10":
        pytest.skip("This regression targets 4.10 cwd-relative INCLUDE resolution")
    source = tmp_path / "source"
    source.mkdir()
    child = source / "first.k"
    child.write_text("*KEYWORD\n*NODE\n100001,5,5,5\n*END\n", encoding="utf8")
    main = source / "main.k"
    model = (fixture / "input.k").read_text(encoding="utf8")
    name = str(child) if absolute else "first.k"
    main.write_text(model.replace("*END", "*INCLUDE\n" + name + "\n*END"), encoding="utf8")
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    result = service.inspect_model(str(main))
    if absolute:
        assert result["status"] == "succeeded", result.get("error")
        assert result["data"]["counts"]["nodes"] == 9
    else:
        assert result["status"] == "failed", result
        assert "Include File first.k Not open" in result["error"]["message"]
        assert any("Include File" in line for line in result["process"]["diagnostics"])
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    (tmp_path / "include-verdict.json").write_text(json.dumps(dict(
        absolute=absolute, status=result["status"], job_id=result["job_id"],
        diagnostic=result.get("error"), source_files_unchanged=True), ensure_ascii=False), encoding="utf8")
