"""I03: generated SCL must preserve UTF-8 paths, not unsupported JSON u-escapes."""

import json

import pytest

from ls_prepost_mcp import native_results
from ls_prepost_mcp.native import commands as nc
from tests.test_native_binout import service_and_source


@pytest.mark.parametrize("path,expected", [
    (r"C:\jobs\native.csv", '"C:/jobs/native.csv"'),
    (r"C:\中文 空格\native.csv", '"C:/中文 空格/native.csv"'),
    ('folder/quote"name;value.csv', '"folder/quote\\"name;value.csv"'),
])
def test_scl_path_literal(path, expected):
    assert nc.scl_string(path) == expected
    assert json.loads(nc.scl_string(path)) == path.replace("\\", "/")


def test_binout_native_separators_are_escaped_without_unicode_escapes():
    path = r"C:\中文 空格\input_data"
    assert nc.scl_string(path, style="native") == '"C:\\\\中文 空格\\\\input_data"'
    assert json.loads(nc.scl_string(path, style="native")) == path


def test_binout_input_and_output_paths_preserve_chinese(tmp_path):
    directory = tmp_path / "中文 空格"
    directory.mkdir()
    service, source = service_and_source(directory)

    def executor(job, manifest):
        script = (job / "binout.scl").read_text(encoding="utf8")
        assert 'SCLBinoutOpen(' + nc.scl_string(job / "input_data", style="native") + ')' in script
        assert 'fopen(' + nc.scl_string(job / "native.csv") + ',"w")' in script
        assert "中文 空格" in script and r"\u4e2d" not in script
        (job / "native.csv").write_text("time,value\n0,0\n1,2\n")

    result = native_results.native_binout(service.settings, service.jobs, source,
                                          "glstat", "internal_energy", None, "raw", executor=executor)
    assert result["status"] == "succeeded", result


def test_field_and_gui_scl_paths_share_literal_builder(monkeypatch):
    from ls_prepost_mcp import gui_fringe

    seen = []

    def literal(path):
        seen.append(path)
        return '"central-literal"'

    monkeypatch.setattr(nc, "scl_string", literal)
    script = native_results.field_script("solid", [1], [1], ["stress_x"], "1", "field.csv")
    assert script.count('fopen("central-literal"') == 2
    assert gui_fringe.scl_string("gui.csv") == '"central-literal"'
    assert seen == ["field.csv", "field.csv", "gui.csv"]
