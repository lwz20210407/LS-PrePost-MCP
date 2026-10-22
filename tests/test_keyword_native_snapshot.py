"""I01: the native reader sees owned ASCII snapshots, never user Include paths."""
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.domain.model import preflight_includes
from ls_prepost_mcp.service import Service


def setup_case(tmp_path, folder="source", header="", child="nodes.k"):
    source = tmp_path / folder
    source.mkdir()
    mesh = source / "mesh" if header else source
    mesh.mkdir(exist_ok=True)
    (mesh / child).write_bytes(b"$ preserve this comment\r\n*NODE\r\n1,0,0,0\r\n")
    main = source / "main.k"
    main.write_text("*KEYWORD\n" + (header + "\nmesh\n" if header else "")
                    + "*INCLUDE\n" + child + "\n*END\n", encoding="utf-8")
    exe = tmp_path / "lsprepost4.13.exe"
    exe.touch()
    return Service(Settings(tmp_path / "work", exe, (source,))), main, mesh / child


@pytest.mark.parametrize("folder,header,child", [("source", "", "nodes.k"),
    ("输入 模型", "", "节点.k"), ("source", "*INCLUDE_PATH", "nodes.k"),
    ("source", "*INCLUDE_PATH_RELATIVE", "nodes.k")])
def test_native_consumes_only_owned_ascii_files_and_releases_successful_copies(tmp_path, monkeypatch, folder, header, child):
    service, main, leaf = setup_case(tmp_path, folder, header, child)
    before = {p: p.read_bytes() for p in (main, leaf)}
    staged = []

    def execute(executable, cfile, directory, **kwargs):
        request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
        owned = Path(request["model"])
        assert owned.parent == directory and owned.name.isascii()
        assert request["absolute_keyword_path"] is False
        report = preflight_includes(owned)
        assert report["ok"]
        for file in report["files"]:
            path = Path(file["path"])
            assert path.parent == directory and path.name.isascii()
            staged.append(path)
        assert len(staged) == 2
        assert any(p.read_bytes() == before[leaf] for p in staged)
        assert all(ref["name"] == "." if ref["kind"] == "path" else Path(ref["name"]).name == ref["name"]
                   for ref in report["references"])
        (directory / "response.json").write_text(json.dumps({"job_id": directory.name, "ok": True,
            "data": {"counts": {"nodes": 1, "elements": 0}, "part_ids": []}}))
        return JobResult(operation=kwargs["operation"], job_id=directory.name, status="unverified",
                         data={"returncode": 0, "timed_out": False})

    monkeypatch.setattr("ls_prepost_mcp.service.run_batch", execute)
    result = service.inspect_model(str(main))
    assert result["status"] == "succeeded", result.get("error")
    assert {p: p.read_bytes() for p in before} == before
    assert staged and all(not p.exists() for p in staged)
    assert result["input_tree"]["cleanup"]["retained"] == []


def test_included_file_change_cannot_be_hidden_by_unchanged_main(tmp_path, monkeypatch):
    service, main, leaf = setup_case(tmp_path)

    def execute(executable, cfile, directory, **kwargs):
        leaf.write_bytes(b"*NODE\n2,0,0,0\n")
        (directory / "response.json").write_text(json.dumps({"job_id": directory.name, "ok": True,
            "data": {"counts": {"nodes": 1}}}))
        return JobResult(operation=kwargs["operation"], job_id=directory.name, status="unverified",
                         data={"returncode": 0, "timed_out": False})

    monkeypatch.setattr("ls_prepost_mcp.service.run_batch", execute)
    result = service.inspect_model(str(main))
    assert result["status"] == "failed" and "Input tree changed" in result["error"]["message"]


def test_ambiguous_include_is_refused_before_a_native_job(tmp_path, monkeypatch):
    service, main, leaf = setup_case(tmp_path)
    sub = main.parent / "sub"
    sub.mkdir()
    (sub / "assembly.k").write_text("*INCLUDE\nnodes.k\n")
    (sub / "nodes.k").write_bytes(leaf.read_bytes())
    main.write_text("*KEYWORD\n*INCLUDE\nsub/assembly.k\n*END\n")
    assert any(p["kind"] == "ambiguous" for p in preflight_includes(main)["problems"])
    monkeypatch.setattr("ls_prepost_mcp.service.run_batch", lambda *a, **kw: pytest.fail("Ambiguous tree launched"))
    with pytest.raises(ValueError, match="Ambiguous"):
        service.inspect_model(str(main))
    assert not service.jobs.root.exists()


@pytest.mark.parametrize("encoding", ["utf-8", "gbk", "utf-16"])
def test_shared_engine_decodes_include_filename_without_changing_bytes(tmp_path, encoding):
    from ls_prepost_mcp.domain.model.deck import KeywordDeck

    main = tmp_path / "main.k"
    content = "*KEYWORD\n*INCLUDE\n节点.k\n*END\n".encode(encoding)
    main.write_bytes(content)
    leaf = tmp_path / "节点.k"
    leaf.write_bytes(b"*NODE\n1,0,0,0\n")
    if encoding == "utf-16":
        with pytest.raises(ValueError, match="cannot be edited without changing bytes"):
            KeywordDeck.load(main)
        return
    loaded = KeywordDeck.load(main)
    assert len(loaded.files) == 2 and loaded.includes[0].name == "节点.k"
    saved = loaded.save_as(tmp_path / "output")
    assert Path(saved["main"]).read_bytes() == content
    assert (Path(saved["main"]).parent / "节点.k").read_bytes() == leaf.read_bytes()
    assert main.read_bytes() == content


