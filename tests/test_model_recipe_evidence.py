"""Source and provenance checks; these do not claim native recipe validity."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "docs/decisions/evidence/p03-active.json"
MCP_REGISTRATION_PRODUCTS = {
    "src/ls_prepost_mcp/operation_registry.py",
    "src/ls_prepost_mcp/data/operations.json",
    "src/ls_prepost_mcp/server.py",
    "src/ls_prepost_mcp/compact_server.py",
}


def read():
    pointer = json.loads(ACTIVE.read_text(encoding="utf8"))
    evidence = ROOT / pointer["active_product_evidence"]
    assert evidence.resolve().is_relative_to((ROOT / "docs/decisions/evidence").resolve())
    return json.loads(evidence.read_text(encoding="utf8"))


def require_registration_identity(evidence):
    paths = {item["path"] for item in evidence["product_source_identity"]}
    assert MCP_REGISTRATION_PRODUCTS <= paths, "Host/stdio evidence omitted a consumed MCP registration dependency"


def test_current_host_evidence_lists_all_consumed_mcp_registration_sources():
    require_registration_identity(read())


@pytest.mark.parametrize("missing", ["operation_registry.py", "data/operations.json"])
def test_registration_identity_gate_rejects_omitted_consumed_code_or_data(missing):
    incomplete = {"product_source_identity": [{"path": path} for path in MCP_REGISTRATION_PRODUCTS
                                               if not path.endswith("/" + missing)]}
    with pytest.raises(AssertionError, match="registration dependency"):
        require_registration_identity(incomplete)


def require_current_product_identity(item, recorded):
    current = subprocess.check_output(["git", "hash-object", item["path"]], cwd=ROOT, text=True).strip()
    assert current == recorded, "Host recipe evidence superseded by product change: " + item["path"]


def test_current_identity_gate_rejects_changed_registry_data_blob(monkeypatch):
    item = {"path": "src/ls_prepost_mcp/data/operations.json"}
    recorded = subprocess.check_output(["git", "hash-object", item["path"]], cwd=ROOT, text=True).strip()

    def drifted(arguments, **kwargs):
        assert arguments == ["git", "hash-object", item["path"]]
        return "0" * 40 + "\n"

    monkeypatch.setattr(subprocess, "check_output", drifted)
    with pytest.raises(AssertionError, match="superseded.*data/operations.json"):
        require_current_product_identity(item, recorded)


def test_host_recipe_evidence_keeps_l1_scope_and_every_original_a10_object():
    evidence = read()
    assert evidence["status"] == "partial" and evidence["verification_level"] == "L1" and evidence["native_executed"] is False
    assert evidence["product_identity_not_all_feature_coverage"] is True
    assert all(case["passed"] for case in evidence["l1_run"]["cases"])
    assert evidence["l1_run"]["passed"] == len(evidence["l1_run"]["cases"])
    assert evidence["wheel"]["offline_build"] and not evidence["wheel"]["pip_install_performed"]
    preserved = evidence["old_a10_objects_preserved"]
    assert preserved["raw_sha256"].keys() == preserved["sha256_git_lf"].keys() == preserved["git_blob_ids"].keys()
    for name, expected in preserved["sha256_git_lf"].items():
        contents = (ROOT / preserved["directory"] / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(contents).hexdigest() == expected
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
                require_current_product_identity(item, recorded)
    preserved = evidence["old_a10_objects_preserved"]
    for name, expected in preserved["git_blob_ids"].items():
        relative = preserved["directory"] + "/" + name
        historical = subprocess.check_output(["git", "rev-parse", preserved["git_source_revision"] + ":" + relative], cwd=ROOT, text=True).strip()
        current = subprocess.check_output(["git", "hash-object", relative], cwd=ROOT, text=True).strip()
        assert historical == current == expected, "Historical A10 Git object changed: " + relative


def test_new_backend_refresh_preserves_original_host_bytes_and_does_not_claim_new_a10_replay():
    evidence = read()
    previous = evidence["previous_host_evidence"]
    assert previous["original_objects_rewritten"] is False
    old_directory = ROOT / "docs/decisions/evidence/p03-model-recipes"
    for name, expected in previous["repository_lf_sha256"].items():
        raw = (old_directory / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == expected
    assert evidence["wheel"]["actual_source_revision"] == evidence["actual_git_revision"]
    assert evidence["wheel"]["new_typed_deck_git_lf_in_wheel"] is True
    assert evidence["wheel"]["source_document_pin_accepted"] is True
    retrieval = evidence["retrieval_dependency_check"]
    assert retrieval["original_11_retrieval_product_git_blobs_unchanged"] is True
    assert retrieval["original_98_queries_replayed"] is False and retrieval["full_index_rebuilt"] is False
    assert retrieval["old_sqlite_reopened"] is False
