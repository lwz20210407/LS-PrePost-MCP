import json
import runpy
import sys

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.program_bundle import python_wrapper
from ls_prepost_mcp.service import Service


@pytest.mark.parametrize("name", ["../helper.py", "/helper.py", "pkg//helper.py", "pkg/../helper.py",
                                 "C:/helper.py", "NUL/data.py", "lib/file.py.", "contract.json", "tmp/a.py"])
def test_bundle_rejects_escape_and_control_file_collisions(tmp_path, name):
    file = tmp_path / "source.py"
    file.write_text("VALUE=1")
    with pytest.raises(ValueError):
        Service(Settings(tmp_path)).prepare_native_program("python", code="pass",
            dependencies=[dict(path=str(file), name=name)])
    assert not (tmp_path / "jobs").exists()


def test_dependency_tamper_fails_before_native_launch(tmp_path):
    helper = tmp_path / "helper-source.py"
    helper.write_text("VALUE=3")
    service = Service(Settings(tmp_path))
    prepared = service.prepare_native_program("python", code="import helper",
        dependencies=[dict(path=str(helper), name="helper.py")])
    assert prepared["data"]["sha256"] != prepared["data"]["source_sha256"]
    (service.jobs.root / prepared["job_id"] / "helper.py").write_text("VALUE=4")
    with pytest.raises(ValueError, match="Dependency changed"):
        service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"])


def test_literal_child_scripts_must_exist_and_must_not_cycle(tmp_path):
    service = Service(Settings(tmp_path))
    with pytest.raises(ValueError, match="not declared"):
        service.prepare_native_program("cfile", code='openc command "missing.cfile" nodialog')
    helper = tmp_path / "child.cfile"
    helper.write_text('openc command "program.cfile" nodialog')
    with pytest.raises(ValueError, match="Cyclic"):
        service.prepare_native_program("cfile", code='openc command "lib/child.cfile" nodialog',
            dependencies=[dict(path=str(helper), name="lib/child.cfile")])


def test_nested_command_reference_is_checked_without_relying_on_extension(tmp_path):
    child = tmp_path / "child.txt"
    child.write_text('top; openc command "missing.cfile" nodialog')
    with pytest.raises(ValueError, match="missing.cfile"):
        Service(Settings(tmp_path)).prepare_native_program("cfile", code='openc command "lib/child.txt" nodialog',
            dependencies=[dict(path=str(child), name="lib/child.txt")])


def test_dependency_rewrite_is_not_success_despite_completion_marker(tmp_path, monkeypatch):
    helper = tmp_path / "helper-source.py"
    helper.write_text("VALUE=3")
    exe = tmp_path / "fake.exe"
    exe.touch()
    service = Service(Settings(tmp_path, exe))
    prepared = service.prepare_native_program("cfile", code="top", expected_counts={"nodes":8},
        dependencies=[dict(path=str(helper), name="helper.py")])

    def execute(executable, command, directory, **kwargs):
        (directory / "helper.py").write_text("VALUE=9")
        (directory / "complete.txt").write_text("8 1 1")
        return dict(returncode=0, timed_out=False)

    monkeypatch.setattr("ls_prepost_mcp.programs.execute", execute)
    result = service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"])
    assert result["status"] == "failed" and "Dependency changed" in result["error"]["message"]
    assert helper.read_text() == "VALUE=3"


def test_empty_package_init_and_frozen_macro_dependencies(tmp_path):
    service = Service(Settings(tmp_path))
    helper = tmp_path / "helper.py"
    helper.write_text("VALUE=7")
    init = tmp_path / "empty.py"
    init.touch()
    macro = service.create_native_macro("bundle", "python", "pass", {}, dependencies=[
        dict(path=str(helper), name="pkg/helper.py"), dict(path=str(init), name="pkg/__init__.py")])
    folder = service.jobs.root / macro["job_id"]
    helper.write_text("VALUE=99")
    assert (folder / "assets/pkg/helper.py").read_text() == "VALUE=7"
    assert (folder / "assets/pkg/__init__.py").read_bytes() == b""


def test_python_wrapper_does_not_reuse_a_previous_bundle_module(tmp_path):
    original_path = list(sys.path)
    for value in (7,19):
        folder = tmp_path / "NAMES" / str(value)
        folder.mkdir(parents=True)
        (folder / "bundle_test_helper.py").write_text("VALUE="+str(value))
        (folder / "program.py").write_text('import bundle_test_helper,json\njson.dump(bundle_test_helper.VALUE,open("value.json","w"))')
        wrapper = folder / "bootstrap.py"
        wrapper.write_text(python_wrapper(folder, ["bundle_test_helper.py"]))
        runpy.run_path(str(wrapper))
        assert json.loads((folder / "value.json").read_text()) == value
        assert "bundle_test_helper" not in sys.modules and sys.path == original_path
