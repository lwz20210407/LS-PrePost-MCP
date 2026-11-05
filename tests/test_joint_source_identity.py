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


class _AfterVersionPolicy(RuntimeError):
    """Stop an entry point before preparation, configuration access or execution."""


def _profile_entry(monkeypatch, tmp_path, entry, version, resource):
    from ls_prepost_mcp.native import versions

    monkeypatch.setattr(versions, "read_version_resource", lambda exe: resource)
    observed = []

    def installation(executable, version=None):
        policy = versions.require_installation(executable, version)
        observed.append(dict(call="installation", profile=dict(policy)))
        return policy

    def capability(executable, name):
        assert name == "batch"
        policy = versions.require_capability(executable, name)
        observed.append(dict(call="batch", profile=dict(policy)))
        return policy

    def stop(*args, **kwargs):
        raise _AfterVersionPolicy("No preparation or native execution in this test")

    executable = tmp_path / ("lsprepost" + version + ".exe")
    if entry == "cli":
        monkeypatch.setattr(verifier, "require_installation", installation)
        monkeypatch.setattr(verifier, "require_capability", capability)
        monkeypatch.setattr(verifier, "execution_identity", stop)
        monkeypatch.setattr("sys.argv", ["verify_p12_joint_roundtrip.py", "--case", "pilot", "--run-native",
            "--profile", version, "--executable", str(executable), "--output", str(tmp_path / "unused-output")])
        return verifier.main, observed
    from tests import test_joint_native_readback as native_case

    monkeypatch.setattr(native_case, "require_installation", installation)
    monkeypatch.setattr(native_case, "require_capability", capability, raising=False)
    monkeypatch.setattr(native_case, "prepare_case", stop)
    def invoke():
        return native_case.test_native_joint_definition_roundtrip(
            (executable, {"version": version}, None), SimpleNamespace(_native_root=tmp_path), lambda *a: None, "pilot")

    return invoke, observed


@pytest.mark.parametrize("entry", ["cli", "pytest"])
@pytest.mark.parametrize("version,fixed,conflict", [("4.10", "4.9.0.1", True), ("4.13", "4.13.0.1", False)])
def test_native_entry_uses_central_batch_policy_without_rejecting_accepted_fixed_resource(
        monkeypatch, tmp_path, entry, version, fixed, conflict):
    resource = dict(product_name="LS-PrePost", file_version=version + ".0.1",
                    product_version=version + ".0.1", fixed_file_version=fixed)
    invoke, observed = _profile_entry(monkeypatch, tmp_path, entry, version, resource)
    with pytest.raises(_AfterVersionPolicy):
        invoke()
    assert [item["call"] for item in observed] == ["installation", "batch"]
    assert all(item["profile"]["resource_conflict"] is conflict for item in observed)
    assert all(item["profile"]["fixed_file_version"] == fixed for item in observed)


@pytest.mark.parametrize("entry", ["cli", "pytest"])
@pytest.mark.parametrize("fault", ["string_conflict", "label_conflict", "excluded", "unrecognized_source"])
def test_native_entry_retains_central_rejections_and_requires_a_file_resource(monkeypatch, tmp_path, entry, fault):
    resource = dict(product_name="LS-PrePost", file_version="4.10.0.1",
                    product_version="4.10.0.1", fixed_file_version="4.9.0.1")
    if fault == "string_conflict":
        resource["product_version"] = "4.13.0.1"
    elif fault in ("label_conflict", "excluded"):
        family = "4.13" if fault == "label_conflict" else "4.11"
        resource.update(file_version=family + ".0.1", product_version=family + ".0.1",
                        fixed_file_version=family + ".0.1")
    else:
        resource = None
    invoke, observed = _profile_entry(monkeypatch, tmp_path, entry, "4.10", resource)
    rejection = (SystemExit if entry == "cli" else AssertionError) if fault == "unrecognized_source" else ValueError
    with pytest.raises(rejection):
        invoke()
    assert not any(item["call"] == "batch" for item in observed)
