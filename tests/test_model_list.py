import pytest

from ls_prepost_mcp.windows_model_list import active_model_candidate, parse_model_rows


def test_display_numbers_are_not_command_positions_after_removal():
    rows = parse_model_rows([["2-Second", "F:/jobs/a/model.k"], ["7-Seventh", "F:/jobs/b/d3plot"]])
    assert [r["display_number"] for r in rows] == [2, 7]
    assert [r["row_index"] for r in rows] == [1, 2]
    assert active_model_candidate(rows, "f:\\jobs\\b\\") == 2
    assert active_model_candidate(rows, "F:/jobs/a/model.k") == 1


@pytest.mark.parametrize("rows", [[[None, "file"]], [["", "file"]], [["1-One", "a", "extra"]], [["1-One"]]])
def test_ambiguous_native_rows_are_not_silently_accepted(rows):
    with pytest.raises(ValueError):
        parse_model_rows(rows)


def test_unknown_or_duplicate_source_does_not_invent_an_active_model():
    rows = parse_model_rows([["1-A", "F:/same/model.k"], ["2-B", "F:/same/model.k"], ["3-Unsaved", ""]])
    assert rows[-1]["path"] is None
    assert active_model_candidate(rows, "F:/same/model.k") is None
    assert active_model_candidate(rows, "relative.k") is None
    assert active_model_candidate(rows, "F:/different/model.k") is None


def test_model_titles_keep_unicode_and_embedded_hyphens():
    rows = parse_model_rows([["12-材料-模型", "F:/模型.k"]])
    assert rows[0]["title"] == "材料-模型"


def test_display_prefix_is_not_used_as_unique_identity():
    rows = parse_model_rows([["3-A", "F:/a.k"], ["3-B", "F:/b.k"], ["No prefix", ""]])
    assert active_model_candidate(rows, "F:/b.k") == 2
    assert rows[-1]["display_number"] is None
