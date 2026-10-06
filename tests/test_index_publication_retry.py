"""I05: real Windows sharing locks must not corrupt publication or hide failures."""

import errno
import os

import pytest

from ls_prepost_mcp import knowledge_index as index
from tests.test_knowledge_query_publication import document

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows no-replace rename and sharing locks")


def no_links(*args):
    raise OSError(errno.ENOTSUP, "No hardlinks on this filesystem")


def test_real_reader_released_after_two_failed_renames_allows_publication(tmp_path, monkeypatch):
    monkeypatch.setattr(index.os, "link", no_links)
    rename = os.rename
    handles, failures = [], []

    def locked_rename(source, destination):
        if not handles:
            handles.append(open(source, "rb"))
        try:
            return rename(source, destination)
        except PermissionError as exc:
            failures.append(exc)
            if len(failures) == 2:
                handles[0].close()
            raise

    monkeypatch.setattr(index.os, "rename", locked_rename)
    path = tmp_path / "index.sqlite"
    try:
        index.build_index(path, [document("record", "runtime42")])
    finally:
        for handle in handles:
            handle.close()
    assert len(failures) == 2 and all(exc.winerror in (5, 32) for exc in failures)
    assert index.search_index(path, "runtime42")[0]["title"] == "record"
    assert set(tmp_path.iterdir()) == {path}


def test_permanent_reader_preserves_original_rename_error_and_reports_orphan(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(index.os, "link", no_links)
    rename = os.rename
    handles, failures, delays = [], [], []
    monkeypatch.setattr(index.time, "sleep", delays.append)

    def locked_rename(source, destination):
        if not handles:
            handles.append(open(source, "rb"))
        try:
            return rename(source, destination)
        except PermissionError as exc:
            failures.append(exc)
            raise

    monkeypatch.setattr(index.os, "rename", locked_rename)
    path = tmp_path / "index.sqlite"
    try:
        with pytest.raises(PermissionError) as caught:
            index.build_index(path, [document("record", "runtime42")])
        assert caught.value is failures[-1]  # Cleanup's unlink error must not replace it.
        assert len(failures) == 6 and sum(delays) < 2
        orphan, = tmp_path.glob("*.publish")
        assert str(orphan) in caplog.text
        assert any(str(orphan) in note for note in caught.value.__notes__)
        assert not path.exists() and not list(tmp_path.glob("*.partial"))
    finally:
        for handle in handles:
            handle.close()
