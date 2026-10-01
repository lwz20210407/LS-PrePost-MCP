import copy

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.gui_quality import native_metric_row
from ls_prepost_mcp.service import Service


def rows():
    def row(cid, label, cls):
        return dict(control_id=cid, text=label, class_name=cls, parent=4, visible=True)

    return [
        row(10701, "Aspect ratio", "Button"),
        row(10702, "10", "Edit"),
        row(5105, "2", "Static"),
        row(5105, "2", "Static"),
        row(5105, "2(100%)", "Static"),
        row(10703, "Warpage", "Button"),
        row(10704, "15", "Edit"),
        row(5105, "0", "Static"),
    ]


def test_native_quality_uses_result_cells_and_actual_command_threshold():
    report = native_metric_row(rows(), "aspect_ratio", 1.5)
    assert report["violated_count"] == 2 and report["violated_percent"] == 100
    assert report["minimum"] == report["maximum"] == 2
    assert report["threshold"] == 1.5
    assert report["raw_display"] == ["2", "2", "2(100%)"]


@pytest.mark.parametrize("value", ["***", "NaN", "inf"])
def test_native_quality_rejects_uncomputed_or_nonfinite_statistics(value):
    data = rows()
    data[2]["text"] = value
    with pytest.raises(ValueError):
        native_metric_row(data, "aspect_ratio", 10)


def test_native_quality_rejects_ambiguous_identity_and_invalid_percent():
    data = rows()
    data.append(copy.deepcopy(data[0]))
    with pytest.raises(ValueError, match="ambiguous"):
        native_metric_row(data, "aspect_ratio", 10)
    data = rows()
    data[4]["text"] = "2(101%)"
    with pytest.raises(ValueError, match="percentage"):
        native_metric_row(data, "aspect_ratio", 10)


def test_quality_threshold_preflight_and_menu_filter_input(tmp_path):
    service = Service(Settings(tmp_path))
    for thresholds in (
        {},
        {"unknown": 1},
        {"warpage": 181},
        {"area": -1},
        {"skew": True},
        {"jacobian": float("nan")},
    ):
        with pytest.raises(ValueError):
            service.check_gui_shell_quality("no-session-needed", thresholds, "mm")
    with pytest.raises(ValueError, match="max_depth"):
        service.inspect_gui_menu("no-session-needed", max_depth=True)
