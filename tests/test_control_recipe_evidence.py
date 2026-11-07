"""Current P10 evidence is source-bound; archived material evidence stays immutable."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

from tools.contact_geometry_evidence import evidence_path, read_evidence

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/decisions/evidence/p10-control-output/evidence.json"


def strings(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, str):
        yield value


def test_control_recipe_evidence_retains_actual_scope_and_explicit_native_projection():
    from tools.verify_p10_control_roundtrip import CAPTURE_SOURCE_PATHS, fixture

    data = json.loads(EVIDENCE.read_text(encoding="utf8"))
    assert data["status"] == "partial" and data["task_acceptance_complete"] is False
    assert data["working_tree_dirty"] is False and data["native_executed"] is True
    assert data["typed_control_recognition"] == "unverified" and data["physical_response"] == "not_run"
    assert data["host"]["passed"] == len(data["host"]["cases"]) > 0
    assert all(row["passed"] for row in data["host"]["cases"])
    assert data["regression"]["actual_git_revision"] == "21978f8fd58a359754636503392cf4bb888d7b1d"
    assert data["regression"]["working_tree_dirty"] is False and data["regression"]["failed"] == 2
    expected = fixture()["expected"]["controls"]
    assert {row["profile"] for row in data["native_runs"]} == {"4.13", "4.10"}
    jobs = []
    for run in data["native_runs"]:
        assert run["actual_git_revision"] == data["actual_git_revision"] and run["working_tree_dirty"] is False
        assert run["creation_mode"] == "recipe" and run["recipe_reference"].startswith("model:control-output@")
        assert run["status"] == "passed" and run["differences"] == [] and all(run["guards"].values())
        assert run["explicit_expected"] == expected
        assert set(run["explicit_readback"]) == set(expected)
        for keyword, fields in expected.items():
            for name, value in fields.items():
                actual = run["explicit_readback"][keyword][name]
                assert type(actual) in (int, float) and abs(actual - value) <= 1e-13 + 1e-8 * abs(value)
        assert len(run["native_job_ids"]) == 3 and len(set(run["native_job_ids"])) == 3
        jobs += run["native_job_ids"]
    assert len(jobs) == len(set(jobs)) == 6
    sources = {item["path"]: item for item in data["capture_source_identity"]}
    assert set(sources) == set(CAPTURE_SOURCE_PATHS)
    for path, identity in sources.items():
        current = subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True, timeout=15).strip()
        recorded = subprocess.check_output(["git", "rev-parse", data["actual_git_revision"] + ":" + path],
                                           cwd=ROOT, text=True, timeout=15).strip()
        assert current == recorded == identity["git_blob_id"], path
        assert hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == identity["sha256_lf"]


def test_new_control_contexts_have_reports_and_preserve_prior_capture_bytes():
    data = json.loads(EVIDENCE.read_text(encoding="utf8"))
    p03 = read_evidence("P03")
    for path, evidence in ((EVIDENCE, data), (evidence_path("P03"), p03)):
        assert len(path.read_bytes()) < 512 * 1024
        report = path.with_name(evidence["report"]).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(report).hexdigest() == evidence["report_sha256_lf"]
        assert all(re.search(r"[A-Za-z]:[\\/]|\\\\[^\\]+\\", item) is None for item in strings(evidence))
    for record in data["preserved_historical_files"]:
        raw = (ROOT / record["path"]).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == record["sha256_lf"]
