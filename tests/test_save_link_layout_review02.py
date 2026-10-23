"""Review02 P02: resolving a layout junction must not create a dangling save tree."""
import os
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck


def linked_tree(tmp_path, mode):
    source, target = tmp_path / "source", tmp_path / "real_lib"
    source.mkdir()
    target.mkdir()
    (target / "nodes.k").write_bytes(b"*NODE\n1,0,0,0\n")
    (target / "asset.bin").write_bytes(b"owned opaque test bytes")
    link = source / "lib"
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)
    cards = {"include": "*INCLUDE\nlib/nodes.k\n",
             "search": "*INCLUDE_PATH\nlib\n*INCLUDE\nnodes.k\n",
             "opaque": "*INCLUDE_BINARY\nlib/asset.bin\n"}
    main = source / "main.k"
    main.write_text("*KEYWORD\n" + cards[mode] + "*END\n")
    return KeywordDeck.load(main), target


@pytest.mark.parametrize("mode", ["include", "search", "opaque"])
def test_linked_layout_is_refused_before_writing_a_dangling_output(tmp_path, mode):
    deck, target = linked_tree(tmp_path, mode)
    original = {p.name: p.read_bytes() for p in target.iterdir()}
    output = tmp_path / "saved"
    with pytest.raises(ValueError, match="symlink|junction"):
        deck.save_as(output)
    assert not output.exists()
    assert {p.name: p.read_bytes() for p in target.iterdir()} == original


def test_link_is_rejected_before_the_physical_cross_volume_layout_step(tmp_path, monkeypatch):
    deck, _ = linked_tree(tmp_path, "include")
    link = deck.main.path.parent / "lib"
    resolve = Path.resolve

    def physical(path, *args, **kwargs):
        if path == link:
            pytest.fail("Physical layout resolved before rejecting the junction")
        return resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", physical)
    with pytest.raises(ValueError, match="symlink|junction"):
        deck.save_as(tmp_path / "saved")
