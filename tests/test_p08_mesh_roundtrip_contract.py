"""Offline P08 fixtures and handwritten geometry/reference contracts, never native."""
import copy

import pytest


def test_eight_bounded_literal_oracles_cover_original_operations():
    from tools import verify_p08_mesh_roundtrip as verifier

    cases = verifier.fixture()["cases"]
    assert {c["id"] for c in cases} == {"translate", "rotate", "reflect", "copy", "merge", "normals", "renumber", "delete"}
    for case in cases:
        verifier.validate_case(case)
        assert len(case["input"]["nodes"]) <= 32 and len(case["expected"]["nodes"]) <= 32


def test_source_admission_precedes_profile_and_output(tmp_path, monkeypatch):
    from tools import verify_p08_mesh_roundtrip as verifier

    monkeypatch.setattr(verifier, "source_identity", lambda *a, **kw: (_ for _ in ()).throw(ValueError("source refused")))
    with pytest.raises(ValueError, match="source refused"):
        verifier.prepare_case(tmp_path / "must-not-exist", "translate", {})
    assert not (tmp_path / "must-not-exist").exists()


def test_pilot_user_labels_cannot_coincide_with_internal_one_based_indices():
    from tools import verify_p08_mesh_roundtrip as verifier

    for case in verifier.fixture()["cases"]:
        for data in (case["input"], case["expected"]):
            assert {r["id"] for r in data["parts"]} == {13, 29}
            assert min(r[0] for r in data["nodes"]) > len(data["nodes"])
            assert min(r["id"] for r in data["elements"]) > len(data["elements"])


@pytest.mark.parametrize("case_id", ["translate", "rotate", "reflect", "copy", "merge", "normals", "renumber", "delete"])
def test_offline_public_mesh_ops_matches_independent_tables(tmp_path, monkeypatch, case_id):
    pytest.importorskip("ansys.dyna.core")
    from tools import verify_p08_mesh_roundtrip as verifier

    monkeypatch.setattr(verifier, "source_identity", lambda *a, **kw: {"offline_test": True})
    prepared = verifier.prepare_case(tmp_path / case_id, case_id, {})
    assert prepared["creation"]["operation"] == "mesh_ops" and prepared["creation"]["status"] == "succeeded"
    assert verifier.compare_export(prepared["edited"], prepared["spec"]) == []
    assert prepared["source"].read_bytes() == prepared["source_bytes"]


def test_changed_observation_does_not_refill_expected_or_hide_sentinel_change(tmp_path):
    pytest.importorskip("ansys.dyna.core")
    from tools import verify_p08_mesh_roundtrip as verifier

    case = verifier.case_spec("translate")
    original = copy.deepcopy(case["expected"])
    path = tmp_path / "changed.k"
    observed = copy.deepcopy(original)
    observed["nodes"][0][1] += .01  # unselected sentinel
    path.write_text(verifier.source_text(observed), encoding="ascii")
    assert verifier.compare_export(path, case)
    assert case["expected"] == original


def test_one_job_retention_is_not_claimed_as_typed_geometry():
    from tools import verify_p08_mesh_roundtrip as verifier

    plan = verifier.job_plan()
    assert plan["retention_only"]["native_jobs_per_case"] == 1
    assert plan["typed_geometry"]["native_jobs_per_case"] == 2
    assert plan["typed_geometry"]["headless_abi_verified"] is False
    assert plan["native_executed"] is False


def test_native_flag_cannot_dispatch_during_offline_preparation(tmp_path, monkeypatch):
    from tools import verify_p08_mesh_roundtrip as verifier

    monkeypatch.setattr(verifier, "execution_identity", lambda *a: {})
    monkeypatch.setattr(verifier, "source_identity", lambda *a, **kw: {})
    with pytest.raises(ValueError, match="offline preparation"):
        verifier.main(["--output", str(tmp_path / "never"), "--expected-head", "a" * 40,
                       "--expected-source-snapshot", "b" * 64, "--run-native"])
    assert not (tmp_path / "never").exists()
