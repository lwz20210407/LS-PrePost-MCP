"""Offline contracts only: no native process or network is used."""

import json

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.native import versions
from ls_prepost_mcp.service import Service


def service_for(tmp_path, monkeypatch, version="4.13.0.1"):
    exe = tmp_path / "fake.exe"
    exe.touch()
    monkeypatch.setattr(versions, "read_version_resource", lambda _: dict(
        file_version=version, product_version=version, fixed_file_version=version,
        product_name="LS-PrePost"))
    return Service(Settings(tmp_path, exe))


def dependency(tmp_path, name="数据.txt", content=b"original bytes\n"):
    source = tmp_path / "中文源文件.txt"
    source.write_bytes(content)
    return dict(path=str(source), name=name)


@pytest.mark.parametrize("version,command", [
    ("4.13.0.1", "import keyword"), ("4.10.0.1", "import keyword"),
    ("4.13.0.1", "open xydata"), ("4.10.0.1", "open xydata"),
    ("4.10.0.1", "runscript"),
])
def test_known_failure_rejected_before_prepare_writes(tmp_path, monkeypatch, version, command):
    service = service_for(tmp_path, monkeypatch, version)
    dep = dependency(tmp_path)
    with pytest.raises(ValueError, match="ASCII bundle"):
        service.prepare_native_program("cfile", code=f'{command} "数据.txt"', dependencies=[dep])
    assert not service.jobs.root.exists()
    assert (tmp_path / "中文源文件.txt").read_bytes() == b"original bytes\n"


@pytest.mark.parametrize("session_id", [None, "owned-session"])
def test_legacy_contract_rechecked_before_any_dispatch(tmp_path, monkeypatch, session_id):
    service = service_for(tmp_path, monkeypatch)
    dep = dependency(tmp_path)
    # Construct an old-format bundle through the existing API without the new
    # reference guard. The unchanged identity is still valid and user-reviewed.
    with monkeypatch.context() as legacy:
        legacy.setattr("ls_prepost_mcp.programs.validate_script_references", lambda *a, **k: {})
        prepared = service.prepare_native_program("cfile", code='open xydata "数据.txt"', dependencies=[dep])
    before = set(service.jobs.root.iterdir())
    monkeypatch.setattr("ls_prepost_mcp.programs.run_batch", lambda *a, **k: pytest.fail("batch dispatch"))
    monkeypatch.setattr("ls_prepost_mcp.gui_programs.execute_prepared", lambda *a, **k: pytest.fail("session dispatch"))

    class Manager:
        def read(self, sid):
            assert sid == session_id
            return {"executable": {"path": str(service.settings.executable)}}

    monkeypatch.setattr(service, "_session_manager", lambda: Manager())
    with pytest.raises(ValueError, match="ASCII bundle"):
        service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"], session_id=session_id)
    assert set(service.jobs.root.iterdir()) == before
    assert json.loads((service.jobs.root / prepared["job_id"] / "contract.json").read_text(encoding="utf8"))["sha256"] == prepared["data"]["sha256"]


@pytest.mark.parametrize("command", ["import keyword", "open xydata", "runscript"])
@pytest.mark.parametrize("name", ["input.txt", "input data.txt"])
def test_explicit_ascii_alias_preserves_bytes_and_execution_identity(tmp_path, monkeypatch, command, name):
    service = service_for(tmp_path, monkeypatch, "4.10.0.1")
    content = "/* 中文注释 */\r\noriginal\n".encode()
    dep = dependency(tmp_path, name, content)
    code = f'{command} "{name}"'
    if command == "open xydata":
        code += f'\nshow "{name}~1" 0'
    prepared = service.prepare_native_program("cfile", code=code, dependencies=[dep], expected_counts={"nodes": 8})
    folder = service.jobs.root / prepared["job_id"]
    assert (folder / name).read_bytes() == content
    # A frozen dependency intentionally survives later source-file changes.
    (tmp_path / "中文源文件.txt").write_bytes(b"later source")
    calls = []

    def execute(executable, cfile, directory, **kwargs):
        calls.append(directory)
        assert (directory / name).read_bytes() == content
        assert code in cfile.read_text(encoding="utf8")
        (directory / "complete.txt").write_text("8 1 1")
        return JobResult(operation=kwargs["operation"], job_id=directory.name, status="unverified",
                         data=dict(returncode=0, timed_out=False))

    monkeypatch.setattr("ls_prepost_mcp.programs.run_batch", execute)
    result = service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"])
    assert result["status"] == "succeeded"
    assert result["data"]["bundle_sha256"] == prepared["data"]["sha256"]
    assert result["job_id"] == calls[0].name and calls[0] != folder
    assert (tmp_path / "中文源文件.txt").read_bytes() == b"later source"


