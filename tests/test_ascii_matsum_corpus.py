"""Opt-in existing public MATSUM literals; no downloads, copies or native process."""
import os
from pathlib import Path

import pytest

from tools.fetch_corpus import plain_path
from tools.verify_ascii_matsum_corpus import CASES, literal_reference, verify_case


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_registered_matsum_all_supported_energy_columns(tmp_path, case):
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        pytest.skip("Set LSPP_CORPUS_DIR to existing registered public MATSUM samples")
    result = verify_case(plain_path(Path(location)), tmp_path, case)
    assert all(c["exact"] for c in result["curves"])
    assert result["source_unchanged"] and result["source_directory_unchanged"]


def test_literal_reference_uses_written_nonsequential_id_not_position(tmp_path):
    source = tmp_path / "matsum"
    source.write_text("time = 0\nmat.#= 90 inten= 4 kinen= 0\nmat.#= 10 inten= 2 kinen= 3\n"
                      "time = 1\nmat.#= 10 inten= 5 kinen= 7\nmat.#= 90 inten= 6 kinen= 9\n")
    times, identifiers, data = literal_reference(source)
    assert times == [0., 1.] and identifiers == [90, 10]
    assert data[0., 90, "kinetic_energy"] == 0.
    assert data[1., 10, "internal_energy"] == 5.
