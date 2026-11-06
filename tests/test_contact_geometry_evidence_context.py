"""The refresh selects fresh contexts; immutable history never fills a missing one."""
import hashlib
import json
import subprocess

import pytest

from tools import contact_geometry_evidence as context
from tools import verify_p05_boundary_roundtrip as p05
from tools import verify_p12_joint_roundtrip as p12


def test_refresh_scopes_are_explicit_and_distinct_from_history():
    index = json.loads(context.INDEX.read_text(encoding="utf8"))
    assert len(context.P03_PRODUCT_PATHS) == 24 and len(context.P06_IDENTITY_PRODUCT_PATHS) == 35
    assert "src/ls_prepost_mcp/data/operations.json" in context.P03_PRODUCT_PATHS
    for paths in (context.P03_PRODUCT_PATHS, context.P06_IDENTITY_PRODUCT_PATHS, p05.PRODUCT_PATHS, p12.PRODUCT_PATHS):
        assert len(paths) == len(set(paths))
        assert {"src/ls_prepost_mcp/domain/model/contact_report.py", "src/ls_prepost_mcp/domain/model/contact.py"} <= set(paths)
    assert len(p05.CAPTURE_SOURCE_PATHS) == len(p12.CAPTURE_SOURCE_PATHS) == 43
    for task in index["current"]:
        assert context.evidence_path(task).is_relative_to(context.INDEX.parent)
        if task in index["historical"]:
            assert context.evidence_path(task) != context.evidence_path(task, historical=True)


@pytest.mark.parametrize("task", ["P03", "P05", "P12", "P06_identity"])
def test_historical_context_references_pin_original_git_lf_bytes(task):
    index = json.loads(context.INDEX.read_text(encoding="utf8"))
    selected = index["historical"][task]
    raw = subprocess.check_output(["git", "show", index["historical_container_reference_revision"] + ":" + selected["path"]],
                                  cwd=context.ROOT, timeout=15)
    assert hashlib.sha256(raw).hexdigest() == selected["sha256_lf"]
    context.read_evidence(task, historical=True)


@pytest.mark.parametrize("task", ["P03", "P06_identity"])
@pytest.mark.parametrize("name", ["contact_report.py", "contact.py"])
def test_host_gate_rejects_missing_consumed_contact_helper(task, name):
    paths = context.P03_PRODUCT_PATHS if task == "P03" else context.P06_IDENTITY_PRODUCT_PATHS
    incomplete = dict(product_source_identity=[dict(path=path) for path in paths if not path.endswith("/" + name)])
    with pytest.raises(AssertionError, match="consumed host dependency"):
        context.require_host_products(incomplete, task)


def test_missing_current_file_does_not_fall_back_to_available_history(tmp_path, monkeypatch):
    history = tmp_path / "history.json"
    history.write_text("{}", encoding="utf8")
    monkeypatch.setattr(context, "evidence_path", lambda task, historical=False:
                        history if historical else tmp_path / "missing-actual-capture.json")
    with pytest.raises(FileNotFoundError, match="Missing actual current.*historical evidence cannot substitute"):
        context.read_evidence("P03")


def test_p03_current_scope_requires_operations_data_in_the_explicit_capture():
    incomplete = dict(product_source_identity=[dict(path=path) for path in context.P03_PRODUCT_PATHS
                                               if path != "src/ls_prepost_mcp/data/operations.json"])
    with pytest.raises(AssertionError, match="consumed host dependency"):
        context.require_host_products(incomplete, "P03")


def test_current_geometry_host_capture_binds_its_own_protocol_test_and_actual_sources():
    evidence = context.read_evidence("P06_geometry")
    assert evidence["status"] == "partial" and evidence["verification_level"] == "L1"
    assert evidence["native_executed"] is False and evidence["working_tree_dirty"] is False
    assert all(case["passed"] for case in evidence["l1_run"]["cases"])
    assert evidence["l1_run"]["passed"] == len(evidence["l1_run"]["cases"])
    products = {item["path"] for item in evidence["product_source_identity"]}
    assert {"src/ls_prepost_mcp/domain/model/contact_report.py", "src/ls_prepost_mcp/domain/model/contact.py",
            "src/ls_prepost_mcp/domain/model/geometry.py", "src/ls_prepost_mcp/domain/model/operations.py",
            "src/ls_prepost_mcp/model_target_tools.py"} <= products
    assert "tests/test_contact_geometry_mcp.py" in {item["path"] for item in evidence["test_source_identity"]}
    for key in ("product_source_identity", "test_source_identity"):
        for item in evidence[key]:
            recorded = subprocess.check_output(["git", "rev-parse", evidence["actual_git_revision"] + ":" + item["path"]],
                                               cwd=context.ROOT, text=True, timeout=15).strip()
            current = subprocess.check_output(["git", "hash-object", item["path"]], cwd=context.ROOT, text=True, timeout=15).strip()
            assert recorded == current == item["git_blob_id"], item["path"]
