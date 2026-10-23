"""No synthetic passed verdicts for legal unsupported variants or mixed-revision ledgers."""
import collections
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/decisions/evidence/i04-variant-review02"


def test_focused_run_and_frozen_ledger_keep_product_failures_explicit():
    data = json.loads((DIRECTORY / "evidence.json").read_text(encoding="utf8"))
    rows = data["focused_cases"]
    assert len(rows) == 15 and data["status"] == "partial"
    assert collections.Counter(r["status"] for r in rows) == data["focused_outcomes"]
    variants = [r for r in rows if r["input_classification"] == "product_unsupported_include_variant"]
    assert len(variants) == 11
    assert all(r["status"] == "failed" and r["native_reference_status"] == "succeeded" for r in variants)
    assert sum(r["native_processes"] for r in rows) == data["native_processes"] == 366
    assert all(r["all_processes_headless_clean_exit"] and r["source_unchanged"] and r["source_directory_listing_unchanged"] for r in rows)
    assert {r["case"] for r in rows if r["status"] == "passed"} == {"extra-keyword-025", "extra-keyword-063", "extra-keyword-082"}
    ledger = data["frozen_ledger"]
    assert len(ledger) == len({r["case"] for r in ledger}) == 100
    assert collections.Counter(r["latest_status"] for r in ledger) == data["latest_mixed_revision_outcomes"]
    assert collections.Counter(r["corrected_historical_status"] for r in ledger) == data["corrected_historical_outcomes"]
    assert sum(r["scope"] == "focused_review02_rerun" for r in ledger) == len(rows)
    text = (DIRECTORY / data["report"]).read_text(encoding="utf8")
    assert hashlib.sha256(text.encode()).hexdigest() == data["report_sha256"]
    table = [line.split("|") for line in text.splitlines() if line.startswith("| extra-")]
    assert {r[1].strip(): r[4].strip() for r in table} == {r["case"]: r["latest_status"] for r in ledger}


def test_focused_native_evidence_binds_actual_product_revision():
    probe = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, text=True, capture_output=True)
    if probe.returncode or probe.stdout.strip() == "true":
        pytest.skip("Native source provenance needs full Git history")
    data = json.loads((DIRECTORY / "evidence.json").read_text(encoding="utf8"))
    assert not data["working_tree_dirty"] and data["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
    for item in [*data["product_source_identity"], data["test_source_identity"]]:
        actual = subprocess.check_output(["git", "rev-parse", data["actual_git_revision"]+":"+item["path"]], cwd=ROOT, text=True).strip()
        assert actual == item["git_blob_id"]