def snapshot(tmp_path):
    from ls_prepost_mcp.keyword_staging import stage_keyword_snapshot

    service, main, leaf = setup_case(tmp_path)
    directory, _ = service.jobs.create("snapshot_test", {})
    with service._guard():
        report = service.settings.native_keyword_report(main)
        staged = stage_keyword_snapshot(service.settings, main, directory, report)
    return service, staged, main, leaf


@pytest.mark.parametrize("replacement", ["changed_bytes", "replaced_inode"])
def test_cleanup_keeps_changed_or_replaced_copies_and_unknown_files(tmp_path, replacement):
    _, staged, main, leaf = snapshot(tmp_path)
    before = main.read_bytes(), leaf.read_bytes()
    owned = staged.files[0].path
    unknown = staged.root / "user-file.txt"
    unknown.write_text("not owned by the snapshot", encoding="utf-8")
    if replacement == "changed_bytes":
        owned.write_bytes(b"changed externally")
    else:
        other = staged.root / "replacement.tmp"
        other.write_bytes(owned.read_bytes())
        other.replace(owned)
    result = staged.cleanup()
    assert str(owned) in result["retained"] and owned.exists()
    assert unknown.read_text(encoding="utf-8") == "not owned by the snapshot"
    assert (main.read_bytes(), leaf.read_bytes()) == before


def test_tampered_snapshot_is_not_reported_as_success(tmp_path, monkeypatch):
    service, main, _ = setup_case(tmp_path)

    def execute(executable, cfile, directory, **kwargs):
        request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
        Path(request["model"]).write_bytes(b"changed staged deck")
        (directory / "response.json").write_text(json.dumps({"job_id": directory.name, "ok": True,
                                                            "data": {"counts": {"nodes": 1}}}))
        return JobResult(operation=kwargs["operation"], job_id=directory.name, status="unverified",
                         data={"returncode": 0, "timed_out": False})

    monkeypatch.setattr("ls_prepost_mcp.service.run_batch", execute)
    result = service.inspect_model(str(main))
    assert result["status"] == "failed" and "snapshot changed" in result["error"]["message"]
    assert "cleanup" not in result["input_tree"]


def test_disk_reserve_is_checked_before_copy_or_native_launch(tmp_path, monkeypatch):
    from types import SimpleNamespace

    service, main, _ = setup_case(tmp_path)
    monkeypatch.setattr("ls_prepost_mcp.keyword_staging.shutil.disk_usage", lambda p: SimpleNamespace(free=0))
    monkeypatch.setattr("ls_prepost_mcp.service.run_batch", lambda *a, **kw: pytest.fail("Insufficient-space job launched"))
    result = service.inspect_model(str(main))
    assert result["status"] == "failed" and "Insufficient free disk space" in result["error"]["message"]
    assert not list(service.jobs.root.glob("*/native_*.k"))


def test_continued_filename_is_normalized_without_touching_other_bytes(tmp_path):
    from ls_prepost_mcp.keyword_staging import stage_keyword_snapshot

    service, main, leaf = setup_case(tmp_path)
    sub = main.parent / "sub"
    sub.mkdir()
    (sub / "leaf.k").write_bytes(leaf.read_bytes())
    main.write_bytes(b"$ GBK comment: \xd6\xd0\xce\xc4\r\n*KEYWORD\r\n*INCLUDE\r\nsub/ +\r\nleaf.k\r\n*END")
    directory, _ = service.jobs.create("snapshot_test", {})
    with service._guard():
        staged = stage_keyword_snapshot(service.settings, main, directory, service.settings.native_keyword_report(main))
    data = staged.main.read_bytes()
    assert data.startswith(b"$ GBK comment: \xd6\xd0\xce\xc4\r\n*KEYWORD\r\n*INCLUDE\r\n")
    assert data.endswith(b"\r\n$ normalized filename continuation\r\n*END")
    assert len(preflight_includes(staged.main)["files"]) == 2


def test_bom_prefixed_include_is_preflighted_and_copied_with_bom_intact(tmp_path):
    from ls_prepost_mcp.keyword_staging import stage_keyword_snapshot

    service, main, _ = setup_case(tmp_path)
    main.write_bytes(b"\xef\xbb\xbf*INCLUDE\nnodes.k\n")
    report = preflight_includes(main)
    assert len(report["files"]) == 2 and report["references"][0]["name_line"] == 2
    directory, _ = service.jobs.create("snapshot_test", {})
    with service._guard():
        staged = stage_keyword_snapshot(service.settings, main, directory, service.settings.native_keyword_report(main))
    assert staged.main.read_bytes().startswith(b"\xef\xbb\xbf*INCLUDE\n")


def test_bom_cannot_hide_a_network_include_from_the_guard(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.model.includes import is_network

    main = tmp_path / "main.k"
    main.write_bytes(b"\xef\xbb\xbf*INCLUDE\n\\\\not-a-real-host.invalid\\share\\mesh.k\n")
    original = Path.open

    def guarded(path, *args, **kwargs):
        if is_network(str(path)):
            pytest.fail("Network name reached filesystem access")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    with pytest.raises(ValueError, match="network_path"):
        Settings(tmp_path).native_keyword_report(main)


def test_bom_does_not_hide_indented_include_syntax(tmp_path):
    main = tmp_path / "main.k"
    main.write_bytes(b"\xef\xbb\xbf *INCLUDE\nchild.k\n")
    with pytest.raises(ValueError, match="first column"):
        Settings(tmp_path).native_keyword_report(main)
