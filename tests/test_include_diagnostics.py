import json

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.native_log import native_errors
from ls_prepost_mcp.service import Service


@pytest.mark.parametrize("line", ["Error - Include File first.k Not open", " error - include file 中文 part.k not open "])
def test_missing_include_diagnostic_is_an_error(line):
    assert native_errors(line) == [line.strip()]
    assert native_errors("Include File first.k opened successfully") == []


@pytest.mark.parametrize("content", ["*KEYWORD\n*END\n".encode("utf16"), b"\x00\x01binary", b"*KEYWORD\n*INCLUDE\nmissing.k\n*END\n"])
def test_outside_error_precedes_external_file_diagnostics(tmp_path, content):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    external = tmp_path / "secret.k"
    external.write_bytes(content)
    main = allowed / "main.k"
    main.write_text("*KEYWORD\n*INCLUDE\n../secret.k\n*END\n")
    with pytest.raises(ValueError, match="outside"):
        Settings(allowed).check_keyword_includes(main)


@pytest.mark.parametrize("text", ["*KEYWORD\n *INCLUDE\nchild.k\n*END\n", "*KEYWORD\n*END\n*INCLUDE\nchild.k\n"])
def test_ignored_include_syntax_is_rejected(tmp_path, text):
    main = tmp_path / "main.k"
    main.write_text(text)
    (tmp_path / "child.k").write_text("*KEYWORD\n*END\n")
    with pytest.raises(ValueError, match=r"first column|after \*END"):
        Settings(tmp_path).check_keyword_includes(main)


def test_cwd_rejection_marks_created_job_failed(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    main = source / "main.k"
    main.write_text("*KEYWORD\n*INCLUDE\nchild.k\n*END\n")
    (source / "child.k").write_text("*KEYWORD\n*END\n")
    exe = tmp_path / "lspp.exe"
    exe.touch()
    service = Service(Settings(tmp_path / "work", exe, (source,)))
    create = service.jobs.create

    def with_alternate(*args):
        directory, manifest = create(*args)
        (directory / "child.k").write_text("*KEYWORD\n*END\n")
        return directory, manifest

    monkeypatch.setattr(service.jobs, "create", with_alternate)
    monkeypatch.setattr("ls_prepost_mcp.service.run_batch", lambda *a, **kw: pytest.fail("Must reject before native launch"))
    with pytest.raises(ValueError, match="different file"):
        service.inspect_model(str(main))
    paths = list(service.jobs.root.glob("*/job.json"))
    assert len(paths) == 1
    result = json.loads(paths[0].read_text(encoding="utf8"))
    assert result["status"] == "failed"
    assert "different file" in result["error"]["message"] and result["finished_at"]
