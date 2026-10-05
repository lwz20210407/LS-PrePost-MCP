"""I11: preserve external fixtures and reject destination escapes."""

import hashlib

import pytest

from tools.fetch_corpus import destination, fetch


def test_fetch_reuses_verified_fixture_but_refuses_corrupt_existing_data(tmp_path):
    entry = dict(
        id="small",
        status="available",
        files=[
            dict(
                path="parts/model.k",
                content="*KEYWORD\n*END\n",
                sha256=hashlib.sha256(b"*KEYWORD\n*END\n").hexdigest(),
            )
        ],
    )
    fetch(entry, tmp_path)
    fetch(entry, tmp_path)
    path = tmp_path / "small/parts/model.k"
    path.write_bytes(b"user edit")
    with pytest.raises(ValueError, match="mismatch"):
        fetch(entry, tmp_path)
    assert path.read_bytes() == b"user edit"


def test_fixture_path_cannot_escape_cache(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        destination(tmp_path, "../outside.k")
