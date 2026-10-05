import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


@pytest.mark.parametrize("kind", ["keyword", "d3plot"])
def test_batch_stages_native_input_and_verifies_original_family(tmp_path, monkeypatch, kind):
    original = tmp_path / "原始 数据"
    original.mkdir()
    source = original / ("模型.k" if kind == "keyword" else "custom.d3plot")
    source.write_text("*KEYWORD\n*NODE\n1,0,0,0\n*END\n")
    if kind == "d3plot":
        (original / "custom.d3plot01").write_bytes(b"state family")
    exe = tmp_path / "lsprepost4.13.exe"
    exe.touch()
    service = Service(Settings(tmp_path / "work", exe, (original,)))
    before = source.read_bytes()

    def execute(executable, cfile, directory, **kwargs):
        request = json.loads((directory / "request.json").read_text())
        owned = Path(request["model"])
        assert owned.parent == directory and owned.read_bytes() == before
        assert owned.name == ("input_data" if kind == "keyword" else "d3plot")
        if kind == "d3plot":
            assert (directory / "d3plot01").read_bytes() == b"state family"
        (directory / "response.json").write_text(json.dumps(dict(job_id=directory.name, ok=True,
                                                   data=dict(counts=dict(nodes=1)))))
        return dict(returncode=0, timed_out=False, engine_status="unverified")

    monkeypatch.setattr("ls_prepost_mcp.service.execute", execute)
    result = service.inspect_model(str(source), kind)
    assert result["status"] == "succeeded", result
    assert result["input"]["path"] == str(source.resolve())
    assert len(result["inputs"]) == (2 if kind == "d3plot" else 1)
    assert source.read_bytes() == before


def test_include_read_uses_absolute_root_but_export_stays_rejected(tmp_path, monkeypatch):
    original = tmp_path / "original"
    original.mkdir()
    source = original / "main.k"
    source.write_text("*KEYWORD\n*INCLUDE\nchild.k\n*END\n")
    (original / "child.k").write_text("*NODE\n1,0,0,0\n")
    exe = tmp_path / "lsprepost4.13.exe"
    exe.touch()
    service = Service(Settings(tmp_path / "work", exe, (original,)))

    def execute(executable, cfile, directory, **kwargs):
        request = json.loads((directory / "request.json").read_text())
        assert Path(request["model"]) == source.resolve()
        assert request["absolute_keyword_path"] is True
        (directory / "response.json").write_text(json.dumps(dict(job_id=directory.name, ok=True,
                                                   data=dict(counts=dict(nodes=1)))))
        return dict(returncode=0, timed_out=False)

    monkeypatch.setattr("ls_prepost_mcp.service.execute", execute)
    assert service.inspect_model(str(source))["status"] == "succeeded"
    with pytest.raises(ValueError, match="include-tree"):
        service.export_keyword(str(source))
