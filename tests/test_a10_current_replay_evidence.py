"""Validate the public historical replay without freezing stale aggregate scores."""

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from tools.refresh_knowledge_evidence import PRODUCT_PATHS, SETS, check_active_product_sources, validate_suite

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/decisions/evidence/a10-control-recipes-refresh"


def artifacts():
    evidence = json.loads((EVIDENCE / "evidence.json").read_text(encoding="utf8"))
    markdown = (EVIDENCE / "summary.md").read_text(encoding="utf8")
    tables = {key: (EVIDENCE / (key + "-top3.md")).read_text(encoding="utf8") for key in SETS}
    return evidence, markdown, tables


def test_current_public_replay_artifacts_and_frozen_questions_are_consistent():
    evidence, markdown, tables = artifacts()
    validate_suite(evidence, markdown, tables)
    assert evidence["status"] == "partial" and evidence["verification_level"] == "L1"
    assert evidence["working_tree_dirty"] is False
    assert evidence["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
    assert set(evidence["index"]["visibility"]) == {"public"}
    assert evidence["index"]["categories"].get("api", 0) == 0
    for record in evidence["sets"].values():
        categories = record["category_totals"]
        for category, total in categories.items():
            rows = [row for row in record["run"]["results"] if row["category"] == category]
            assert total == dict(queries=len(rows), hits_at_3=sum(row["hit_at_3"] for row in rows))
        assert categories["api"]["queries"] > 0 and categories["api"]["hits_at_3"] == 0
    text = json.dumps(evidence, ensure_ascii=False)
    assert "F:\\" not in text and "C:\\" not in text and "D:\\" not in text
    assert "private_supplement" not in text


def test_evidence_checker_catches_stale_summary_and_reference_tables():
    evidence, markdown, tables = artifacts()
    record = evidence["sets"]["holdout_24"]
    record["run"]["hits_at_3"] += 1
    with pytest.raises(ValueError, match="total"):
        validate_suite(evidence, markdown, tables)
    evidence, markdown, tables = artifacts()
    with pytest.raises(ValueError, match="Summary Markdown"):
        validate_suite(evidence, markdown + "stale", tables)
    stale = deepcopy(tables)
    stale["legacy_20"] += "stale"
    with pytest.raises(ValueError, match="Markdown"):
        validate_suite(evidence, markdown, stale)


def test_active_product_binding_rejects_source_drift_even_with_valid_historical_records(tmp_path):
    identities = []
    for relative in PRODUCT_PATHS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"public product fixture\r\n")
        identities.append(dict(path=relative, sha256_lf=hashlib.sha256(b"public product fixture\n").hexdigest()))
    evidence = dict(product_source_identity=identities)
    check_active_product_sources(evidence, tmp_path)
    (tmp_path / PRODUCT_PATHS[0]).write_bytes(b"changed retrieval implementation\n")
    with pytest.raises(ValueError, match="stale after product source change"):
        check_active_product_sources(evidence, tmp_path)


def test_active_product_binding_rejects_omitted_control_pin_source(tmp_path):
    identities = []
    for relative in PRODUCT_PATHS:
        if relative == "src/ls_prepost_mcp/domain/model/controls.py":
            continue
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"public product fixture\n")
        identities.append(dict(path=relative, sha256_lf=hashlib.sha256(path.read_bytes()).hexdigest()))
    with pytest.raises(ValueError, match="every retrieval product source"):
        check_active_product_sources(dict(product_source_identity=identities), tmp_path)


def test_index_input_declarations_cover_each_actual_model_pin_source(tmp_path):
    from ls_prepost_mcp.model_recipes import load_registry
    from tools.refresh_knowledge_evidence import MODEL_RECIPE_INPUT_PATHS, index_input_paths

    _, _, _, identity = load_registry()
    pin_sources = {row["locator"].removeprefix("repo://") for row in identity.values()}
    assert "src/ls_prepost_mcp/domain/model/controls.py" in pin_sources
    assert len(pin_sources) == 6 and pin_sources == set(MODEL_RECIPE_INPUT_PATHS)
    assert len(PRODUCT_PATHS) == 12 and pin_sources <= set(PRODUCT_PATHS)
    declared = index_input_paths(tmp_path)
    assert len(declared) == len(set(declared)) and pin_sources <= set(declared)


def test_evidence_has_product_runner_query_and_corpus_blob_identities():
    evidence, _, _ = artifacts()
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
                             capture_output=True, text=True, timeout=15)
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Historical A10 source identity needs complete Git history")
    groups = [(evidence["actual_git_revision"], records) for records in (
        evidence["product_source_identity"], evidence["runner_source_identity"], evidence["test_source_identity"],
        [record["questions"] for record in evidence["sets"].values()])]
    build = evidence["index"]["build"]
    groups.append((build["actual_git_revision"], build["input_source_identity"]))
    for revision, records in groups:
        for identity in records:
            ref = revision + ":" + identity["path"]
            blob = subprocess.check_output(["git", "rev-parse", ref], cwd=ROOT, text=True, timeout=15).strip()
            data = subprocess.check_output(["git", "show", ref], cwd=ROOT, timeout=15)
            assert blob == identity["git_blob"]
            assert hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest() == identity["sha256_lf"]
            if identity in evidence["product_source_identity"]:
                current_blob = subprocess.check_output(["git", "rev-parse", "HEAD:" + identity["path"]],
                                                       cwd=ROOT, text=True, timeout=15).strip()
                assert current_blob == blob, "Active A10 evidence needs replay after product source changes"
