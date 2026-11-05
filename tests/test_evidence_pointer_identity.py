"""Historical raw identities and portable Git identities must be distinguishable."""
import hashlib
import json
import subprocess

import pytest


def test_family_pointer_history_identifies_raw_crlf_and_the_archived_git_lf_blob(pytestconfig):
    root = pytestconfig.rootpath
    evidence = json.loads((root / "docs/decisions/evidence/p11-save/evidence.json").read_text(encoding="utf8"))
    snapshots = [item for item in evidence["active_product_evidence_history"]
                 if item["path"] == "docs/decisions/evidence/p11-family-refresh/evidence.json"]
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.get("sha256_convention") == "captured_working_tree_bytes_crlf", (
        "Pointer history must describe switch-time raw bytes separately from the archived Git LF identity")
    repository = snapshot.get("repository_lf_identity")
    assert repository and repository.get("added_as") == "post_capture_archival_metadata_not_native_measurement"
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=root,
                             capture_output=True, text=True, timeout=10)
    if shallow.returncode or shallow.stdout.strip() == "true":
        pytest.skip("Historical Git evidence identities require a complete Git checkout")
    object_name = repository["git_revision"] + ":" + snapshot["path"]
    blob = subprocess.check_output(["git", "show", object_name], cwd=root, timeout=10)
    blob_id = subprocess.check_output(["git", "rev-parse", object_name], cwd=root, text=True, timeout=10).strip()
    assert blob_id == repository["git_blob_id"]
    assert b"\r\n" not in blob
    assert hashlib.sha256(blob).hexdigest() == repository["sha256"]
    # This particular one-line JSON was captured with Windows CRLF. Rebuilding
    # that byte form verifies the original field without changing its meaning.
    assert hashlib.sha256(blob.replace(b"\n", b"\r\n")).hexdigest() == snapshot["sha256"]