def test_observed_scl_reader_preserves_unicode_and_does_not_infer_extension(tmp_path, monkeypatch):
    service = service_for(tmp_path, monkeypatch)
    dep = dependency(tmp_path, "节点 计数.txt", "/* 中文 */\n".encode())
    prepared = service.prepare_native_program("cfile", code='runscript "节点 计数.txt"', dependencies=[dep])
    assert (service.jobs.root / prepared["job_id"] / dep["name"]).read_bytes() == "/* 中文 */\n".encode()


@pytest.mark.parametrize("command", ["import keyword", "open xydata", "runscript"])
@pytest.mark.parametrize("version", ["4.13.9.9", "4.8.0.1", None])
def test_unknown_build_is_unverified_not_observed_failure(tmp_path, monkeypatch, command, version):
    service = service_for(tmp_path, monkeypatch, version)
    dep = dependency(tmp_path)
    with pytest.raises(ValueError, match="unverified build/operation"):
        service.prepare_native_program("cfile", code=f'{command} "数据.txt"', dependencies=[dep])
    assert not service.jobs.root.exists()


def test_path_hint_cannot_enable_scl_unicode(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path, tmp_path / "lsprepost4.13.exe"))
    monkeypatch.setattr(versions, "read_version_resource", lambda _: None)
    with pytest.raises(ValueError, match="unverified"):
        service.prepare_native_program("cfile", code='runscript "数据.txt"', dependencies=[dependency(tmp_path)])


@pytest.mark.parametrize("language,code", [
    ("python", 'print("中文内容")'), ("scl", '/* 中文内容 */'),
    ("cfile", '$ import keyword "数据.txt"\n# open xydata "数据.txt"\nc runscript "数据.txt"\ntop'),
    ("cfile", 'runpython "数据.txt"'),
    ("cfile", 'open xydata "C:/外部/数据.txt"'),
    ("cfile", 'import keyword "/外部/数据.txt"'),
])
def test_unrelated_unicode_content_and_absolute_reader_paths_not_restricted(tmp_path, language, code):
    service = Service(Settings(tmp_path))
    prepared = service.prepare_native_program(language, code=code, dependencies=[dependency(tmp_path)])
    assert prepared["status"] == "prepared"


@pytest.mark.parametrize("target", ['"数据.txt"', '数据.txt', '"./数据.txt"', '"DATA/数据.txt"'])
def test_nested_semicolon_reader_cannot_bypass_policy(tmp_path, monkeypatch, target):
    service = service_for(tmp_path, monkeypatch)
    child = tmp_path / "child.txt"
    child.write_text(f'top; OPEN   XYDATA {target}; bottom', encoding="utf8")
    with pytest.raises(ValueError, match="ASCII bundle"):
        service.prepare_native_program("cfile", code='openc command "child.txt" nodialog',
            dependencies=[dependency(tmp_path), dict(path=str(child), name="child.txt")])
    assert not service.jobs.root.exists()


def test_reader_without_manifest_cannot_bypass_policy(tmp_path, monkeypatch):
    service = service_for(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="ASCII bundle"):
        service.prepare_native_program("command", code='import keyword "数据.k"')


