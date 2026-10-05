"""I10: offline guards against calling stale artifacts an experiment pass."""

import time

import pytest

from tools.experiments.run_matrix import check_outputs


def test_old_receipt_is_not_a_fresh_native_result(tmp_path):
    (tmp_path / "receipt.txt").write_text("request 8")
    started = time.time_ns() + 1_000_000
    cell = dict(directory=str(tmp_path), request_id="request", expected_nodes=8, language="scl")
    with pytest.raises(ValueError, match="fresh"):
        check_outputs(cell, "execution", started)


def test_correct_count_with_wrong_request_identity_fails(tmp_path):
    (tmp_path / "receipt.txt").write_text("wrong 8")
    cell = dict(directory=str(tmp_path), request_id="request", expected_nodes=8, language="scl")
    with pytest.raises(ValueError, match="identity"):
        check_outputs(cell, "execution", 0)


def test_native_count_alone_does_not_certify_saved_keyword(tmp_path):
    (tmp_path / "receipt.txt").write_text("request 8")
    (tmp_path / "model.k").write_text("*KEYWORD\n*NODE\n11,0,0,0\n*END\n")
    cell = dict(directory=str(tmp_path), request_id="request", expected_nodes=8, language="command")
    with pytest.raises(ValueError, match="node count"):
        check_outputs(cell, "execution", 0)
