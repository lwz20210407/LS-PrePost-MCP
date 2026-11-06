"""The P06 identity claim is source-bound and stays separate from native geometry."""
import hashlib
import importlib.metadata
import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "docs/decisions/evidence/p06-contact-identities"
PATH = FOLDER / "evidence.json"


def _git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf8", timeout=20)


@lru_cache(maxsize=None)
def _recorded_tree(revision):
    if _git("rev-parse", "--is-shallow-repository").strip() == "true":
        pytest.skip("Historical source objects require full Git checkout")
    lines = _git("ls-tree", "-r", revision).splitlines()
    return {line.split("\t", 1)[1]: line.split("\t", 1)[0].split()[2] for line in lines}


def _current_blobs(data):
    paths = [item["path"] for key in ("product_source_identity", "test_source_identity") for item in data[key]]
    return dict(zip(paths, _git("hash-object", "--", *paths).splitlines(), strict=True))


def _assert_bindings(data, current):
    recorded = _recorded_tree(data["actual_git_revision"])
    assert len(data["product_source_identity"]) == 34 and len(data["test_source_identity"]) == 4
    assert "src/ls_prepost_mcp/domain/model/contacts.py" in current
    for key in ("product_source_identity", "test_source_identity"):
        for item in data[key]:
            assert recorded[item["path"]] == item["git_blob_id"]
            assert current[item["path"]] == item["git_blob_id"], "P06 contact identity evidence source drift: " + item["path"]
            assert re.fullmatch(r"[0-9a-f]{64}", item["sha256_actual"])


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


def test_contact_identity_evidence_binds_current_sources_and_historical_test_objects():
    data = json.loads(PATH.read_text(encoding="utf8"))
    _assert_bindings(data, _current_blobs(data))
    try:
        provider = importlib.metadata.version(data["provider_name"])
    except importlib.metadata.PackageNotFoundError:
        pass
    else:
        assert provider == data["provider_version"]


@pytest.mark.parametrize("path", ["src/ls_prepost_mcp/domain/model/contacts.py",
                                  "src/ls_prepost_mcp/domain/model/_identity.py",
                                  "tests/data/p06-contact-identity-golden.json"])
def test_contact_identity_evidence_rejects_changed_product_or_golden(path):
    data = json.loads(PATH.read_text(encoding="utf8"))
    current = _current_blobs(data)
    current[path] = "0" * 40
    with pytest.raises(AssertionError, match="source drift"):
        _assert_bindings(data, current)


def test_contact_identity_evidence_does_not_upgrade_scope_or_hide_iterations():
    data = json.loads(PATH.read_text(encoding="utf8"))
    assert data["status"] == "partial" and data["verification_level"] == "L1" and data["native_executed"] is False
    assert data["working_tree_dirty"] is False and data["source_unchanged"] is True
    assert data["actual_git_revision"] == "85c707699b90a336969d102e767c6d7a9080277f"
    assert data["l1_run"]["passed"] == len(data["l1_run"]["cases"]) == 87
    assert all(case["passed"] for case in data["l1_run"]["cases"])
    assert data["original_main_regression"]["failed"] == 28
    assert data["ambiguous_collection_regression"]["failed"] == 3
    assert data["invalidated_test_iteration"]["second_product_defect_claimed"] is False
    assert data["ambiguous_collection_regression"]["clean_checkout_claimed"] is False
    assert data["previous_capture"]["superseded_for_current_contacts_source"] is True
    assert data["nested_mapping_review"]["old_failed"] == 2
    assert data["nested_mapping_review"]["final_independent_controls_passed"] == 4
    assert data["nested_mapping_review"]["final_product_revision"] == data["actual_git_revision"]
    assert data["optional_provider_absent"]["passed"] == 11 and data["optional_provider_absent"]["skipped"] == 54
    assert data["golden"]["cases"] == 5


def test_contact_identity_report_hash_and_public_metadata_exclude_private_paths():
    raw = PATH.read_text(encoding="utf8")
    data = json.loads(raw)
    report = (FOLDER / data["report"]).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(report).hexdigest() == data["report_sha256_lf"]
    assert all(re.search(r"[A-Za-z]:[\\/]|\\\\[^\\]+\\", value) is None for value in _strings(data))
