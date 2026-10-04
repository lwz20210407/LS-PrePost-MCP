import numpy as np
import pytest

from ls_prepost_mcp.gui_curves import native_plot_values, plot_text, read_xy_csv, verify_xy_readback


def test_hysteresis_csv_preserves_backtracking_and_column_choice(tmp_path):
    source = tmp_path / "loop.csv"
    source.write_text("time,u,F\n0,0,0\n1,2,3\n2,1,1\n3,0,0\n")
    values = read_xy_csv(source, "u", "F")
    assert values.tolist() == [[0, 0], [2, 3], [1, 1], [0, 0]]
    native = tmp_path / "native.xy"
    native.write_text("4\n0 0\n2 3\n1 1\n0 0\n")
    assert verify_xy_readback(native, values)["row_order_preserved"]
    with pytest.raises(ValueError, match="values"):
        verify_xy_readback(native, values[[0, 3, 2, 1]])


def test_native_single_precision_is_explicit_and_not_a_broad_comparison_tolerance(tmp_path):
    path = tmp_path / "native.xy"
    path.write_text("2\n0 0\n1.0000000149e-01 1\n")
    report = verify_xy_readback(path, np.array([[0.0, 0.0], [0.1, 1.0]]))
    assert report["native_storage_dtype"] == "float32"
    assert report["maximum_absolute_difference"] > 0
    path.write_text("2\n0 0\n1.00000004e-01 1\n")
    with pytest.raises(ValueError):
        verify_xy_readback(path, np.array([[0.0, 0.0], [0.1, 1.0]]))
    for value in (1e100, 1e-100, 1e-45):
        with pytest.raises(ValueError, match="float32|quantization"):
            native_plot_values(np.array([[0.0, 0.0], [value, 1.0]]))


@pytest.mark.parametrize(
    "text", ["x,x\n0,1\n1,2\n", "x,y\n0,nan\n1,2\n", "x,y\n0,1\n", "x,y\n0,1,extra\n1,2\n", "x,y\n0\n1,2\n"]
)
def test_ambiguous_nonfinite_or_incomplete_csv_is_rejected(tmp_path, text):
    source = tmp_path / "invalid.csv"
    source.write_text(text)
    with pytest.raises(ValueError):
        read_xy_csv(source, "x", "y")


@pytest.mark.parametrize(
    "text", ["3\n0 0\n1 1\n", "2\n0 0\n1 1\n2\n0 0\n1 1\n", "2\n0 0\n1 nan\n", "2\n0 0\n1 2\n"]
)
def test_native_readback_rejects_truncation_extra_curves_and_wrong_values(tmp_path, text):
    path = tmp_path / "native.xy"
    path.write_text(text)
    with pytest.raises(ValueError):
        verify_xy_readback(path, np.array([[0.0, 0.0], [1.0, 1.0]]))


@pytest.mark.parametrize("text", ['x"\nexit', "x\\y", "", "应力", "a" * 81])
def test_unvalidated_label_encoding_and_command_delimiters_are_rejected(text):
    with pytest.raises(ValueError):
        plot_text(text, "title", 80)


def test_multicurve_roundtrip_preserves_unequal_lengths_grids_and_order(tmp_path):
    from ls_prepost_mcp.gui_curves import verify_curve_readback

    curves = [np.array([[0.0, 0.0], [2.0, 3.0], [1.0, 1.0]]), np.array([[0.0, 2.0], [4.0, 6.0]])]
    path = tmp_path / "both.xy"
    path.write_text("3\n0 0\n2 3\n1 1\n2\n0 2\n4 6\n")
    report = verify_curve_readback(path, curves)
    assert [c["sample_count"] for c in report] == [3, 2]
    assert all(c["row_order_preserved"] for c in report)
    with pytest.raises(ValueError, match="count"):
        verify_curve_readback(path, curves[::-1])
    with pytest.raises(ValueError, match="count"):
        verify_curve_readback(path, curves[:1])
    path.write_text("3\n0 0\n2 3\n1 1\n2\n0 2\n")
    with pytest.raises(ValueError, match="count"):
        verify_curve_readback(path, curves)


@pytest.mark.parametrize("bad", ["unit", "label", "missing", "extra", "first_label", "number"])
def test_overlay_contract_rejects_ambiguous_sources_before_native_work(tmp_path, bad):
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.gui_curves import curve_sources
    from ls_prepost_mcp.service import Service

    path = tmp_path / "curve.csv"
    path.write_text("x,y\n0,0\n1,1\n")
    spec = dict(path=str(path), x_column="x", y_column="y", label="Second", x_unit="s", y_unit="N")
    label = "First"
    if bad == "unit":
        spec["y_unit"] = "kN"
    if bad == "label":
        spec["label"] = "First"
    if bad == "missing":
        del spec["x_column"]
    if bad == "extra":
        spec["guess_units"] = True
    if bad == "first_label":
        label = None
    with pytest.raises(ValueError):
        curve_sources(
            Service(Settings(tmp_path)),
            str(path),
            "x",
            "y",
            "s",
            "N",
            label,
            [spec] * (10 if bad == "number" else 1),
        )


def test_single_curve_column_names_remain_independent_of_optional_legend(tmp_path):
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.gui_curves import curve_sources
    from ls_prepost_mcp.service import Service

    path = tmp_path / "curve.csv"
    path.write_text("位移,载荷\n0,0\n1,1\n", encoding="utf8")
    curves = curve_sources(Service(Settings(tmp_path)), str(path), "位移", "载荷", "mm", "N", None, None)
    assert curves[0]["spec"]["y_column"] == "载荷"
