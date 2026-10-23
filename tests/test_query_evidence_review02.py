"""Keep refreshed retrieval results tied to actual code and unmodified query files."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_query_replay_includes_unavailable_sources_in_overall_denominators():
    evidence = json.loads((ROOT / "docs/decisions/evidence/i05-query-review02/evidence.json").read_text(encoding="utf8"))
    assert evidence["status"] == "partial" and not evidence["index"]["private"]
    assert evidence["index"]["categories"].get("api", 0) == 0
    assert evidence["index"]["api_tokenization"] == "identifier-parts-v2"
    assert [(r["hits_at_3"], r["queries"]) for r in evidence["replay"]] == [(14, 20), (16, 24), (13, 24)]
    for replay in evidence["replay"]:
        raw = (ROOT / "tests/data" / replay["cases"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == replay["queries_sha256"]
        assert len(replay["results"]) == replay["queries"]
        assert sum(row["hit_at_3"] for row in replay["results"]) == replay["hits_at_3"]


def test_query_evidence_binds_product_and_evaluator_blobs():
    probe = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, capture_output=True, text=True)
    if probe.returncode or probe.stdout.strip() == "true":
        pytest.skip("Historical query product provenance needs complete Git history")
    evidence = json.loads((ROOT / "docs/decisions/evidence/i05-query-review02/evidence.json").read_text(encoding="utf8"))
    for identity in [*evidence["product_source_identity"], evidence["test_source_identity"]]:
        blob = subprocess.check_output(["git", "rev-parse", evidence["actual_git_revision"] + ":" + identity["path"]], cwd=ROOT, text=True).strip()
        assert blob == identity["git_blob_id"]
