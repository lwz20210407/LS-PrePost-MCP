"""Materials, EOS, sections, parts (P03) and contacts (P06) from recipes at keyword level."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import FieldError, KeywordDeck, contacts, materials
from ls_prepost_mcp.domain.model.cards import card_text
from ls_prepost_mcp.domain.model.operations import edit_deck

pytest.importorskip("ansys.dyna.core")

CUBE = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
STEEL = {"ro": 7.8e-9, "e": 210000.0, "pr": 0.3}
RECIPE_PARAMS = {
    "elastic": STEEL,
    "plastic_kinematic": {**STEEL, "sigy": 350.0, "etan": 1000.0},
    "johnson_cook": {"ro": 7.8e-9, "g": 80000.0, "a": 350.0, "b": 275.0, "n": 0.36, "c": 0.022, "m": 1.0,
                     "tm": 1793.0, "tr": 293.0, "epso": 1.0, "cp": 4.77e8},
    "rigid": {**STEEL, "cmo": 1.0, "con1": 7, "con2": 7},
    "piecewise_linear_plasticity": {**STEEL, "sigy": 350.0, "etan": 1000.0},
    "simplified_johnson_cook": {**STEEL, "a": 350.0, "b": 275.0, "n": 0.36, "c": 0.022},
}


def _two_blocks(tmp_path: Path) -> KeywordDeck:
    lower, upper = CUBE, [(x, y, z + 1.5) for x, y, z in CUBE]
    nodes = "".join(f"{i + 1:>8}{float(x):>16}{float(y):>16}{float(z):>16}\n" for i, (x, y, z) in enumerate(lower + upper))
    solids = "".join(f"{e:>8}{e:>8}" + "".join(f"{n:>8}" for n in range(first, first + 8)) + "\n"
                     for e, first in ((1, 1), (2, 9)))
    (tmp_path / "main.k").write_bytes(("*KEYWORD\n*NODE\n" + nodes + "*ELEMENT_SOLID\n" + solids + "*END\n").encode())
    return KeywordDeck.load(tmp_path / "main.k")


@pytest.mark.parametrize("recipe", sorted(materials.MATERIALS))
def test_every_material_recipe_reads_back(tmp_path: Path, recipe: str) -> None:
    deck = _two_blocks(tmp_path)
    result = materials.add_material(deck, recipe, RECIPE_PARAMS[recipe], title=f"{recipe} test")
    block = deck.blocks(result["keyword"])[0]
    for name, value in RECIPE_PARAMS[recipe].items():
        assert deck.get(block, name).value == pytest.approx(value)
    assert result["mid"] == 1 and deck.references(False).defined["material"] == {1}


def test_missing_and_unknown_parameters_are_refused(tmp_path: Path) -> None:
    deck = _two_blocks(tmp_path)
    with pytest.raises(FieldError, match=r"missing \['pr'\]"):
        materials.add_material(deck, "elastic", {"ro": 1.0, "e": 1.0})
    with pytest.raises(FieldError, match="unknown parameters"):
        materials.add_material(deck, "elastic", {**STEEL, "sigy": 1.0})
    with pytest.raises(FieldError, match="SIGY"):
        materials.add_material(deck, "piecewise_linear_plasticity", STEEL)
    with pytest.raises(FieldError, match="curve 4 is not defined"):
        materials.add_material(deck, "piecewise_linear_plasticity", {**STEEL, "lcss": 4})
    assert deck.changes == []


def test_unset_fields_stay_blank_for_dependent_defaults() -> None:
    """R17 Vol I *HOURGLASS: QB and QW default to QM; PyDYNA would write 0.1 for both. Q1/Q2 keep
    their nonzero defaults explicitly, IBQ (default 0) stays blank."""
    text = card_text("*HOURGLASS", {"hgid": 1, "ihq": 4, "qm": 0.05})
    assert text.splitlines()[-1].rstrip() == "         1         4      0.05                 1.5      0.06"


def test_nonzero_defaults_are_written_and_given_values_keep_their_digits() -> None:
    """R11 reads a blank *MAT_ELASTIC_PERI GT as 0 (every bond breaks); PyDYNA writes 5 digits."""
    text = card_text("*MAT_ELASTIC_PERI", {"mid": 1, "ro": 2200.0, "e": 1.79998e12})
    cells = text.splitlines()[-1]
    assert cells[20:30].strip() == "1.79998e12" and cells[30:40].strip() == "1e+20" and cells[40:50].strip() == "1e+20"
    deck_value = card_text("*MAT_ELASTIC", {"mid": 1, "ro": 7.8e-9, "e": 201955937667.92})
    assert "2.01956e11" in deck_value


def test_eos_section_hourglass_and_parts(tmp_path: Path) -> None:
    deck = _two_blocks(tmp_path)
    materials.add_material(deck, "johnson_cook", RECIPE_PARAMS["johnson_cook"])
    materials.add_eos(deck, "gruneisen", {"c": 4570000.0, "s1": 1.49, "gamao": 1.93})
    materials.add_section(deck, "solid", {"elform": 1})
    shell = materials.add_section(deck, "shell", {"elform": 16, "thickness": 2.0})
    assert [deck.get(deck.blocks("*SECTION_SHELL")[0], f"t{i}").value for i in range(1, 5)] == [2.0] * 4
    materials.add_hourglass(deck, {"ihq": 6, "qm": 0.1})
    part = materials.add_part(deck, title="core", secid=1, mid=1, eosid=1, hgid=1)
    assert part["pid"] == 1 and shell["secid"] == 2
    with pytest.raises(FieldError, match="eos 5 is not defined"):
        materials.add_part(deck, title="bad", secid=1, mid=1, eosid=5)
    with pytest.raises(FieldError, match="already defined"):
        materials.add_part(deck, title="dup", secid=1, mid=1, pid=1)
    materials.set_part(deck, 1, secid=2, eosid=0)
    block = deck.blocks("*PART")[0]
    assert deck.get(block, "secid", row=1).value == 2 and deck.get(block, "eosid", row=1).value == 0
    assert deck.references(False).dangling_count == 0  # element 2 still points at part 2 (not created here)


def _with_parts(tmp_path: Path) -> KeywordDeck:
    deck = _two_blocks(tmp_path)
    materials.add_section(deck, "solid", {"elform": 1})
    materials.add_material(deck, "elastic", STEEL)
    materials.add_part(deck, title="lower", secid=1, mid=1)
    materials.add_part(deck, title="upper", secid=1, mid=1)
    return deck


@pytest.mark.parametrize("recipe,a,b,params", [
    ("automatic_surface_to_surface", {"part": 1}, {"part": 2}, {"fs": 0.2}),
    ("automatic_single_surface", "all", None, {"fs": 0.1}),
    ("eroding_surface_to_surface", {"parts": [1]}, {"part": 2}, {"fs": 0.0, "erosop": 1}),
    ("tied_surface_to_surface_offset", {"exterior": {"parts": [1]}}, {"part": 2}, {}),
    ("automatic_nodes_to_surface", {"select": {"parts": [1]}}, {"part": 2}, {"fs": 0.3}),
])
def test_every_contact_recipe(tmp_path: Path, recipe: str, a: object, b: object, params: dict) -> None:
    deck = _with_parts(tmp_path)
    result = contacts.add_contact(deck, recipe, a, b, params=params, cid=7, title="pair")
    block = deck.blocks(result["keyword"])[0]
    assert deck.get(block, "cid").value == 7
    for name, value in params.items():
        assert deck.get(block, name).value == pytest.approx(value)
    assert deck.references().dangling_count == 0


def test_contact_refusals(tmp_path: Path) -> None:
    deck = _with_parts(tmp_path)
    before = len(deck.changes)
    cases = [
        (("automatic_surface_to_surface", {"part": 1}, {"part": 9}), {"fs": 0.0}, "part 9 is not defined"),
        (("automatic_surface_to_surface", {"part": 1}, {"part": 2}), {}, "static friction"),
        (("automatic_single_surface", {"segment_set": 1}, None), {"fs": 0.0}, "cannot be a segment_set"),
        (("automatic_nodes_to_surface", {"part": 1}, None), {"fs": 0.0}, "needs a side B"),
        (("automatic_surface_to_surface", {"part": 1}, {"part": 2}), {"fs": 0.0, "soft": 1}, "default cards"),
        (("eroding_surface_to_surface", {"part": 1}, {"part": 2}), {"fs": 0.0, "saboxid": 1}, "SABOXID"),
        (("automatic_surface_to_surface", {"exterior": {"parts": [1]}}, {"part": 2}), {"fs": 0.0, "saboxid": 1},
         "SABOXID"),
    ]
    for args, params, message in cases:
        with pytest.raises(FieldError, match=message):
            contacts.add_contact(deck, *args, params=params)
    assert len(deck.changes) == before


def test_edit_deck_property_and_contact_ops(tmp_path: Path) -> None:
    _two_blocks(tmp_path)
    edits = [
        {"op": "add_section", "units": "mm-t-s", "recipe": "solid", "params": {"elform": 1}},
        {"op": "add_material", "units": "mm-t-s", "recipe": "elastic", "params": STEEL, "title": "steel"},
        {"op": "add_part", "title": "lower", "secid": 1, "mid": 1},
        {"op": "add_part", "title": "upper", "secid": 1, "mid": 1},
        {"op": "add_contact", "recipe": "automatic_surface_to_surface", "a": {"part": 2}, "b": {"part": 1},
         "params": {"fs": 0.1}},
    ]
    result = edit_deck(str(tmp_path / "main.k"), edits, output_dir=str(tmp_path / "out"))
    assert result["status"] == "succeeded", result
    saved = KeywordDeck.load(tmp_path / "out" / "main.k")
    assert saved.references().defined["part"] == {1, 2} and saved.references().dangling_count == 0
    missing_units = edit_deck(str(tmp_path / "main.k"), [{**edits[1], "units": None}])
    assert missing_units["status"] == "failed" and "units" in missing_units["error"]
