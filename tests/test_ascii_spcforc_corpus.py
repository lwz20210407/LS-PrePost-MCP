"""Opt-in local registered SPCFORC products; public data is never downloaded or copied."""
import os
from pathlib import Path

import pytest

from tests.test_ascii_spcforc_database import TEXT
from tools.fetch_corpus import plain_path
from tools.verify_ascii_spcforc_corpus import CASES, literal_reference, verify_case


@pytest.mark.parametrize("case", CASES, ids=[case[0] for case in CASES])
def test_registered_spcforc_all_stored_vectors_and_missing_moment_rejections(tmp_path, case):
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        pytest.skip("Set LSPP_CORPUS_DIR to existing registered public SPCFORC samples")
    result = verify_case(plain_path(Path(location)), tmp_path, case, reader_mode="service")
    assert all(curve["exact"] for curve in result["curves"])
    assert len(result["curves"]) == (6 if case[3] else 3)
    assert result["unavailable_components_rejected"] == ([] if case[3] else ["x_moment", "y_moment", "z_moment"])
    assert result["source_unchanged"] and result["source_directory_unchanged"]
    assert result["source_stat_before"] == result["source_stat_after"]


@pytest.mark.parametrize("moments", [False, True])
def test_reference_scanner_preserves_distinct_force_and_nonzero_moment_vectors(tmp_path, moments):
    source = tmp_path / "spcforc"
    text = TEXT if moments else "\n".join(line for line in TEXT.splitlines() if "moments=" not in line)
    source.write_text(text, encoding="utf8")
    reference = literal_reference(source)
    assert reference["times"] == [0, 2] and reference["ids"] == [90, 10]
    assert reference["setid"] == [7, 0] and reference["moments"] is moments
    assert reference["frames"][0]["forces"][90] == [1, -2, 3]
    assert reference["frames"][1]["forces"][10] == [0, -21, 31]
    if moments:
        assert reference["frames"][0]["moments"][90] == [4, -5, 6]
        assert reference["frames"][1]["moments"][10] == [41, -51, 61]
    else:
        assert all(not frame["moments"] for frame in reference["frames"])
