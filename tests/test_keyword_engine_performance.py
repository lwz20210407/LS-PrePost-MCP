"""Speed-ups for large decks keep the results: trimmed unified diff, one-line instance layouts."""
import difflib
import random
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck, schema
from ls_prepost_mcp.domain.model.persist import _unified

pytest.importorskip("ansys.dyna.core")


@pytest.mark.parametrize("seed", range(40))
def test_trimmed_diff_equals_difflib_on_the_whole_file(seed: int) -> None:
    rng = random.Random(seed)
    old = [f"line {i}\n" for i in range(rng.randint(0, 60))]
    new = list(old)
    for _ in range(rng.randint(1, 4)):
        where = rng.randint(0, len(new))
        action = rng.choice(["insert", "delete", "replace"])
        if action == "insert" or not new:
            new[where:where] = [f"new {rng.random()}\n" for _ in range(rng.randint(1, 5))]
        elif action == "delete":
            del new[min(where, len(new) - 1)]
        else:
            new[min(where, len(new) - 1)] = f"changed {rng.random()}\n"
    expected = list(difflib.unified_diff(old, new, fromfile="a", tofile="b"))
    assert _unified(old, new, "a", "b") == expected


def _velocity_deck(tmp_path: Path, rows: int, comma_rows: tuple[int, ...] = ()) -> KeywordDeck:
    lines = []
    for n in range(1, rows + 1):
        if n in comma_rows:
            lines.append(f"{n},1.5,-2.0,3.25\n")
        else:
            lines.append(f"{n:>10}{1.5:>10}{-2.0:>10}{3.25:>10}\n")
    (tmp_path / "main.k").write_text("*KEYWORD\n*INITIAL_VELOCITY_NODE\n" + "".join(lines) + "*END\n")
    return KeywordDeck.load(tmp_path / "main.k")


def test_one_line_instances_reuse_the_checked_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    deck = _velocity_deck(tmp_path, 2500, comma_rows=(7, 1200))
    block = [b for b in deck.iter_blocks() if b.name == "*INITIAL_VELOCITY_NODE"][0]
    fast = deck.layout(block)
    monkeypatch.setattr(schema, "SELF_CHECK_EVERY", 1)  # every row through PyDYNA
    full = schema.layout(block, {})
    assert len(fast.rows) == len(full.rows) == 2500
    for key in full.rows:
        assert [(i.name, i.slot) for i in fast.rows[key]] == [(i.name, i.slot) for i in full.rows[key]]
    assert deck.get(block, "vy", row=1200).value == -2.0 and deck.get(block, "vz", row=2500).value == 3.25


@pytest.mark.parametrize("bad", ["        14       abc      -2.0      3.25\n",
                                 "14,1.5,-2.0,3.25,0,0,0,0,9,9\n"])
def test_a_malformed_row_still_gets_the_full_check(tmp_path: Path, bad: str) -> None:
    """Junk in a number field, or more comma items than fields (text past column 80 is ignored by
    LS-DYNA and by the full self-check alike, so it is no test case)."""
    _velocity_deck(tmp_path, 30, comma_rows=(3,))  # a checked comma template exists before row 14
    path = tmp_path / "main.k"
    text = path.read_text().splitlines(keepends=True)
    text[15] = bad  # row 14
    path.write_text("".join(text))
    deck = KeywordDeck.load(path)
    block = [b for b in deck.iter_blocks() if b.name == "*INITIAL_VELOCITY_NODE"][0]
    with pytest.raises(schema.Unsupported):
        deck.layout(block)
