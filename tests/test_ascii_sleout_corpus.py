"""Opt-in existing public SLEOUT literals; no downloads, copies or native process."""
import os
from pathlib import Path

import pytest

from tests.test_ascii_sleout_database import FIRST, SECOND, frame
from tools.fetch_corpus import plain_path
from tools.verify_ascii_sleout_corpus import CASES, literal_reference, verify_case


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_registered_sleout_all_three_energy_columns(tmp_path, case):
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        pytest.skip("Set LSPP_CORPUS_DIR to existing registered public SLEOUT samples")
    result = verify_case(plain_path(Path(location)), tmp_path, case)
    assert all(curve["exact"] for curve in result["curves"])
    assert result["source_unchanged"] and result["source_stat_unchanged"] and result["source_directory_unchanged"]


@pytest.mark.parametrize("layout", ["slave", "surfa"])
def test_independent_scanner_joins_raw_written_ids_and_keeps_all_three_columns(tmp_path, layout):
    source = tmp_path / "sleout"
    source.write_text(frame(0, 1, FIRST, layout) + frame(2, 2, SECOND, layout), encoding="utf8")
    times, identifiers, frames, labels = literal_reference(source)
    assert times == [0., 2.] and identifiers == [90, 10]
    assert frames[0]["rows"][90] == [1., -2., 3.]
    assert frames[1]["rows"][90] == [10., -11., 12.]
    assert frames[1]["rows"][10] == [-7., 8., -9.]
    assert labels == [("slave", "master", "frictional") if layout == "slave" else ("surfa", "surfb", "frictional")]
