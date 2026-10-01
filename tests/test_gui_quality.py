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


def test_keyword_report_separates_findings_without_claiming_solver_validation():
    from ls_prepost_mcp.gui_quality import parse_keyword_report

    source = "*Model Check Result\ntotal warning 4\ntotal error 1\ntotal unref 0\ntotal undefine 2\n*PART (1) Warning(0) Error(1) Unreferenced(0) Undefine(0)\n*PART\nMissing material\n*endcheckinfo\n"
    report = parse_keyword_report(source)
    assert report["totals"] == dict(warning=4, error=1, unref=0, undefine=2)
    assert report["categories"][0]["keyword"] == "PART"
    assert report["has_findings"] and not report["passed_checks"]
    assert not report["solver_validated"] and not report["contacts_checked"]
    assert "Missing material" in report["details"]
    for broken in [
        source.replace("*endcheckinfo", ""),
        source.replace("total undefine 2\n", ""),
        source.replace("total error 1", "total error 1\ntotal error 0"),
    ]:
        with pytest.raises(ValueError):
            parse_keyword_report(broken)
