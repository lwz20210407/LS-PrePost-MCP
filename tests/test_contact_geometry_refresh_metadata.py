"""Portable checks of the archived captures; no host/native/wheel execution is replayed."""
import hashlib
import json
import re
import subprocess
from collections import Counter

import pytest

from tools import contact_geometry_evidence as context

TASKS = ("P03", "P04", "P05", "P12", "P06_identity", "P06_geometry")


def _strings(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


@pytest.mark.parametrize("task", TASKS)
def test_each_actual_refresh_context_has_bound_report_and_no_private_paths(task):
    path = context.evidence_path(task)
    data = context.read_evidence(task)
    assert len(path.read_bytes()) < 512 * 1024
    report = path.with_name(data["report"]).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(report).hexdigest() == data["report_sha256_lf"]
    assert data["status"] == "partial"
    assert all(re.search(r"[A-Za-z]:[\\/]|\\\\[^\\]+\\", item) is None for item in _strings(data))


def test_completed_host_roles_keep_their_actual_nonadditive_execution_sets():
    index = json.loads(context.INDEX.read_text(encoding="utf8"))
    assert index["state"] == "actual_captures_archived" and index["role_counts_not_additive"]
    for task, count, products in (("P03", 60, 24), ("P06_identity", 87, 35), ("P06_geometry", 90, 39)):
        data = context.read_evidence(task)
        assert data["actual_git_revision"] == index["actual_git_revision"]
        assert data["source_snapshot_sha256"] == index["source_snapshot_sha256"]
        assert data["l1_run"]["passed"] == len(data["l1_run"]["cases"]) == count
        assert len(data["product_source_identity"]) == products and len(data["test_source_identity"]) == 4
        assert data["overlapping_role_runs_not_unique_coverage"] is True and data["native_executed"] is False
        tests = {item["path"] for item in data["test_source_identity"]}
        assert ("tests/test_contact_geometry_mcp.py" in tests) == (task == "P06_geometry")
    geometry = context.read_evidence("P06_geometry")
    expected = set(context.P06_IDENTITY_PRODUCT_PATHS) | {"src/ls_prepost_mcp/" + path for path in (
        "server.py", "compact_server.py", "operation_registry.py", "data/operations.json")}
    assert {item["path"] for item in geometry["product_source_identity"]} == expected


def test_offline_wheel_accounts_for_all221_members_against_its_actual_git_source():
    data = context.read_evidence("P03")
    wheel = data["wheel"]
    assert wheel["actual_source_revision"] == data["actual_git_revision"]
    assert wheel["offline_build"] and not wheel["pip_install_performed"] and not wheel["native_executed"]
    assert wheel["bytes"] == 785079 and wheel["all_archive_members_accounted_for"]
    members = wheel["members"]
    assert len(members) == len({item["member"] for item in members}) == 221
    kinds = Counter(item["kind"] for item in members)
    assert kinds["package_source_git_lf_verified"] == 215
    assert kinds["generated_distribution_metadata"] == 5 and sum(kinds.values()) == 221
    mapped = [item for item in members if item.get("source") is not None]
    assert len(mapped) == 216
    tree = subprocess.check_output(["git", "ls-tree", "-r", data["actual_git_revision"]],
                                   cwd=context.ROOT, text=True, timeout=15)
    blobs = {line.split("\t", 1)[1]: line.split("\t", 1)[0].split()[2] for line in tree.splitlines()}
    for item in mapped:
        if item["kind"] == "package_source_git_lf_verified":
            assert blobs[item["source"]] == item["git_blob_id"]
        else:
            assert item["kind"] == "distribution_license_git_lf_verified" and item["source"] == "LICENSE"
    for item in members:
        assert re.fullmatch(r"[0-9a-f]{64}", item["wheel_raw_sha256"])
        if item["kind"] == "generated_distribution_metadata":
            assert item["source"] is None and "git_blob_id" not in item
    # Check recorded Git LF identities, including force-includes; do not pretend every member maps to src/.
    command = "".join(blobs[item["source"]] + "\n" for item in mapped).encode()
    response = subprocess.check_output(["git", "cat-file", "--batch"], input=command, cwd=context.ROOT, timeout=30)
    offset = 0
    for item in mapped:
        end = response.index(b"\n", offset)
        blob, kind, size = response[offset:end].split()
        assert blob.decode() == blobs[item["source"]] and kind == b"blob"
        contents = response[end + 1:end + 1 + int(size)].replace(b"\r\n", b"\n")
        assert hashlib.sha256(contents).hexdigest() == item["git_lf_sha256"]
        offset = end + 1 + int(size) + 1
    assert offset == len(response)
    assert wheel["baseline_refs_compared"] == 9 and wheel["baseline_refs_unchanged"]
    assert wheel["original_baseline_elastic_ref_executed"] and "in-process" in wheel["protocol_scope"]
    assert wheel["smoke_stdout_bytes_raw"] == 197 and wheel["smoke_stdout_bytes_lf"] == 196
    assert wheel["smoke_stdout_sha256_raw"] == "92158c0ea8e9f4fee80f6e90564fc5ffc6e0597a3556473d6466d6cb69dd35e4"
    assert wheel["smoke_stdout_sha256_lf"] == "c3836a25c154dffe8a3fe6455318dd919d6452b1bb622168754a71e98910b0af"


def test_native_per_job_stat_and_outer_full_hash_layers_remain_distinct():
    identifiers = []
    for task, jobs in (("P05", 6), ("P12", 18)):
        data = context.read_evidence(task)
        assert data["current_context_native_jobs"] == jobs
        assert data["current_native_validation"]["task_acceptance_complete"] is False
        for run in data["native_captures"]:
            assert re.fullmatch(r"[0-9a-f]{64}", run["executable_sha256"])
            for process in run["processes"]:
                identifiers.append(process["job_id"])
                executable = process["executable_identity"]
                assert executable["sha256"] is None and "64 MiB" in executable["hash_note"]
                assert executable["size"] > 64 * 1024 * 1024 and executable["path_matches_controller_profile"]
                assert "not this per-job manifest" in executable["full_sha256_origin"]
                assert process["os_process_creation_time"] == "not_continuously_observed"
                assert process["configuration_input"]["source_sha256"] == run["selected_configuration_sha256"]
    assert len(identifiers) == len(set(identifiers)) == 24
