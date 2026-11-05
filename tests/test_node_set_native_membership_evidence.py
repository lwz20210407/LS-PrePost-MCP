"""P04 finite native claims bind the actual producer, inputs and consumer blobs."""
import ast
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/decisions/evidence/p04-native-membership/evidence.json"
BINARY = "ce76fdf75a2f14c0a3e94964809ddd178934d04381f7f31e1e1eb05592bd5414"
REQUIRED_PRODUCTS = {
    "src/ls_prepost_mcp/service.py", "src/ls_prepost_mcp/programs.py",
    "src/ls_prepost_mcp/domain/model/deck.py", "src/ls_prepost_mcp/domain/model/fields.py",
    "src/ls_prepost_mcp/domain/model/layouts.py", "src/ls_prepost_mcp/domain/model/node_sets.py",
    "src/ls_prepost_mcp/domain/model/sets.py", "src/ls_prepost_mcp/domain/model/operations.py",
    "src/ls_prepost_mcp/domain/model/matching.py", "src/ls_prepost_mcp/domain/model/_identity.py",
}


def evidence():
    return json.loads(EVIDENCE.read_text(encoding="utf8"))


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=20)


def test_current_membership_evidence_binds_consumer_producer_and_test_sources():
    data = evidence()
    assert data["task_status"] == "partial" and data["validity"] == "current_for_recorded_product_blobs"
    assert data["working_tree_dirty"] is False
    assert data["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
    products = data["product_source_identity"]
    assert {item["path"] for item in products} == REQUIRED_PRODUCTS
    assert data["producer_source_identity"]["path"] == "tools/verify_node_set_user_ids.py"
    assert data["test_source_identity"]["path"] == "tests/test_node_set_native_identity.py"
    if git("rev-parse", "--is-shallow-repository").strip() == b"true":
        pytest.skip("Source-bound historical proof requires complete Git history")
    for item in [*products, data["producer_source_identity"], data["test_source_identity"]]:
        actual = git("rev-parse", data["actual_git_revision"] + ":" + item["path"]).decode().strip()
        current = git("rev-parse", "HEAD:" + item["path"]).decode().strip()
        assert actual == item["git_blob_id"] == current, "Native membership evidence is stale: " + item["path"]
        if "repository_lf_sha256" in item:
            source = git("show", data["actual_git_revision"] + ":" + item["path"])
            assert hashlib.sha256(source.replace(b"\r\n", b"\n")).hexdigest() == item["repository_lf_sha256"]
    producer = git("show", data["actual_git_revision"] + ":" + data["producer_source_identity"]["path"]).decode("utf8")
    constants = {}
    for node in ast.parse(producer).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("PROGRAM", "SOURCE") for t in node.targets):
            constants[node.targets[0].id] = ast.literal_eval(node.value)
    assert hashlib.sha256(constants["PROGRAM"].encode()).hexdigest() == data["native_run"]["script_sha256"]
    assert hashlib.sha256(constants["SOURCE"].encode("ascii")).hexdigest() == data["fixture"]["source_sha256"]
    report = (EVIDENCE.parent / data["report"]).read_text(encoding="utf8")
    assert hashlib.sha256(report.encode()).hexdigest() == data["report_sha256_lf"]


def test_native_membership_is_finite_and_does_not_claim_add_definition_order():
    data = evidence()
    native = data["native_run"]
    assert native["native_executed"] is True and native["actual_native_processes"] == 1
    assert native["status"] == native["domain_proof_status"] == "passed" and native["engine_api_status"] == "succeeded"
    process = native["process"]
    assert type(process["pid"]) is int and process["pid"] > 0 and process["returncode"] == 0
    assert process["nographics"] is True and process["graphics"] is False and process["timed_out"] is False
    assert native["executable_sha256"] == BINARY
    profile = native["executable_profile"]
    assert profile["version"] == "4.13" and profile["version_source"] == "file_version_resource"
    assert profile["resource_conflict"] is False
    assert all(native["identity_guards"].values()) and len(native["identity_guards"]) == 6
    assert data["fixture"]["node_ids"] == [11, 37, 89, 121] and data["fixture"]["node_count"] == 4
    assert data["fixture"]["source_files"] == 1
    result = native["comparison"]
    assert result["registry_user_ids"] == [11, 37, 89, 121]
    assert [(row["user_id"], row["internal_id"], row["roundtrip_user_id"]) for row in result["mapping"]] == [
        (11, 0, 11), (37, 1, 37), (89, 2, 89), (121, 3, 121)]
    sets = {item["sid"]: item for item in result["sets"]}
    assert set(sets) == {101, 202, 303}
    assert [sets[sid]["raw_ids_inset"] for sid in (101, 202, 303)] == [[4, 2], [1, 2, 3], [1, 2, 3, 4]]
    expected = {101: [121, 37], 202: [11, 37, 89], 303: [121, 37, 11, 89]}
    for sid, written in expected.items():
        assert sets[sid]["expected_user_ids"] == written
        assert sorted(sets[sid]["native_user_ids"]) == sorted(written)
        assert sets[sid]["membership_equal"] is True
    assert [sets[sid]["definition_order_equal"] for sid in (101, 202, 303)] == [True, True, False]
    assert native["saved_tree_path_reopen_or_native_export_claim"] is False
    monitor = data["cross_profile_configuration_monitor"]
    assert monitor["native_lease_released"] and monitor["no_native_processes_remain"] and monitor["both_config_bytes_unchanged"]
    assert monitor["other_version_native_executed"] is False
    assert monitor["generalized_global_write_protection_proven"] is False
    assert {item["version"] for item in monitor["profiles"]} == {"4.13", "4.10"}
    for profile in monitor["profiles"]:
        assert profile["source_config_sha_size_mtime_unchanged"] is True
        assert {k: profile["before"][k] for k in ("sha256", "size", "mtime_ns")} == {
            k: profile["after"][k] for k in ("sha256", "size", "mtime_ns")}


def test_static_provenance_does_not_publish_vendor_code_or_hide_old_refusal():
    data = evidence()
    static = data["static_evidence"]
    assert static["target_source_sha256"] == BINARY
    assert static["original_source_recovered"] is False and static["global_analysis_complete"] is False
    assert static["new_provider_or_decompiler_run"] is False and static["vendor_code_published"] is False
    assert static["sufficient_conditions"] and static["remaining_unknowns"]
    allowed = {"index", "entry", "bundle", "bundle_sha256", "jsonl_row_1based", "pseudocode_sha256",
               "global_analysis_complete", "original_source_recovered"}
    assert static["retained_function_entries"]
    for item in static["retained_function_entries"]:
        assert set(item) <= allowed and item["entry"]
        assert item["global_analysis_complete"] is False and item["original_source_recovered"] is False
        for name in ("bundle_sha256", "pseudocode_sha256"):
            assert len(item[name]) == 64 and int(item[name], 16) >= 0
    historical = data["historical_observations"]
    assert historical["d139"]["rewritten"] is False and historical["d139"]["expected_user_id_matches"] == [False] * 3
    old = historical["source950"]
    assert old["rewritten"] is False and old["native_executed"] is True
    assert old["engine_api_status"] == "succeeded" and old["domain_proof_status"] == "failed"
    replay = historical["policy_only_replay"]
    assert replay["new_native_execution"] is False and replay["counts_as_fresh_native_evidence"] is False
    assert replay["original_capture_status"] == replay["old_policy_status"] == "failed"
    assert replay["original_report_sha256"] == old["private_report_raw_sha256"]
