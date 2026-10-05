"""I10: offline guards against calling stale artifacts an experiment pass."""

import struct
import time

import pytest

from tools.experiments.run_matrix import check_outputs, session_flags_state


@pytest.mark.parametrize(
    "state,flags,expected",
    [(0, 0, "locked"), (0, 1, "unlocked"), (4, 0, "rdp_disconnected"), (0, 0xFFFFFFFF, "unknown")],
)
def test_wts_lock_flags_are_not_inferred_from_input_desktop(state, flags, expected):
    data = struct.pack("<5I", 1, 0, 7, state, flags)
    assert session_flags_state(data, 7) == expected
    assert session_flags_state(data, 8) == "unknown"
    assert session_flags_state(data[:19], 7) == "unknown"


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
