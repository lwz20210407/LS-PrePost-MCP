import numpy as np
import pytest

from ls_prepost_mcp.results import lasso_vectors


def test_lasso_state_coordinates_are_not_displacements():
    pytest.importorskip("lasso.dyna")
    arrays = {"node_coordinates": np.array([[100., 200., 300.]]),
              "node_displacement": np.array([[[100., 200., 300.]], [[103., 204., 300.]]]),
              "node_velocity": np.array([[[1., 2., 3.]], [[4., 5., 6.]]])}
    np.testing.assert_array_equal(lasso_vectors(arrays, "displacement"), [[[0., 0., 0.]], [[3., 4., 0.]]])
    np.testing.assert_array_equal(lasso_vectors(arrays, "velocity"), arrays["node_velocity"])


def test_lasso_rejects_misaligned_reference():
    pytest.importorskip("lasso.dyna")
    with pytest.raises(ValueError, match="align"):
        lasso_vectors({"node_coordinates": np.zeros((2, 3)), "node_displacement": np.zeros((2, 3, 3))}, "displacement")


def test_binout_literal_brackets_do_not_escape_to_another_directory(tmp_path, monkeypatch):
    pytest.importorskip("lasso.dyna")
    import glob
    from types import SimpleNamespace

    from ls_prepost_mcp.results import open_binout
    literal = tmp_path / "case[1]"
    other = tmp_path / "case1"
    literal.mkdir()
    other.mkdir()
    (literal / "binout").touch()
    (other / "binout").touch()
    closed = []
    def fake(pattern):
        assert glob.glob(pattern) == [str(literal / "binout")]
        return SimpleNamespace(lsda=SimpleNamespace(close=lambda: closed.append(True)))
    monkeypatch.setattr("lasso.dyna.Binout", fake)
    with open_binout(str(literal / "binout")):
        pass
    assert closed == [True]
