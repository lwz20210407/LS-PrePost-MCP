"""I05 independent regression data; never use A10's held-out questions for tuning."""
import errno
import os
import shutil
from types import SimpleNamespace

import pytest

import ls_prepost_mcp.knowledge_index as index


def document(title, text, visibility="public"):
    return index.Document(title, "known_issue", title, text, "test://" + title, "MIT", visibility)


def test_mixed_query_ranks_both_languages_before_code_or_text_only(tmp_path):
    path = tmp_path / "index.sqlite"
    index.build_index(path, [document("both", "runtime42 梁端转角 " + "背景说明 " * 150),
                             document("code", "runtime42 独立说明"), document("text", "梁端转角说明")])
    rows = index.search_index(path, "runtime42 梁端转角")
    assert [row["title"] for row in rows] == ["both", "code", "text"]
    assert [row["query_match"] for row in rows] == ["both", "code_only", "text_only"]


def test_mixed_query_retains_chinese_candidates_when_code_has_no_match(tmp_path):
    path = tmp_path / "index.sqlite"
    index.build_index(path, [document("rotation", "梁端转角说明"), document("unrelated", "完全无关记录")])
    rows = index.search_index(path, "runtime43 梁端转角")
    assert [row["title"] for row in rows] == ["rotation"]
    assert rows[0]["query_match"] == "text_only"


def test_private_both_language_match_cannot_leak_into_public_fallback(tmp_path):
    path = tmp_path / "index.sqlite"
    index.build_index(path, [document("hidden", "runtime42 梁端转角", "private"),
                             document("public", "runtime42")])
    assert [r["title"] for r in index.search_index(path, "runtime42 梁端转角")] == ["public"]
    assert index.search_index(path, "runtime42 梁端转角", include_private=True)[0]["title"] == "hidden"


def test_code_only_query_keeps_all_identifiers_required(tmp_path):
    path = tmp_path / "index.sqlite"
    index.build_index(path, [document("one", "runtime42"), document("two", "runtime42 value73")])
    assert [r["title"] for r in index.search_index(path, "runtime42 value73")] == ["two"]


def test_identifier_prefix_compatibility_does_not_expand_chinese_terms(tmp_path):
    path = tmp_path / "index.sqlite"
    index.build_index(path, [document("prefix", "runtime_section_alpha 梁端转角"),
                             document("unrelated", "runtime_section_beta 其它说明")])
    rows = index.search_index(path, "runtime_section 梁端转角")
    assert rows[0]["title"] == "prefix" and rows[0]["query_match"] == "both"


@pytest.mark.skipif(os.name != "nt", reason="Windows atomic no-replace rename semantics")
def test_no_hardlink_filesystem_publishes_complete_index(tmp_path, monkeypatch):
    path = tmp_path / "index.sqlite"
    monkeypatch.setattr(index.os, "link", lambda *args: (_ for _ in ()).throw(OSError(errno.ENOTSUP, "No links")))
    index.build_index(path, [document("record", "runtime42")])
    assert index.search_index(path, "runtime42")[0]["title"] == "record"
    assert set(tmp_path.iterdir()) == {path}


@pytest.mark.skipif(os.name != "nt", reason="Windows atomic no-replace rename semantics")
def test_fallback_does_not_overwrite_index_created_during_copy(tmp_path, monkeypatch):
    path = tmp_path / "index.sqlite"
    monkeypatch.setattr(index.os, "link", lambda *args: (_ for _ in ()).throw(OSError(errno.ENOTSUP, "No links")))
    copy = shutil.copyfileobj

    def racing_copy(source, destination):
        copy(source, destination)
        path.write_bytes(b"Other writer's index")

    monkeypatch.setattr(index.shutil, "copyfileobj", racing_copy)
    with pytest.raises(FileExistsError):
        index.build_index(path, [document("record", "runtime42")])
    assert path.read_bytes() == b"Other writer's index"
    assert set(tmp_path.iterdir()) == {path}


@pytest.mark.skipif(os.name != "nt", reason="Windows fallback")
def test_interrupted_fallback_does_not_publish_partial_bytes(tmp_path, monkeypatch):
    path = tmp_path / "index.sqlite"
    monkeypatch.setattr(index.os, "link", lambda *args: (_ for _ in ()).throw(OSError(errno.ENOTSUP, "No links")))

    def interrupted(source, destination):
        destination.write(b"incomplete")
        assert not path.exists()
        raise RuntimeError("Interrupted copy")

    monkeypatch.setattr(index.shutil, "copyfileobj", interrupted)
    with pytest.raises(RuntimeError, match="Interrupted copy"):
        index.build_index(path, [document("record", "runtime42")])
    assert list(tmp_path.iterdir()) == []


def test_permission_failure_is_not_reinterpreted_as_missing_link_support(tmp_path, monkeypatch):
    path = tmp_path / "index.sqlite"
    monkeypatch.setattr(index.os, "link", lambda *args: (_ for _ in ()).throw(PermissionError(errno.EACCES, "Denied")))
    monkeypatch.setattr(index.shutil, "copyfileobj", lambda *args: pytest.fail("Do not retry access denial"))
    with pytest.raises(PermissionError):
        index.build_index(path, [document("record", "runtime42")])
    assert list(tmp_path.iterdir()) == []


def test_colliding_partial_name_keeps_preexisting_file(tmp_path, monkeypatch):
    path = tmp_path / "index.sqlite"
    orphan = tmp_path / "index.sqlite.fixed.partial"
    orphan.write_bytes(b"Keep earlier evidence")
    monkeypatch.setattr(index.uuid, "uuid4", lambda: SimpleNamespace(hex="fixed"))
    with pytest.raises(FileExistsError):
        index.build_index(path, [document("record", "runtime42")])
    assert orphan.read_bytes() == b"Keep earlier evidence"
    assert set(tmp_path.iterdir()) == {orphan}


@pytest.mark.skipif(os.name != "nt", reason="Windows fallback")
def test_colliding_publish_name_keeps_preexisting_file(tmp_path, monkeypatch):
    path = tmp_path / "index.sqlite"
    orphan = tmp_path / "index.sqlite.fixed.publish"
    orphan.write_bytes(b"Keep earlier publication")
    monkeypatch.setattr(index.uuid, "uuid4", lambda: SimpleNamespace(hex="fixed"))
    monkeypatch.setattr(index.os, "link", lambda *args: (_ for _ in ()).throw(OSError(errno.ENOTSUP, "No links")))
    with pytest.raises(FileExistsError):
        index.build_index(path, [document("record", "runtime42")])
    assert orphan.read_bytes() == b"Keep earlier publication"
    assert set(tmp_path.iterdir()) == {orphan}
