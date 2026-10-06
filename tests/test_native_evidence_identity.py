"""I04 report provenance includes staged, unstaged and untracked source edits."""

import hashlib
import subprocess

from tools.native_regression import execution_identity


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL)


def test_identity_matches_actual_revision_and_combined_diff(tmp_path):
    git(tmp_path, "init")
    git(tmp_path, "config", "core.autocrlf", "false")
    (tmp_path / "src").mkdir()
    source = tmp_path / "src/example.py"
    source.write_bytes(b"VALUE = 1\n")
    git(tmp_path, "add", "src/example.py")
    git(tmp_path, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture")
    head = git(tmp_path, "rev-parse", "HEAD").decode().strip()
    clean = execution_identity(tmp_path)
    assert clean["actual_git_head"] == head and clean["working_tree_dirty"] is False
    assert clean["git_diff_sha256"] == hashlib.sha256(b"").hexdigest()
    source.write_bytes(b"VALUE = 2\n")
    git(tmp_path, "add", "src/example.py")
    source.write_bytes(b"VALUE = 3\n")
    dirty = execution_identity(tmp_path)
    assert dirty["actual_git_head"] == head and dirty["working_tree_dirty"] is True
    assert dirty["git_diff_sha256"] == hashlib.sha256(git(tmp_path, "diff", "HEAD", "--binary")).hexdigest()
    assert dirty["source_files"]["src/example.py"] == hashlib.sha256(source.read_bytes()).hexdigest()
    (tmp_path / "src/untracked.py").write_bytes(b"VALUE = 4\n")
    untracked = execution_identity(tmp_path)
    assert untracked["git_diff_sha256"] == dirty["git_diff_sha256"]
    assert untracked["source_snapshot_sha256"] != dirty["source_snapshot_sha256"]
    assert "src/untracked.py" in untracked["source_files"]


def test_nested_noncheckout_does_not_claim_parent_git_revision(tmp_path):
    git(tmp_path, "init")
    child = tmp_path / "unpacked-source"
    child.mkdir()
    result = execution_identity(child)
    assert result["actual_git_head"] is None and result["working_tree_dirty"] is None
    assert result["git_diff_sha256"] is None


def test_git_timeout_keeps_source_fingerprint_and_marks_revision_unavailable(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/example.py").write_bytes(b"VALUE = 1\n")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("git", 10)

    monkeypatch.setattr("tools.native_regression.subprocess.check_output", timeout)
    result = execution_identity(tmp_path)
    assert result["actual_git_head"] is None and result["git_diff_sha256"] is None
    assert result["source_files"]["src/example.py"] == hashlib.sha256(b"VALUE = 1\n").hexdigest()
