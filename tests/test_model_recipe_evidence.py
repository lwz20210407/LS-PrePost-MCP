"""Source and provenance checks; these do not claim native recipe validity."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/decisions/evidence/p03-model-recipes/evidence.json"


def read():
    return json.loads(EVIDENCE.read_text(encoding="utf8"))


def test_host_recipe_evidence_keeps_l1_scope_and_every_original_a10_object():
    evidence = read()
    assert evidence["status"] == "partial" and evidence["verification_level"] == "L1" and evidence["native_executed"] is False
    assert evidence["product_identity_not_all_feature_coverage"] is True
    assert all(case["passed"] for case in evidence["l1_run"]["cases"])
    assert evidence["l1_run"]["passed"] == len(evidence["l1_run"]["cases"])
    assert evidence["wheel"]["offline_build"] and not evidence["wheel"]["pip_install_performed"]
    preserved = evidence["old_a10_objects_preserved"]
    for name, expected in preserved["raw_sha256"].items():
        assert hashlib.sha256((ROOT / preserved["directory"] / name).read_bytes()).hexdigest() == expected
    assert evidence["a10"]["queries_total"] == sum(row["queries"] for row in evidence["a10"]["sets"].values())
    assert evidence["a10"]["generated_field_descriptors"] - evidence["a10"]["indexed_keyword_fields"] == evidence["a10"]["exact_duplicates"]
    text = json.dumps(evidence, ensure_ascii=False)
    assert not any(prefix in text for prefix in ("F:\\", "D:\\", "C:\\"))


def test_current_host_recipe_evidence_binds_actual_product_and_test_git_objects():
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, capture_output=True, text=True)
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Historical product binding requires a complete Git checkout")
    evidence = read()
    for key in ("product_source_identity", "test_source_identity"):
        for item in evidence[key]:
            recorded = subprocess.check_output(["git", "rev-parse", evidence["actual_git_revision"] + ":" + item["path"]], cwd=ROOT, text=True).strip()
            assert recorded == item["git_blob_id"]
            if key == "product_source_identity" and evidence["validity"] == "current_for_recorded_product_blobs":
                current = subprocess.check_output(["git", "hash-object", item["path"]], cwd=ROOT, text=True).strip()
                assert current == recorded, "Host recipe evidence superseded by product change: " + item["path"]
