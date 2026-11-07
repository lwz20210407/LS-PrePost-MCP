"""Portable checks of actual finite P08 observations, without rerunning C++."""
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path

from tools.verify_p08_mesh_roundtrip import CAPTURE_SOURCE_PATHS, CASE_IDS, case_spec, compare_typed

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "docs/decisions/evidence/p08-mesh-readback"


def evidence():
    return json.loads((FOLDER / "evidence.json").read_text(encoding="utf8"))


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


def test_actual_mesh_matrix_is_finite_source_bound_and_preserves_scope():
    data = evidence()
    assert data["status"] == "partial" and data["overall_task_accepted"] is False and data["L2_complete"] is False
    source = data["source"]
    assert source["working_tree_dirty_at_capture"] is False
    assert source["actual_git_revision"] == data["actual_git_revision"]
    identities = source["selected_source_identity"]
    assert set(identities) == set(CAPTURE_SOURCE_PATHS) and source["selected_source_count"] == len(identities)
    paths = list(identities)
    current = subprocess.check_output(["git", "hash-object", "--", *paths], cwd=ROOT, text=True, timeout=30).splitlines()
    recorded = subprocess.check_output(["git", "ls-tree", "-r", data["actual_git_revision"], "--", *paths],
                                       cwd=ROOT, text=True, timeout=30).splitlines()
    blobs = {line.split("\t", 1)[1]: line.split("\t", 1)[0].split()[2] for line in recorded}
    for path, blob in zip(paths, current, strict=True):
        identity = identities[path]
        assert blob == blobs[path] == identity["git_blob_id"], path
        raw_lf = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw_lf).hexdigest() == identity["git_lf_sha256"]
        assert re.fullmatch(r"[0-9a-f]{64}", identity["captured_file_sha256"])
    assert {(row["profile"], row["case"]) for row in data["cases"]} == {
        (profile, case) for profile in ("4.13", "4.10") for case in CASE_IDS}
    job_ids = []
    for row in data["cases"]:
        assert row["source_revision"] == data["actual_git_revision"] and row["status"] == "passed_case"
        spec = case_spec(row["case"])
        assert compare_typed(row["observed_typed"], spec) == []
        assert row["keyword_reference_comparison"]["typed_differences"] == []
        assert row["keyword_reference_comparison"]["export_differences"] == []
        assert row["keyword_reference_comparison"]["no_dangling_unverified_or_unchecked_references"] is True
        assert all(value is True for value in row["guards"]["final_guards"].values())
        assert [job["role"] for job in row["native_jobs"]] == ["gui_mesh_state", "export_keyword"]
        for job in row["native_jobs"]:
            assert job["status"] == "succeeded" and job["returncode"] == 0 and job["timed_out"] is False
            assert job["graphics"] is False and job["execution_mode"] == "nographics" and job["launch_mode"] == "c"
            assert job["process_isolation"] == "windows_job" and job["private_configuration_modified"] is False
            assert job["outer_full_sha256"] == row["executable_sha256"]
            job_ids.append(job["job_id"])
    assert len(job_ids) == len(set(job_ids)) == data["matrix"]["distinct_native_jobs"] == 32


def test_mesh_observation_gate_rejects_wrong_coordinate_or_part_membership():
    row = evidence()["cases"][0]
    observed = copy.deepcopy(row["observed_typed"])
    observed["nodes"][0][1] += 1
    assert compare_typed(observed, case_spec(row["case"]))
    observed = copy.deepcopy(row["observed_typed"])
    first = next(iter(observed["part_elements"]))
    observed["part_elements"][first] = []
    assert "typed_part_membership" in compare_typed(observed, case_spec(row["case"]))


def test_mesh_public_report_and_metadata_have_no_private_paths():
    data = evidence()
    assert hashlib.sha256((FOLDER / "report.md").read_bytes().replace(b"\r\n", b"\n")).hexdigest() == data["report_sha256_lf"]
    assert (FOLDER / "evidence.json").stat().st_size < 512 * 1024
    assert all(re.search(r"[A-Za-z]:[\\/]|\\\\[^\\]+\\", value) is None for value in strings(data))
