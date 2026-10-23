"""P1-1: save-as uses the resolution in effect when each Include was read."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model.deck import KeywordDeck


def make_source(tmp_path, mixed=False):
    root = tmp_path / "source"
    root.mkdir()
    child = root / ("lib/x.k" if mixed else "part.k")
    child.parent.mkdir(exist_ok=True)
    child.write_bytes(b"*NODE\n1,0,0,0\n")
    main = root / "main.k"
    main.write_text(
        "*KEYWORD\n*INCLUDE\n" + ("lib/x.k" if mixed else "part.k")
        + "\n*INCLUDE_PATH\n" + child.parent.as_posix()
        + ("\n*INCLUDE\nx.k" if mixed else "") + "\n*END\n"
    )
    return main, child


@pytest.mark.parametrize("edited", [False, True], ids=["untouched", "edited-child"])
def test_later_absolute_search_card_cannot_make_prior_local_include_external(tmp_path, edited):
    main, child = make_source(tmp_path)
    before = main.read_bytes(), child.read_bytes()
    deck = KeywordDeck.load(main)
    if edited:
        block = deck.blocks("*NODE")[0]
        block.lines[1] = "1,2,0,0\n"
        block.file.modified = True
    saved = deck.save_as(tmp_path / "output")
    assert saved["external_unchanged"] == []
    assert saved["reload_warnings"] == []
    restored = KeywordDeck.load(saved["main"])
    assert len(restored.files) == 2 and not restored.warnings
    saved_child = Path(saved["main"]).parent / "part.k"
    assert saved_child.read_bytes() == (b"*NODE\n1,2,0,0\n" if edited else before[1])
    assert (main.read_bytes(), child.read_bytes()) == before


def test_one_file_can_be_external_and_still_need_a_local_relative_copy(tmp_path):
    main, child = make_source(tmp_path, mixed=True)
    before = main.read_bytes(), child.read_bytes()
    saved = KeywordDeck.load(main).save_as(tmp_path / "output")
    assert not any("Missing include" in w for w in saved["reload_warnings"])
    assert (Path(saved["main"]).parent / "lib/x.k").read_bytes() == before[1]
    assert str(child) in saved["external_unchanged"]
    assert (main.read_bytes(), child.read_bytes()) == before


def test_include_resolution_records_the_search_directory_that_actually_won(tmp_path):
    root = tmp_path / "source"
    (root / "first").mkdir(parents=True)
    (root / "second").mkdir()
    child = root / "second/x.k"
    child.write_bytes(b"*NODE\n1,0,0,0\n")
    main = root / "main.k"
    main.write_text("*KEYWORD\n*INCLUDE_PATH\nfirst\n" + child.parent.as_posix()
                    + "\n*INCLUDE\nx.k\n*END\n")
    deck = KeywordDeck.load(main)
    ref = next(r for r in deck.includes if r.kind == "file")
    assert ref.resolution.rule == "include_path"
    assert ref.resolution.search_directory == child.parent
    assert ref.resolution.search_directory_index == 1


def test_dual_local_external_parent_keeps_its_relative_descendants_in_both_trees(tmp_path):
    main, child = make_source(tmp_path, mixed=True)
    child.write_text("*INCLUDE\nleaf.k\n")
    leaf = child.parent / "leaf.k"
    leaf.write_bytes(b"*NODE\n1,0,0,0\n")
    saved = KeywordDeck.load(main).save_as(tmp_path / "output")
    assert not any("Missing include" in w for w in saved["reload_warnings"])
    assert (Path(saved["main"]).parent / "lib/leaf.k").read_bytes() == leaf.read_bytes()