@pytest.mark.parametrize("names", [["same.txt", "SAME.TXT"], ["../escape.txt"], ["目录", "目录/a.txt"]])
def test_existing_bundle_collision_and_traversal_contracts_remain(tmp_path, names):
    service = Service(Settings(tmp_path))
    deps = [dependency(tmp_path, name) for name in names]
    with pytest.raises(ValueError):
        service.prepare_native_program("cfile", code="top", dependencies=deps)
    assert not service.jobs.root.exists()


@pytest.mark.parametrize("tamper", ["program", "dependency", "manifest"])
def test_identity_tampering_fails_before_filename_policy_or_execution(tmp_path, monkeypatch, tamper):
    service = service_for(tmp_path, monkeypatch)
    prepared = service.prepare_native_program("cfile", code='runscript "数据.txt"', dependencies=[dependency(tmp_path)])
    folder = service.jobs.root / prepared["job_id"]
    if tamper == "manifest":
        contract = json.loads((folder / "contract.json").read_text(encoding="utf8"))
        contract["dependencies"] = []
        (folder / "contract.json").write_text(json.dumps(contract), encoding="utf8")
    else:
        (folder / ("program.cfile" if tamper == "program" else "数据.txt")).write_text("changed")
    before = set(service.jobs.root.iterdir())
    monkeypatch.setattr("ls_prepost_mcp.programs.run_batch", lambda *a, **k: pytest.fail("dispatch"))
    with pytest.raises(ValueError, match="changed"):
        service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"])
    assert set(service.jobs.root.iterdir()) == before


def test_session_uses_its_executable_not_prepare_default(tmp_path, monkeypatch):
    service = service_for(tmp_path, monkeypatch)
    prepared = service.prepare_native_program("cfile", code='runscript "数据.txt"', dependencies=[dependency(tmp_path)])
    session_exe = tmp_path / "session410.exe"
    monkeypatch.setattr(versions, "read_version_resource", lambda exe: dict(
        file_version="4.10.0.1" if str(exe) == str(session_exe) else "4.13.0.1", product_name="LS-PrePost"))

    class Manager:
        def read(self, sid):
            assert sid == "owned"
            return {"executable": {"path": str(session_exe)}}

    monkeypatch.setattr(service, "_session_manager", lambda: Manager())
    monkeypatch.setattr("ls_prepost_mcp.gui_programs.execute_prepared", lambda *a, **k: pytest.fail("dispatch"))
    with pytest.raises(ValueError, match="observed failure"):
        service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"], session_id="owned")


@pytest.mark.parametrize("artifact", ["missing", "invalid-json", "symlink"])
def test_ascii_alias_does_not_weaken_artifact_checks(tmp_path, monkeypatch, artifact):
    service = service_for(tmp_path, monkeypatch)
    prepared = service.prepare_native_program("cfile", code='open xydata "input.txt"',
        dependencies=[dependency(tmp_path, "input.txt")], outputs=[dict(name="result.json", kind="json")])
    foreign = tmp_path / "foreign.json"
    foreign.write_text('{"valid":true}')
    if artifact == "symlink":
        try:
            (tmp_path / "probe-link").symlink_to(foreign)
        except OSError:
            pytest.skip("Symlink creation unavailable")

    def execute(executable, cfile, directory, **kwargs):
        (directory / "complete.txt").write_text("8 1 1")
        if artifact == "invalid-json":
            (directory / "result.json").write_text("invalid")
        elif artifact == "symlink":
            (directory / "result.json").symlink_to(foreign)
        return JobResult(operation=kwargs["operation"], job_id=directory.name, status="unverified",
                         data=dict(returncode=0, timed_out=False))

    monkeypatch.setattr("ls_prepost_mcp.programs.run_batch", execute)
    result = service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"])
    assert result["status"] == "failed"
