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
