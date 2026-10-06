"""Cleanup notes belong to this index build, not an unrelated handled error."""

from pathlib import Path

from ls_prepost_mcp import knowledge_index as index
from tests.test_knowledge_query_publication import document


def test_successful_build_cleanup_does_not_annotate_outer_exception(tmp_path, monkeypatch, caplog):
    unlink = Path.unlink

    def locked_partial(path, *args, **kwargs):
        if path.suffix == ".partial":
            raise PermissionError("reader retains the temporary index")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked_partial)
    outer = RuntimeError("unrelated caller failure")
    path = tmp_path / "index.sqlite"
    try:
        raise outer
    except RuntimeError:
        index.build_index(path, [document("record", "runtime42")])

    assert not getattr(outer, "__notes__", [])
    assert index.search_index(path, "runtime42")[0]["title"] == "record"
    assert "could not be removed" in caplog.text
