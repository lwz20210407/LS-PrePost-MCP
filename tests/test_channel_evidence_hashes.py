"""Verify recorded native-test source hashes on Linux and Windows without LSPP."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("task", ["a01", "a02", "a03", "a04"])
def test_recorded_channel_source_blobs_have_portable_lf_hashes(task):
    if not (ROOT / ".git").exists():
        pytest.skip("Historical Git objects are unavailable in an unpacked source copy")
    data = json.loads((ROOT / "docs/decisions/evidence" / task / "evidence.json").read_text(encoding="utf8"))
    for run in data["runs"]:
        source = run["test_source_identity"]
        blob = subprocess.check_output(["git", "cat-file", "blob", source["git_blob_id"]], cwd=ROOT)
        digest = hashlib.sha256(blob.replace(b"\r\n", b"\n")).hexdigest()
        assert source["sha256_lf"] == digest
        assert "LF" in source["newline_basis"]
        if source == data["test_source_identity"]:
            assert data["test_source_sha256"] == digest
        assert run["context"] in run["report"]
