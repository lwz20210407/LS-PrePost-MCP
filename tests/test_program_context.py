from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ls_prepost_mcp.gui_programs import declared_save_context, execute_prepared
from ls_prepost_mcp.program_bundle import identity


@pytest.mark.parametrize("nodes,language,source,allowed", [
    (0, "cfile", b'meshing boxsolid accept 1 1 1 boxsolid\nsave keyword "mesh.k"', True),
    (8, "cfile", b'save keyword "mesh.k"', False),
    (8, "command", b'save keyword "mesh.k"', True),
    (8, "command", b'save keyword "undeclared.k"', False),
    (8, "command", b'save keyword "mesh.k"; open keyword "other.k"', False),
    (0, "command", b'open keyword "other.k"', False),
    (0, "python", b'print("save keyword")', False),
])
def test_only_empty_creation_or_literal_declared_save_as_can_adopt_context(nodes, language, source, allowed):
    contract = dict(language=language, outputs=[dict(name="mesh.k", kind="keyword")])
    assert declared_save_context(dict(counts=dict(nodes=nodes)), contract, source) is allowed


@pytest.mark.parametrize("scenario,error", [
    ("create", None),
    ("save_as", None),
    ("foreign_source", "Native active model does not match"),
    ("missing_output", "Missing or empty artifact"),
    ("invalid_output", "Invalid keyword artifact"),
    ("multiple_outputs", "Program replaced the current model context"),
    ("wrong_counts", "Native counts differ"),
    ("result_session", "Program replaced the current model context"),
    ("nonempty_cfile", "Program replaced the current model context"),
])
def test_context_adoption_requires_owned_output_and_native_readback(tmp_path, scenario, error):
    """Exercise the execution boundary with real artifact and source checks."""
    directory = tmp_path / "execution"
    directory.mkdir()
    old_source = str(tmp_path / "original" / "model.k")
    nodes = 8 if scenario in ("save_as", "nonempty_cfile") else 0
    meta = dict(model_kind="d3plot" if scenario == "result_session" else "keyword",
                process={}, process_alive=True, staged_model=old_source, source=old_source,
                state="ready")
    manager = Mock()
    manager.lock.return_value = nullcontext()
    manager.read.side_effect = lambda sid: meta.copy()
    manager.directory.return_value = tmp_path
    manager.save.side_effect = lambda sid, value: meta.update(value)
    source = b'save keyword "mesh.k"'
    contract = dict(language="command" if scenario == "save_as" else "cfile",
                    program="program.cfile", outputs=[dict(name="mesh.k", kind="keyword")],
                    expected_counts=dict(nodes=8))
    if scenario == "multiple_outputs":
        contract["outputs"].append(dict(name="another.k", kind="keyword"))

    def dispatch(sid, action, parameters, **kwargs):
        if action == "export_keyword":
            return dict(status="succeeded", artifacts=[dict(path=old_source)])
        if not kwargs.get("native_commands"):
            return dict(status="succeeded", data=dict(model_directory=old_source,
                                                       counts=dict(nodes=nodes, states=1)))
        if scenario != "missing_output":
            (directory / "mesh.k").write_text(
                "invalid" if scenario == "invalid_output" else "*KEYWORD\n*END\n", encoding="utf8")
        observed = str(tmp_path / "foreign" / "other.k") if scenario == "foreign_source" else str(directory / "mesh.k")
        return dict(status="succeeded", data=dict(model_directory=observed,
                                                   counts=dict(nodes=9 if scenario == "wrong_counts" else 8, states=1)))

    manager.dispatch.side_effect = dispatch
    service = SimpleNamespace(_session_manager=lambda: manager,
                              _visible_mesh_session=lambda *args, **kwargs: meta.copy(),
                              jobs=SimpleNamespace(create=lambda *args: (directory, {})))
    result = execute_prepared(service, "session", "prepared", identity(source, contract),
                              contract, source, [])
    if error:
        assert result["status"] == "failed"
        assert error in result["error"]["message"]
        assert result["artifacts"] == []
        assert meta["staged_model"] == old_source
        assert meta["state"] == "uncertain"
    else:
        assert result["status"] == "succeeded"
        assert result["artifacts"][0]["validated"] is True
        assert meta["staged_model"] == str(directory / "mesh.k")
        assert meta["last_checkpoint"] == str(directory / "mesh.k")
    manager.journal.assert_called_once()
