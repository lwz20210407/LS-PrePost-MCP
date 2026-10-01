import pytest

from ls_prepost_mcp.recording_compiler import compile_commands
from ls_prepost_mcp.workflows import resolve


def test_recorded_model_ids_require_explicit_scope_and_never_silently_drop_suffix():
    text = "genselect clear\ngenselect target node\ngenselect node add node 12/2\ntranslate_model 1 0 0\ntranslate_model accept"
    assert compile_commands(text, "mm")["unrecognized_commands"]
    result = compile_commands(text, "mm", 2)
    assert not result["unrecognized_commands"]
    assert result["steps"][-1]["action"] == "translate_gui_nodes"
    assert result["steps"][-1]["arguments"]["node_ids"] == [12]
    assert compile_commands(text + "\ngenselect node add node 13/3", "mm", 2)["unrecognized_commands"]
    with pytest.raises(ValueError):
        compile_commands(text, "mm", True)


def test_whole_selection_and_buffer_load_use_verified_runtime_ids_for_translation():
    result = compile_commands(
        "genselect clear\ngenselect target node\ngenselect whole\ngenselect save 2\ngenselect clear\ngenselect load 2\ntranslate_model 1 0 0\ntranslate_model accept",
        "mm",
    )
    assert not result["unrecognized_commands"]
    saved = next(step for step in result["steps"] if step["action"] == "save_gui_selection_buffer")
    loaded = next(step for step in result["steps"] if step["action"] == "load_gui_selection_buffer")
    assert saved["arguments"]["slot"] == 3
    binding = result["steps"][-1]["arguments"]["node_ids"]
    assert binding["$result"] == loaded["id"]
    assert resolve(binding, {}, {loaded["id"]: {"verification": {"selected_ids": [10, 20]}}}) == [10, 20]


def test_unknown_or_uncleared_buffer_and_unknown_selection_are_review_blockers():
    for body in [
        "genselect target node\ngenselect whole",
        "genselect clear\ngenselect target node\ngenselect load 9",
        "genselect clear\ngenselect target node\ngenselect node add node 1\ngenselect save 2\ngenselect load 2",
    ]:
        assert compile_commands(body, "mm")["unrecognized_commands"]


def test_partial_normal_and_native_quality_recording_compile_to_typed_actions():
    result = compile_commands(
        "genselect clear\ngenselect target shell\ngenselect shell add shell 42\nnormal reverse\nelemcheck shell init\nelemcheck shell aratio 5",
        "mm",
    )
    assert not result["unrecognized_commands"]
    normal, quality = result["steps"][-2:]
    assert normal["arguments"]["shell_ids"] == [42]
    assert quality["action"] == "check_gui_shell_quality"
    assert quality["arguments"]["thresholds"] == {"aspect_ratio": 5}
