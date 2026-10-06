"""Public sample configuration remains data-free and resolvable in CI."""
import json
from pathlib import Path, PurePosixPath

import pytest

from tools.fetch_corpus import entries, load_registry


def test_keyword_oracle_compares_exact_ids_independent_of_native_order():
    from test_public_corpus_native import compare_node_rows

    before = [[100000001, 1., 2., 3.], [7, 0., 1., 2.]]
    compare_node_rows(before, list(reversed(before)))
    with pytest.raises(AssertionError, match="User node IDs"):
        compare_node_rows(before, [[100000002, 1., 2., 3.], [7, 0., 1., 2.]])
    with pytest.raises(AssertionError):
        compare_node_rows(before, [[100000001, 9., 2., 3.], [7, 0., 1., 2.]])


def test_representative_cases_use_existing_public_ids_and_portable_members():
    payload = json.loads((Path(__file__).parent / "corpus/public_cases.json").read_text(encoding="utf8"))
    assert payload["schema_version"] == 1 and payload["task"] == "I04"
    cases, registry = payload["cases"], entries(load_registry())
    assert len({case["id"] for case in cases}) == len(cases)
    assert {case["kind"] for case in cases} == {"keyword", "d3plot", "binout", "ascii"}
    for case in cases:
        source = registry[case["corpus"]]
        assert source["path"].startswith(("public-keyword/", "public-results/"))
        member = PurePosixPath(case["member"])
        assert not member.is_absolute() and ".." not in member.parts
        assert ":" not in case["member"] and "\\" not in case["member"]
        assert case["features"] and len(set(case["features"])) == len(case["features"])
