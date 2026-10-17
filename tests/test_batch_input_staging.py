import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
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
        request = json.loads((directory / "request.json").read_text(encoding="utf8"))
        owned = Path(request["model"])
        assert owned.parent == directory and owned.read_bytes() == before
        assert owned.name == ("input_data" if kind == "keyword" else "d3plot")
        if kind == "d3plot":
            assert (directory / "d3plot01").read_bytes() == b"state family"
        (directory / "response.json").write_text(json.dumps(dict(job_id=directory.name, ok=True,
                                                   data=dict(counts=dict(nodes=1)))))
        return JobResult(operation=kwargs["operation"], job_id=directory.name, status="unverified", data=dict(returncode=0, timed_out=False))

    monkeypatch.setattr("ls_prepost_mcp.service.run_batch", execute)
    result = service.inspect_model(str(source), kind)
    assert result["status"] == "succeeded", result
    assert result["input"]["path"] == str(source.resolve())
    assert len(result["inputs"]) == (2 if kind == "d3plot" else 1)
    assert source.read_bytes() == before


@pytest.mark.parametrize("folder", ["original", "输入 模型"])
def test_include_read_uses_absolute_root_but_export_stays_rejected(tmp_path, monkeypatch, folder):
    original = tmp_path / folder
    original.mkdir()
    source = original / "main.k"
    source.write_text("*KEYWORD\n*INCLUDE\nchild.k\n*END\n")
    (original / "child.k").write_text("*NODE\n1,0,0,0\n")
    exe = tmp_path / "lsprepost4.13.exe"
    exe.touch()
    service = Service(Settings(tmp_path / "work", exe, (original,)))
    before = {p.name: p.read_bytes() for p in original.iterdir()}

    if os.name == "nt" and not str(source).isascii():
        # I04 native evidence supersedes the old mock-only Unicode assumption.
        monkeypatch.setattr("ls_prepost_mcp.service.run_batch",
                            lambda *a, **kw: pytest.fail("Must reject before launch"))
        for operation in (service.inspect_model, service.export_keyword):
            with pytest.raises(ValueError, match="Non-ASCII.*INCLUDE"):
                operation(str(source))
        assert not service.jobs.root.exists()
        assert {p.name: p.read_bytes() for p in original.iterdir()} == before
        return

    def execute(executable, cfile, directory, **kwargs):
        request = json.loads((directory / "request.json").read_text(encoding="utf8"))
        assert Path(request["model"]) == source.resolve()
        assert request["absolute_keyword_path"] is True
        (directory / "response.json").write_text(json.dumps(dict(job_id=directory.name, ok=True,
                                                   data=dict(counts=dict(nodes=1)))))
        return JobResult(operation=kwargs["operation"], job_id=directory.name, status="unverified", data=dict(returncode=0, timed_out=False))

    monkeypatch.setattr("ls_prepost_mcp.service.run_batch", execute)
    assert service.inspect_model(str(source))["status"] == "succeeded"
    assert {p.name: p.read_bytes() for p in original.iterdir()} == before
    with pytest.raises(ValueError, match="include-tree"):
        service.export_keyword(str(source))


@pytest.mark.parametrize("limit", ["bytes", "files"])
def test_large_result_family_is_rejected_before_native_launch(tmp_path, monkeypatch, limit):
    original = tmp_path / "source"
    original.mkdir()
    source = original / "d3plot"
    source.write_bytes(b"synthetic header")
    if limit == "files":
        for number in range(1, 1001):
            (original / ("d3plot" + str(number))).write_bytes(b"state")
    else:
        stat = Path.stat

        def large_stat(path, *args, **kwargs):
            value = stat(path, *args, **kwargs)
            if path == source:
                fields = list(value)
                fields[6] = 2 * 1024**3 + 1
                return os.stat_result(fields)
            return value

        monkeypatch.setattr(Path, "stat", large_stat)
    exe = tmp_path / "lsprepost4.13.exe"
    exe.touch()
    service = Service(Settings(tmp_path / "work", exe, (original,)))

    monkeypatch.setattr("ls_prepost_mcp.service.run_batch", lambda *args, **kwargs: pytest.fail("Must reject before launch"))
    with pytest.raises(ValueError, match="1000 files / 2 GiB"):
        service.inspect_model(str(source), "d3plot")
    assert not service.jobs.root.exists()
    assert source.read_bytes() == b"synthetic header"


@pytest.mark.parametrize("mutation", ["modify", "add", "remove"])
def test_result_family_mutation_during_execution_is_rejected(tmp_path, monkeypatch, mutation):
    original = tmp_path / "source"
    original.mkdir()
    source = original / "d3plot"
    source.write_bytes(b"header")
    state = original / "d3plot01"
    state.write_bytes(b"state")
    exe = tmp_path / "lsprepost4.13.exe"
    exe.touch()
    service = Service(Settings(tmp_path / "work", exe, (original,)))

    def execute(executable, cfile, directory, **kwargs):
        if mutation == "modify":
            state.write_bytes(b"changed state")
        elif mutation == "add":
            (original / "d3plot02").write_bytes(b"extra state")
        else:
            state.unlink()
        (directory / "response.json").write_text(json.dumps(dict(job_id=directory.name, ok=True,
                                                                  data=dict(counts=dict(nodes=8)))))
        return JobResult(operation=kwargs["operation"], job_id=directory.name, status="unverified", data=dict(returncode=0, timed_out=False))

    monkeypatch.setattr("ls_prepost_mcp.service.run_batch", execute)
    result = service.inspect_model(str(source), "d3plot")
    assert result["status"] == "failed"
    assert "Input family changed" in result["error"]["message"]


def test_embedded_include_open_keeps_user_directory_unchanged(tmp_path, monkeypatch):
    from ls_prepost_mcp import embedded
    from ls_prepost_mcp.native import commands as nc

    original = tmp_path / "输入 模型"
    original.mkdir()
    source = original / "main.k"
    source.write_bytes(b"*KEYWORD\n*INCLUDE\nchild.k\n*END\n")
    (original / "child.k").write_bytes(b"*NODE\n1,0,0,0\n")
    before = {p.name: p.read_bytes() for p in original.iterdir()}
    work = tmp_path / "job"
    work.mkdir()
    monkeypatch.chdir(work)
    calls = []

    def execute(command):
        calls.append(command)
        assert Path.cwd() == work
        Path("native-side-effect.txt").write_text("owned output", encoding="utf8")

    monkeypatch.setitem(sys.modules, "LsPrePost", SimpleNamespace(execute_command=execute))
    monkeypatch.setitem(sys.modules, "DataCenter", SimpleNamespace(get_data=lambda key, **kwargs: 8 if key == "num_nodes" else 0))
    request = work / "request.json"
    response = work / "response.json"
    request.write_text(json.dumps(dict(job_id="test", action="probe", parameters={}, model=str(source),
                                       file_type="keyword", job_directory=str(work), absolute_keyword_path=True)), encoding="utf8")
    embedded.run(str(request), str(response))
    assert json.loads(response.read_text())["ok"] is True
    assert calls == [nc.open_model(str(source), "keyword")]
    assert {p.name: p.read_bytes() for p in original.iterdir()} == before
    assert (work / "native-side-effect.txt").is_file()
