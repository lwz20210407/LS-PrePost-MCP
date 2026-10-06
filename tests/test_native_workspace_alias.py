"""Windows alias ownership, preference isolation and source preservation."""

import os
from unittest.mock import MagicMock

import pytest

from ls_prepost_mcp.engine import BatchEngine, BatchJob
from ls_prepost_mcp.engine.environment import native_environment
from ls_prepost_mcp.engine.workspace import native_workspace

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows directory junctions")


@pytest.mark.parametrize("fail", [False, True])
def test_alias_cleanup_preserves_the_actual_job_tree(tmp_path, monkeypatch, fail):
    root = tmp_path / "aliases"
    root.mkdir()
    job = tmp_path / "中文 作业"
    job.mkdir()
    original = b"unchanged source bytes"
    (job / "input.k").write_bytes(original)
    monkeypatch.setenv("LSPP_NATIVE_ALIAS_ROOT", str(root))
    try:
        with native_workspace(job) as alias:
            assert str(alias).isascii() and alias.resolve() == job
            assert (alias / "input.k").read_bytes() == original
            (alias / "result.json").write_bytes(b"{}")
            if fail:
                raise RuntimeError("domain failed")
    except RuntimeError as exc:
        assert fail and str(exc) == "domain failed"
    assert (job / "input.k").read_bytes() == original
    assert (job / "result.json").read_bytes() == b"{}"
    assert list(root.iterdir()) == [] and not alias.exists()


def test_alias_preferences_keep_original_config_and_use_ascii_paths(tmp_path, monkeypatch):
    root = tmp_path / "aliases"
    root.mkdir()
    job = tmp_path / "中文 作业"
    job.mkdir()
    source = tmp_path / "user-lsppconf"
    original = b"*\npython_home = original\nconsent = YES\nopaque = \xff\n"
    source.write_bytes(original)
    monkeypatch.setenv("LSPP_NATIVE_ALIAS_ROOT", str(root))
    with native_workspace(job) as alias:
        env, meta = native_environment(tmp_path / "lspp.exe", job,
            {"LSPP_CONFIG_SOURCE": str(source)}, batch=True, execution_directory=alias)
        assert env["LSTC_FILE"] == str(alias / "native-config")
        assert env["TEMP"] == env["TMP"] == str(alias / "tmp")
        private = (job / "native-config/lsppconf").read_bytes()
        assert b"opaque = \xff\n" in private
        assert b"working_directory = .\n" in private
        assert ("message_file = " + (alias / "lspost.msg").as_posix()).encode() in private
        assert meta["source_modified"] is False
    assert source.read_bytes() == original


def test_unconfigured_workspace_is_unchanged_and_foreign_alias_is_rejected(tmp_path, monkeypatch):
    job = tmp_path / "中文 作业"
    job.mkdir()
    monkeypatch.delenv("LSPP_NATIVE_ALIAS_ROOT", raising=False)
    with native_workspace(job) as actual:
        assert actual == job
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    with pytest.raises(ValueError, match="resolve to this"):
        native_environment(tmp_path / "lspp.exe", job, {}, batch=True, execution_directory=foreign)
    assert not (job / "native-config").exists()


@pytest.mark.parametrize("root_name", ["中文根", "job"])
def test_invalid_alias_root_does_not_create_a_link(tmp_path, monkeypatch, root_name):
    job = tmp_path / "中文 作业"
    job.mkdir()
    root = job if root_name == "job" else tmp_path / root_name
    root.mkdir(exist_ok=True)
    monkeypatch.setenv("LSPP_NATIVE_ALIAS_ROOT", str(root))
    with pytest.raises(ValueError, match="ASCII|outside"):
        with native_workspace(job):
            pytest.fail("Invalid root must be rejected before execution")
    assert not list(job.iterdir())


def test_replaced_alias_is_retained_instead_of_deleting_foreign_contents(tmp_path, monkeypatch):
    root = tmp_path / "aliases"
    root.mkdir()
    job = tmp_path / "中文 作业"
    job.mkdir()
    (job / "input.k").write_bytes(b"keep original")
    monkeypatch.setenv("LSPP_NATIVE_ALIAS_ROOT", str(root))
    with pytest.raises(RuntimeError, match="identity changed"):
        with native_workspace(job) as alias:
            alias.rmdir()
            alias.mkdir()
            (alias / "replacement.txt").write_bytes(b"keep replacement")
    assert (job / "input.k").read_bytes() == b"keep original"
    assert (alias / "replacement.txt").read_bytes() == b"keep replacement"


def test_graphics_batch_retains_its_original_execution_directory(tmp_path, monkeypatch):
    job = tmp_path / "中文 图形"
    job.mkdir()
    command = job / "commands.cfile"
    command.write_bytes(b"exit\n")
    monkeypatch.setenv("LSPP_NATIVE_ALIAS_ROOT", str(tmp_path))
    monkeypatch.setattr("ls_prepost_mcp.engine.batch.native_workspace",
                        lambda *_: pytest.fail("Graphics must not create an execution alias"))
    monkeypatch.setattr("ls_prepost_mcp.engine.batch.native_environment", lambda *a, **kw: ({}, {}))
    owned = MagicMock()
    owned.__enter__.return_value = owned
    owned.process.pid = 123
    owned.process.returncode = 0
    owned.process.communicate.return_value = (b"", b"")
    owned.mechanism = "test-owned-process"

    def launch(args, **kwargs):
        assert kwargs["cwd"] == job
        assert args[1] == "c=" + str(command)
        return owned

    monkeypatch.setattr("ls_prepost_mcp.engine.batch.OwnedProcess", launch)
    result = BatchEngine().run(BatchJob(tmp_path / "lspp.exe", command, job, 1, graphics=True))
    assert result.status == "unverified" and "workspace_alias" not in result.data


@pytest.mark.parametrize("residue", ["empty", "nonempty", "junction"])
def test_failed_junction_creation_only_cleans_owned_empty_directory(tmp_path, monkeypatch, residue):
    import _winapi
    from pathlib import Path

    create = _winapi.CreateJunction
    root = tmp_path / "aliases"
    root.mkdir()
    job = tmp_path / "中文 作业"
    job.mkdir()
    (job / "keep.k").write_bytes(b"unchanged")
    created = []

    def fail(source, destination):
        path = Path(destination)
        created.append(path)
        if residue == "junction":
            create(source, destination)
        else:
            path.mkdir()
            if residue == "nonempty":
                (path / "keep.txt").write_bytes(b"keep")
        raise PermissionError("CreateJunction denied")

    monkeypatch.setattr(_winapi, "CreateJunction", fail)
    monkeypatch.setenv("LSPP_NATIVE_ALIAS_ROOT", str(root))
    with pytest.raises(RuntimeError, match="NTFS"):
        with native_workspace(job):
            pytest.fail("Creation failed before entering the native workspace")
    assert (job / "keep.k").read_bytes() == b"unchanged"
    if residue == "empty":
        assert list(root.iterdir()) == []
    elif residue == "nonempty":
        assert (created[0] / "keep.txt").read_bytes() == b"keep"
    else:
        assert created[0].resolve() == job
