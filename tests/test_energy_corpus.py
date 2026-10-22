"""Optional Q12 public references: no local paths, source copying or native process."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.service import Service
from tools.fetch_corpus import entries, load_registry, plain_path, resolve

CASES = [
    ("result.ansys__pyansys-heart.tests.heart.assets.post.main", "binout", 161, 8),
    ("result.hu-shuhan__editOpeniGame.test.Format_Validation_Test.lsdyna.Bolt_B_Explicit", "binout0000", 1000, 7),
    ("result.jascott4427__PILLARS-LSDyna.Bolt_B_Explicit", "glstat", 1001, 7),
]


@pytest.mark.parametrize("corpus_id,member,samples,parts", CASES)
def test_registered_energy_corpus_preserves_source_and_parts(tmp_path, corpus_id, member, samples, parts):
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        pytest.skip("Set LSPP_CORPUS_DIR to use locally registered public energy inputs")
    if member.startswith("binout"):
        pytest.importorskip("lasso.dyna")
    root = Path(location)
    source = plain_path(resolve(entries(load_registry())[corpus_id], root) / member)
    if not source.is_file():
        pytest.fail(f"Registered corpus lacks {member}")
    family = [p for p in source.parent.iterdir() if p.is_file() and (
        p.name in ("glstat", "matsum") or p.name.startswith("binout"))]
    before = {}
    for path in family:
        with path.open("rb") as stream:
            before[path] = hashlib.file_digest(stream, "sha256").hexdigest()
    listing = sorted(p.name for p in source.parent.iterdir())
    result = JobResult.model_validate_json(json.dumps(Service(Settings(tmp_path / "jobs", allowed_roots=(root,)))
                                                     .check_energy(str(source), "model_energy"), allow_nan=False))
    assert result.status == "succeeded", result.error
    assert result.data["sample_count"] == samples and result.data["parts_analyzed"] == parts
    assert result.data["passed"] is None
    assert len(result.artifacts) == 3
    for path, sha in before.items():
        with path.open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == sha
    assert sorted(p.name for p in source.parent.iterdir()) == listing
