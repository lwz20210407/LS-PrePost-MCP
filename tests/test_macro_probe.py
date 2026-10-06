from unittest.mock import Mock

import pytest

from tools.experiments import macro_probe


@pytest.mark.parametrize("lane,file_type,command,filename", [
    ("execution", None, "open keyword", "input.k"),
    ("execution", "d3plot", "openc d3plot", "d3plot"),
    ("png", "d3plot", "openc d3plot", "d3plot"),
    ("mp4", None, "openc d3plot", "d3plot"),
    ("mp4", "keyword", "openc d3plot", "d3plot"),
])
def test_macro_probe_loads_input_before_macro_callback(tmp_path, monkeypatch, lane, file_type, command, filename):
    directory = tmp_path / "cell"
    directory.mkdir()
    (directory / "program.mac").write_text("*macro begin M0Export\nac\n*macro end\n", encoding="utf8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    cell = dict(directory=str(directory), mode="nographics")
    if file_type is not None:
        cell["file_type"] = file_type
    monkeypatch.setattr("ls_prepost_mcp.native_config.isolate_preferences", lambda *args: ({}, {}))
    process = Mock()
    process.poll.return_value = 0
    launch = Mock(return_value=process)
    monkeypatch.setattr(macro_probe.subprocess, "Popen", launch)

    result = macro_probe.run(cell, tmp_path / "lspp.exe", lane, run_dir)

    startup = (run_dir / "start.cfile").read_text(encoding="utf8").splitlines()
    assert startup[0] == command + ' "' + str(tmp_path / "fixture" / filename) + '"'
    assert startup[1].startswith("runscript ")
    macro = (run_dir / "probe.mac").read_text(encoding="utf8")
    assert "openc d3plot" not in macro
    assert "ac\n" in macro
    if lane == "mp4":
        assert "movie MP4/H264" in macro
    assert result["input_type"] == ("d3plot" if filename == "d3plot" else "keyword")
    assert result["source_kind"] == "native_macro"
    launch.assert_called_once()
    process.terminate.assert_not_called()


def test_macro_probe_invalid_input_rejected_before_writing_or_launching(tmp_path, monkeypatch):
    launch = Mock()
    monkeypatch.setattr(macro_probe.subprocess, "Popen", launch)
    with pytest.raises(ValueError, match="input type"):
        macro_probe.run(dict(directory=str(tmp_path), file_type="unknown"),
                        tmp_path / "lspp.exe", "execution", tmp_path)
    launch.assert_not_called()
    assert list(tmp_path.iterdir()) == []
