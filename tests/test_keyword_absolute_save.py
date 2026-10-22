"""P02/P11: absolute dependencies must not turn successful edits into unused copies."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model.deck import KeywordDeck

pytest.importorskip("ansys.dyna.core")


def files(tmp_path, search=False):
    project, external = tmp_path / "project", tmp_path / "external"
    project.mkdir()
    external.mkdir()
    material = external / "material.k"
    material.write_bytes(b"$ original material\r\n*MAT_ELASTIC\r\n1,1,100,0.3\r\n")
    main = project / "main.k"
    if search:
        main.write_text("*KEYWORD\n*INCLUDE_PATH\n" + str(external) + "\n*INCLUDE\nmaterial.k\n*END\n")
    else:
        parent = external / "assembly.k"
        parent.write_text("*INCLUDE\nmaterial.k\n")
        main.write_text("*KEYWORD\n*INCLUDE\n" + str(parent) + "\n*END\n")
    return main, material


@pytest.mark.parametrize("search", [True, False], ids=["absolute-search-dir", "absolute-parent-relative-child"])
def test_modified_absolute_dependency_fails_before_writing_unused_output(tmp_path, search):
    main, material = files(tmp_path, search)
    before = main.read_bytes(), material.read_bytes()
    deck = KeywordDeck.load(main)
    deck.set(deck.blocks("*MAT_ELASTIC")[0], "e", 200.)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="absolute.*edited|absolute.*modified"):
        deck.save_as(output)
    assert not output.exists()
    assert (main.read_bytes(), material.read_bytes()) == before


def test_unmodified_absolute_subtree_is_explicitly_external(tmp_path):
    main, material = files(tmp_path)
    deck = KeywordDeck.load(main)
    saved = deck.save_as(tmp_path / "output")
    assert set(saved["external_unchanged"]) == {str(material), str(material.parent / "assembly.k")}
    assert len(saved["files"]) == 1 and Path(saved["main"]).read_bytes() == main.read_bytes()
    restored = KeywordDeck.load(saved["main"])
    assert restored.get(restored.blocks("*MAT_ELASTIC")[0], "e").value == 100.


def test_relative_search_dir_keeps_working_modified_copy(tmp_path):
    project = tmp_path / "project"
    (project / "assets").mkdir(parents=True)
    material = project / "assets/material.k"
    material.write_text("*MAT_ELASTIC\n1,1,100,0.3\n")
    main = project / "main.k"
    main.write_text("*KEYWORD\n*INCLUDE_PATH\nassets\n*INCLUDE\nmaterial.k\n*END\n")
    deck = KeywordDeck.load(main)
    deck.set(deck.blocks("*MAT_ELASTIC")[0], "e", 200.)
    saved = deck.save_as(tmp_path / "output")
    restored = KeywordDeck.load(saved["main"])
    assert restored.get(restored.blocks("*MAT_ELASTIC")[0], "e").value == 200.
    assert material.read_text() == "*MAT_ELASTIC\n1,1,100,0.3\n"
    assert saved["external_unchanged"] == []


def test_mcp_edit_does_not_return_verified_disconnected_material_copy(tmp_path):
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.service import Service

    main, material = files(tmp_path, search=True)
    before = material.read_bytes()
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    result = service.edit_keywords(str(main), [{"op": "set", "keyword": "*MAT_ELASTIC", "field": "e", "value": 200.}])
    assert result["status"] == "failed" and "absolute" in result["error"]["message"]
    assert result["artifacts"] == []
    assert not (service.jobs.root / result["job_id"] / "deck").exists()
    assert material.read_bytes() == before


def test_opaque_file_under_external_parent_is_not_copied_as_an_unused_asset(tmp_path):
    main, material = files(tmp_path)
    parent = material.parent / "assembly.k"
    parent.write_text(parent.read_text() + "*INCLUDE_BINARY\nmesh.bin\n")
    binary = material.parent / "mesh.bin"
    binary.write_bytes(b"\x00opaque payload\xff")
    saved = KeywordDeck.load(main).save_as(tmp_path / "output")
    assert len(saved["files"]) == 1
    assert str(binary) in saved["external_unchanged"]
    assert binary.read_bytes() == b"\x00opaque payload\xff"


def test_relative_opaque_file_is_still_copied_verbatim(tmp_path):
    main = tmp_path / "main.k"
    main.write_text("*KEYWORD\n*INCLUDE_BINARY\nmesh.bin\n*END\n")
    binary = tmp_path / "mesh.bin"
    binary.write_bytes(b"\x00opaque payload\xff")
    saved = KeywordDeck.load(main).save_as(tmp_path / "output")
    assert len(saved["files"]) == 2 and saved["external_unchanged"] == []
    assert (Path(saved["main"]).parent / "mesh.bin").read_bytes() == binary.read_bytes()


def test_external_parent_main_directory_fallback_remains_relocatable(tmp_path):
    project, external = tmp_path / "project", tmp_path / "external"
    project.mkdir()
    external.mkdir()
    material = project / "material.k"
    material.write_text("*MAT_ELASTIC\n1,1,100,0.3\n")
    parent = external / "assembly.k"
    parent.write_text("*INCLUDE\nmaterial.k\n")
    main = project / "main.k"
    main.write_text("*KEYWORD\n*INCLUDE\n" + str(parent) + "\n*END\n")
    deck = KeywordDeck.load(main)
    deck.set(deck.blocks("*MAT_ELASTIC")[0], "e", 200.)
    saved = deck.save_as(tmp_path / "output")
    restored = KeywordDeck.load(saved["main"])
    assert restored.get(restored.blocks("*MAT_ELASTIC")[0], "e").value == 200.
    assert saved["external_unchanged"] == [str(parent)] and len(saved["files"]) == 2
    assert material.read_text() == "*MAT_ELASTIC\n1,1,100,0.3\n"
