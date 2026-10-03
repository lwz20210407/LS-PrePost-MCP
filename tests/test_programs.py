import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.programs import gui_command, native_errors, output_contract
from ls_prepost_mcp.service import Service


def test_preparation_numeric_macro_and_source_identity(tmp_path):
    s = Service(Settings(tmp_path))
    p = s.prepare_native_program(
        "cfile", code="meshing boxsolid create 0 0 0 {{width}} 2 2 1 1 1 0", parameters={"width": 5}
    )
    assert p["status"] == "prepared" and "0 0 0 5 2 2" in p["data"]["rendered_source"]
    with pytest.raises(ValueError, match="finite named numbers"):
        s.prepare_native_program("python", code="print({{width}})", parameters={"width": '__import__("os")'})
    with pytest.raises(ValueError, match="Missing"):
        s.prepare_native_program("scl", code="Int n={{missing}};")
    Path(p["artifacts"][0]["path"]).write_text("modified")
    with pytest.raises(ValueError, match="changed"):
        s.execute_native_program(p["job_id"], p["data"]["sha256"])


@pytest.mark.parametrize(
    "name", ["../outside.k", "program.py", "complete.txt", "NUL.txt", "model.k.", "a/b.k", "a:b.k"]
)
def test_output_contract_rejects_escape_reserved_and_windows_aliases(name):
    with pytest.raises(ValueError):
        output_contract([dict(name=name, kind="keyword")])


def test_gui_raw_lifecycle_and_script_commands_have_dedicated_routes():
    for code in [
        "new",
        "exit",
        "runpython a.py",
        "runscript a.scl",
        "system something",
        "open keyword a.k",
        "top\nbottom",
    ]:
        with pytest.raises(ValueError):
            gui_command(code)
    assert gui_command('save keyword "new_model.k"')


@pytest.mark.parametrize(
    "scenario, expected",
    [
        ("no_contract", "completed_unverified"),
        ("counts", "succeeded"),
        ("mismatch", "failed"),
        ("native_error", "failed"),
        ("missing_marker", "failed"),
        ("python_error", "failed"),
        ("bad_json", "failed"),
    ],
)
def test_program_execution_completion_and_artifact_contracts(tmp_path, monkeypatch, scenario, expected):
    exe = tmp_path / "native.exe"
    exe.write_bytes(b"test executable identity only")
    s = Service(Settings(tmp_path, exe))
    language = "python" if scenario == "python_error" else "cfile"
    outputs = [dict(name="result.json", kind="json")] if scenario == "bad_json" else None
    counts = None if scenario == "no_contract" else {"nodes": 999 if scenario == "mismatch" else 8}
    p = s.prepare_native_program(language, code="test source", outputs=outputs, expected_counts=counts)

    def fake_execute(executable, cfile, directory, **kwargs):
        if scenario != "missing_marker":
            (directory / "complete.txt").write_text("8 1 1")
        if scenario == "native_error":
            (directory / "lspost.msg").write_text("Invalid command test_source!\n")
        if scenario == "python_error":
            (directory / "python-result.json").write_text(
                json.dumps(dict(ok=False, error="intentional failure"))
            )
        if scenario == "bad_json":
            (directory / "result.json").write_text("not json")
        return dict(returncode=0, timed_out=False)

    monkeypatch.setattr("ls_prepost_mcp.programs.execute", fake_execute)
    result = s.execute_native_program(p["job_id"], p["data"]["sha256"])
    assert result["status"] == expected


def test_native_error_detection_excludes_success_message():
    assert not native_errors("Script file program.scl parsed. no error found")
    assert native_errors("Invalid measure command!")
    assert not native_errors("Invalid solid elements accounted for 2%")
    assert (
        len(
            native_errors(
                " *** Error while compiling function definition\nerror occurred in parsing script : -8\nInvalid command x!"
            )
        )
        == 3
    )


def test_macro_override_is_typed_and_definition_survives(tmp_path, monkeypatch):
    s = Service(Settings(tmp_path))
    macro = s.create_native_macro("width", "cfile", "mesh {{width}}", {"width": 2})
    path = macro["artifacts"][0]["path"]
    original = Path(path).read_bytes()
    with pytest.raises(ValueError, match="Unknown"):
        s.run_native_macro(path, {"other": 3})
    seen = []

    def execute(prepared_job_id, expected_sha256, *args):
        prepared = s.jobs.get(prepared_job_id)
        seen.append(prepared["data"]["rendered_source"])
        directory, result = s.jobs.create("fake_execution", {})
        result.update(status="completed_unverified", job_directory=str(directory))
        return result

    monkeypatch.setattr(s, "execute_native_program", execute)
    s.run_native_macro(path, {"width": 5})
    assert seen == ["mesh 5"] and Path(path).read_bytes() == original


def test_program_preparation_and_execution_compose_as_typed_workflow(tmp_path, monkeypatch):
    s = Service(Settings(tmp_path))
    seen = []

    def execute(prepared_job_id, expected_sha256):
        prepared = s.jobs.get(prepared_job_id)
        assert expected_sha256 == prepared["data"]["sha256"]
        seen.append(prepared["data"]["rendered_source"])
        return dict(status="succeeded")

    monkeypatch.setattr(s, "execute_native_program", execute)
    definition = s.create_workflow(
        "native program chain",
        [
            dict(
                id="prepare",
                action="prepare_native_program",
                arguments=dict(
                    language="command", code="rotang {{angle}}", parameters={"angle": {"$param": "angle"}}
                ),
            ),
            dict(
                id="execute",
                action="execute_native_program",
                arguments=dict(
                    prepared_job_id={"$result": "prepare", "path": ["job_id"]},
                    expected_sha256={"$result": "prepare", "path": ["data", "sha256"]},
                ),
            ),
        ],
        defaults={"angle": 90},
    )
    result = s.run_workflow(definition["artifacts"][0]["path"])
    assert result["status"] == "succeeded" and seen == ["rotang 90"]
