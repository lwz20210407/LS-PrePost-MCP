"""Client metadata evidence binds code/data and preserves actual prior host contexts."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/decisions/evidence/i08-client-migration/evidence.json"
PRODUCTS = {
    "src/ls_prepost_mcp/operation_registry.py", "src/ls_prepost_mcp/data/operations.json",
    "src/ls_prepost_mcp/server.py", "src/ls_prepost_mcp/compact_server.py",
}


def read():
    return json.loads(EVIDENCE.read_text(encoding="utf8"))


def test_migration_evidence_has_current_code_and_registry_data_identities():
    data = read()
    assert PRODUCTS <= {item["path"] for item in data["product_source_identity"]}
    shallow = subprocess.check_output(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, text=True).strip()
    if shallow == "true":
        pytest.skip("Historical evidence requires full Git objects")
    for item in data["product_source_identity"]:
        recorded = subprocess.check_output(["git", "rev-parse", data["actual_git_revision"] + ":" + item["path"]], cwd=ROOT, text=True).strip()
        current = subprocess.check_output(["git", "hash-object", item["path"]], cwd=ROOT, text=True).strip()
        assert recorded == current == item["git_blob_id"], "Client metadata evidence source drift: " + item["path"]
    for item in data["test_source_identity"]:
        recorded = subprocess.check_output(["git", "rev-parse", data["actual_git_revision"] + ":" + item["path"]], cwd=ROOT, text=True).strip()
        assert recorded == item["git_blob_id"]


def test_migration_evidence_keeps_profile_native_and_archival_scope_honest():
    data = read()
    assert data["working_tree_dirty"] is False and data["source_unchanged"] is True
    assert data["native_executed"] is False and data["verification_level"] == "L1"
    assert data["task_status_changed"] is False and data["catalog"]["profiles_changed"] is False
    assert data["catalog"]["full_default"] == data["catalog"]["registered"] == 163
    assert data["catalog"]["compact_entrypoints"] == 3
    assert data["catalog"]["compatibility_names"] + data["catalog"]["canonical"] == data["catalog"]["registered"]
    assert data["optional_sdk_absence"]["deselected"] == 2
    assert data["original_98_questions_replayed"] is False and data["full_index_rebuilt"] is False
    archive = data["additional_dependency_identity"]
    assert archive["new_execution_performed"] is False
    assert archive["captured_raw_sha256_before"] == archive["captured_raw_sha256_after"]
    assert archive["original_selected_product_files"] == 21
    assert archive["source_scope"] == "explicit21+archived_data1=22"
    assert not any(prefix in json.dumps(data) for prefix in ("F:\\", "D:\\", "C:\\"))


def test_new_host_context_keeps_previous_active_typed_write_artifacts_unchanged():
    report = ROOT / read()["p03_refresh"]["report"]
    host = json.loads(report.with_name("evidence.json").read_text(encoding="utf8"))
    previous = host["previous_active_evidence"]
    assert previous["original_objects_rewritten"] is False
    for name, expected in previous["repository_lf_sha256"].items():
        raw = (ROOT / previous["directory"] / name).read_bytes()
        assert hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == expected
    assert host["source_scope"]["explicitly_selected"] == 21 and host["source_scope"]["archived_data_dependencies"] == 1
    assert len(host["product_source_identity"]) == 22
    assert host["wheel"]["source_document_pin_accepted"] is True
    assert len(host["wheel"]["source_member_identity"]) == 21
    assert host["wheel"]["additional_archived_member_identity"]["path"] == "ls_prepost_mcp/data/operations.json"
