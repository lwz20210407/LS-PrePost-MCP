"""Review02 P0-1: distinguish user IDs from native internal title ordinals."""

import numpy as np
import pytest

from ls_prepost_mcp.domain.results import lasso_backend as lb


@pytest.mark.parametrize(
    "part_ids,title_ids,titles,expected",
    [
        (
            [6, 9, 8, 10],
            [1, 2, 3, 4],
            ["fabric top", "head / nut", "fabric bottom", "shank"],
            {6: "fabric top", 9: "head / nut", 8: "fabric bottom", 10: "shank"},
        ),
        (
            [10, 20, 100],
            [1, 2, 3],
            ["part ten", "part twenty", "part hundred"],
            {10: "part ten", 20: "part twenty", 100: "part hundred"},
        ),
        (
            [2, 1, 3],
            [1, 2, 3],
            ["internal first", "internal second", "internal third"],
            {2: "internal first", 1: "internal second", 3: "internal third"},
        ),
        ([10, 20], [20, 10], ["part twenty", "part ten"], {20: "part twenty", 10: "part ten"}),
    ],
)
def test_title_id_space_is_resolved_before_associating_names(part_ids, title_ids, titles, expected):
    mapping, warnings = lb._part_titles(
        {
            "part_ids": np.array(part_ids),
            "part_titles_ids": np.array(title_ids),
            "part_titles": np.array(titles),
        }
    )
    assert mapping == expected
    assert not warnings


@pytest.mark.parametrize(
    "title_ids,titles",
    [
        ([20, 10], ["twenty", "ten"]),
        ([1, 1, 2], ["a", "b", "c"]),
        ([1, 2], ["a"]),
        ([1.5, 2, 3], ["a", "b", "c"]),
    ],
)
def test_ambiguous_or_malformed_titles_are_null_with_warning_not_wrong_or_fatal(title_ids, titles):
    mapping, warnings = lb._part_titles(
        {
            "part_ids": np.array([10, 20, 30]),
            "part_titles_ids": np.array(title_ids),
            "part_titles": np.array(titles),
        }
    )
    assert mapping == {} and warnings


def test_title_only_ids_must_not_silently_drive_part_filter_or_history():
    arrays = {"part_titles_ids": np.array([1, 2]), "part_titles": np.array(["six", "nine"])}
    with pytest.raises(lb.ResultsError, match="unconfirmed"):
        lb._part_ids(arrays)


def test_title_mapping_provenance_is_in_overview(tmp_path, monkeypatch):
    arrays = {
        "timesteps": np.array([0.0, 1.0]),
        "part_ids": np.array([6, 9]),
        "part_titles_ids": np.array([1, 2]),
        "part_titles": np.array(["fabric top", "head / nut"]),
    }
    monkeypatch.setattr(lb, "_arrays", lambda *args, **kwargs: arrays)
    result = lb.overview(tmp_path / "d3plot")
    assert result["part_title_mapping"] == "internal_ordinal"
    assert result["part_id_scope"] == "stored_user_ids"


def test_title_only_overview_is_explicitly_unconfirmed(tmp_path, monkeypatch):
    arrays = {
        "timesteps": np.array([0.0, 1.0]),
        "part_titles_ids": np.array([1, 2]),
        "part_titles": np.array(["fabric top", "head / nut"]),
    }
    monkeypatch.setattr(lb, "_arrays", lambda *args, **kwargs: arrays)
    result = lb.overview(tmp_path / "d3plot")
    assert result["part_id_scope"] == "unconfirmed_title_ids" and result["warnings"]
    assert all(p["title"] is None for p in result["parts"])


def test_public_overview_exposes_unconfirmed_namespace_as_partial(tmp_path, monkeypatch):
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.service import Service

    source = tmp_path / "d3plot"
    source.write_bytes(b"controlled metadata input")
    arrays = {
        "timesteps": np.array([0.0, 1.0]),
        "part_titles_ids": np.array([1, 2]),
        "part_titles": np.array(["first", "second"]),
    }
    monkeypatch.setattr(lb, "_arrays", lambda *args, **kwargs: arrays)
    monkeypatch.setattr(
        lb, "header", lambda *args: {"neiph_solid": 0, "neips_shell_tshell": 0, "neipb_beam": 0}
    )
    result = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,))).result_info(str(source))
    assert result["status"] == "partial" and result["warnings"]
    assert result["data"]["part_id_scope"] == "unconfirmed_title_ids"
    assert all(row["title"] is None for row in result["data"]["parts"])
