"""Future P12 captures must bind the real matching/identity dependency before native IO."""

import hashlib
from types import SimpleNamespace

import pytest

import tools.verify_p12_joint_roundtrip as verifier
from tools.native_regression import execution_identity

MATCHING = "src/ls_prepost_mcp/domain/model/matching.py"
IDENTITY = "src/ls_prepost_mcp/domain/model/_identity.py"


@pytest.mark.parametrize("missing", [MATCHING, IDENTITY])
def test_missing_required_source_is_rejected_before_native_or_configuration_io(tmp_path, missing):
    identity = execution_identity(verifier.ROOT)
    identity["working_tree_dirty"] = False  # isolate the source gate from the existing dirty-tree guard
    del identity["source_files"][missing]

    def forbidden():
        pytest.fail("No executable/configuration IO may precede the required source check")

    prepared = dict(service=SimpleNamespace(settings=SimpleNamespace(native_executable=forbidden)),
                    source=tmp_path / "unused-input.k", edited=tmp_path / "unused-edited.k")
    with pytest.raises(ValueError, match="Missing required capture source"):
        verifier.verify_native(prepared, identity)


@pytest.fixture
def source_fixture(tmp_path, monkeypatch):
    paths = (MATCHING, IDENTITY, "tools/verify_p12_joint_roundtrip.py")
    for path in paths:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# owned source fixture\n", encoding="utf8")
    identity = dict(actual_git_head="a" * 40, source_files={
        p: hashlib.sha256((tmp_path / p).read_bytes()).hexdigest() for p in paths})
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    monkeypatch.setattr(verifier, "CAPTURE_SOURCE_PATHS", paths)
    tree = "".join("100644 blob " + "b" * 40 + "\t" + p + "\n" for p in paths)
    monkeypatch.setattr(verifier.subprocess, "check_output", lambda *a, **kw: tree)
    return paths, identity


def test_required_dependency_set_explicitly_includes_matching_and_exact_identity():
    assert MATCHING in verifier.PRODUCT_PATHS and IDENTITY in verifier.PRODUCT_PATHS
    assert "src/ls_prepost_mcp/domain/model/deck.py" in verifier.PRODUCT_PATHS


def test_source_gate_binds_both_git_blob_and_actual_captured_bytes(source_fixture):
    paths, identity = source_fixture
    found = verifier.capture_source_identity(identity)
    assert set(found) == set(paths)
    assert all(found[p] == dict(git_blob_id="b" * 40, captured_file_sha256=identity["source_files"][p])
               for p in paths)


@pytest.mark.parametrize("fault", ["missing_disk", "changed_bytes", "missing_capture", "missing_git_blob"])
def test_source_gate_rejects_missing_or_changed_dependencies(source_fixture, monkeypatch, fault):
    _, identity = source_fixture
    if fault == "missing_disk":
        monkeypatch.setattr(verifier, "CAPTURE_SOURCE_PATHS", (MATCHING, "src/absent.py"))
        identity["source_files"]["src/absent.py"] = "c" * 64
    elif fault == "changed_bytes":
        (verifier.ROOT / MATCHING).write_text("# changed after identity capture\n", encoding="utf8")
    elif fault == "missing_capture":
        del identity["source_files"][MATCHING]
    else:
        monkeypatch.setattr(verifier.subprocess, "check_output", lambda *a, **kw: "")
    with pytest.raises(ValueError):
        verifier.capture_source_identity(identity)


def test_source_gate_cannot_accept_an_unresolvable_revision(source_fixture, monkeypatch):
    _, identity = source_fixture

    def missing_object(*args, **kwargs):
        raise verifier.subprocess.CalledProcessError(128, "git ls-tree")

    monkeypatch.setattr(verifier.subprocess, "check_output", missing_object)
    with pytest.raises(ValueError, match="committed capture source"):
        verifier.capture_source_identity(identity)
