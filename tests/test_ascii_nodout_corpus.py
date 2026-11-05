"""Registered optional public inputs, never copied into the repository."""
import os
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from tools.fetch_corpus import entries, load_registry, plain_path, resolve
from tools.verify_ascii_nodout_corpus import CASES, literal_reference, verify_case


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_public_nodout_all_nine_literal_components(tmp_path, case):
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        pytest.skip("Set LSPP_CORPUS_DIR to existing registered public NODOUT inputs")
    result = verify_case(plain_path(Path(location)), tmp_path, case)
    assert result["source_unchanged"] and result["source_directory_unchanged"]


@pytest.mark.parametrize("corpus_id,reason", [
    ("result.node997__dyna_pladebuk.Plade_300_150_4.BB", "No NODOUT"),
    ("result.mlp6__fem.tests", "underflows"),
])
def test_public_nodout_explicit_no_data_or_unrepresentable_number_limit(tmp_path, corpus_id, reason):
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        pytest.skip("Set LSPP_CORPUS_DIR to existing registered public NODOUT inputs")
    corpus = plain_path(Path(location))
    source = plain_path(resolve(entries(load_registry())[corpus_id], corpus) / "nodout")
    result = Service(Settings(tmp_path, allowed_roots=(corpus,))).extract_database(
        str(source), "nodout", "z_displacement", "declared_source")
    assert result["status"] == "failed" and not result["artifacts"]
    assert reason in result["error"]["message"]


def test_independent_reference_does_not_use_the_fixed_width_slicer(tmp_path):
    from tests.test_ascii_nodout_database import TEXT

    source = tmp_path / "nodout"
    source.write_text(TEXT)
    times, ids, data = literal_reference(source)
    assert times == [0., 2.] and ids == [90, 10]
    assert data[0., 90] == [1., -2., 3., -4., 5., -6., 7., -8., 9.]
