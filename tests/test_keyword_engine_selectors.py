"""core.contracts.Selector resolved on a keyword deck, and Selectors inside edit_deck."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import FieldError, KeywordDeck
from ls_prepost_mcp.domain.model.operations import edit_deck
from ls_prepost_mcp.domain.model.selectors import resolve

pytest.importorskip("ansys.dyna.core")

CORNERS = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]


def _text() -> str:
    lines = ["*KEYWORD", "*NODE"]
    nid = 0
    for shift in (0.0, 2.0):  # two separate unit cubes along x: nodes 1-8 and 9-16
        for x, y, z in CORNERS:
            nid += 1
            lines.append(f"{nid:>8}{x + shift:>16}{float(y):>16}{float(z):>16}")
    lines += [f"{17:>8}{0.0:>16}{0.0:>16}{-1.0:>16}", f"{18:>8}{1.0:>16}{0.0:>16}{-1.0:>16}",
              f"{19:>8}{1.0:>16}{1.0:>16}{-1.0:>16}", f"{20:>8}{0.0:>16}{1.0:>16}{-1.0:>16}"]
    lines += ["*ELEMENT_SOLID", f"{1:>8}{1:>8}" + "".join(f"{n:>8}" for n in range(1, 9)),
              f"{2:>8}{2:>8}" + "".join(f"{n:>8}" for n in range(9, 17)),
              "*ELEMENT_SHELL", f"{3:>8}{3:>8}{17:>8}{18:>8}{19:>8}{20:>8}"]
    for pid in (1, 2, 3):
        lines += ["*PART", f"part {pid}", f"{pid:>10}{1:>10}{1:>10}"]
    lines += ["*SET_NODE_LIST", f"{7:>10}", f"{1:>10}{2:>10}{18:>10}",
              "*SET_PART_LIST", f"{8:>10}", f"{2:>10}{3:>10}",
              "*SET_SHELL_LIST", f"{9:>10}", f"{3:>10}", "*END"]
    return "\n".join(lines) + "\n"


@pytest.fixture()
def deck(tmp_path: Path) -> KeywordDeck:
    (tmp_path / "main.k").write_text(_text())
    return KeywordDeck.load(tmp_path / "main.k")


def _ids(deck: KeywordDeck, entity: str, predicate: dict) -> list[int]:
    return resolve(deck, {"entity_type": entity, "predicate": predicate}).tolist()


def test_basic_predicates(deck: KeywordDeck) -> None:
    assert _ids(deck, "node", {"kind": "all"}) == list(range(1, 21))
    assert _ids(deck, "node", {"kind": "none"}) == []
    assert _ids(deck, "solid", {"kind": "ids", "ids": [2]}) == [2]
    assert _ids(deck, "node", {"kind": "parts", "ids": [2]}) == list(range(9, 17))
    assert _ids(deck, "solid", {"kind": "parts", "ids": [1, 2]}) == [1, 2]
    assert _ids(deck, "part", {"kind": "all"}) == [1, 2, 3]
    assert _ids(deck, "node", {"kind": "box", "minimum": [1.5, -1, -1], "maximum": [3.5, 2, 2]}) == list(range(9, 17))
    assert _ids(deck, "solid", {"kind": "box", "minimum": [2, 0, 0], "maximum": [3, 1, 1]}) == [2]  # centroid
    assert _ids(deck, "node", {"kind": "sphere", "center": [0, 0, 0], "radius": 0.5}) == [1]


def test_planes_sets_surface_and_boolean(deck: KeywordDeck) -> None:
    plane = {"kind": "plane", "origin": [0, 0, 0], "normal": [0, 0, 1], "tolerance": 1e-9}
    assert _ids(deck, "node", plane) == [1, 2, 3, 4, 9, 10, 11, 12]
    assert _ids(deck, "node", {**plane, "side": "negative"}) == [17, 18, 19, 20]
    assert _ids(deck, "node", {"kind": "sets", "set_type": "node", "ids": [7]}) == [1, 2, 18]
    assert _ids(deck, "node", {"kind": "sets", "set_type": "shell", "ids": [9]}) == [17, 18, 19, 20]
    assert _ids(deck, "shell", {"kind": "sets", "set_type": "part", "ids": [8]}) == [3]
    assert _ids(deck, "node", {"kind": "surface", "part_ids": [1]}) == list(range(1, 9))
    union = {"kind": "boolean", "operator": "union",
             "operands": [{"kind": "ids", "ids": [1]}, {"kind": "sets", "set_type": "node", "ids": [7]}]}
    assert _ids(deck, "node", union) == [1, 2, 18]
    difference = {"kind": "boolean", "operator": "difference",
                  "operands": [{"kind": "parts", "ids": [1]}, {"kind": "box", "minimum": [0, 0, 0.5],
                                                                 "maximum": [1, 1, 1]}]}
    assert _ids(deck, "node", difference) == [1, 2, 3, 4]


@pytest.mark.parametrize(("selector", "message"), [
    ({"entity_type": "node", "predicate": {"kind": "ids", "ids": [99]}}, "not defined"),
    ({"entity_type": "node", "predicate": {"kind": "sets", "set_type": "node", "ids": [70]}}, "not defined"),
    ({"entity_type": "beam", "predicate": {"kind": "all"}}, "not a keyword-deck entity"),
    ({"entity_type": "node", "predicate": {"kind": "all"}, "configuration": "deformed", "state": 2}, "reference"),
    ({"entity_type": "node", "predicate": {"kind": "surface", "part_ids": [1], "feature_angle_degrees": 30.0}},
     "feature angle"),
])
def test_refusals(deck: KeywordDeck, selector: dict, message: str) -> None:
    with pytest.raises(FieldError, match=message):
        resolve(deck, selector)


def test_selectors_inside_edit_deck(tmp_path: Path) -> None:
    (tmp_path / "main.k").write_text(_text())
    box = {"entity_type": "node", "predicate": {"kind": "box", "minimum": [1.5, -1, -1], "maximum": [3.5, 2, 2]}}
    result = edit_deck(str(tmp_path / "main.k"), [
        {"op": "create_set", "kind": "node", "selector": box, "sid": 50},
        {"op": "add_boundary", "kind": "spc", "units": "mm-t-s", "dofs": "all",
         "target": {"selector": {"entity_type": "node", "predicate": {"kind": "parts", "ids": [3]}}}},
        {"op": "transform_nodes", "translate": [0, 0, 5.0],
         "selector": {"entity_type": "node", "predicate": {"kind": "sets", "set_type": "node", "ids": [7]}}},
    ], output_dir=str(tmp_path / "out"))
    assert result["status"] == "succeeded", result
    deck = KeywordDeck.load(tmp_path / "out" / "main.k")
    new_set = [b for b in deck.iter_blocks() if b.name.startswith("*SET_NODE") and deck.get(b, "sid").value == 50][0]
    assert deck.members(new_set) == list(range(9, 17))
    wrong = edit_deck(str(tmp_path / "main.k"), [
        {"op": "create_set", "kind": "node", "selector": {"entity_type": "solid", "predicate": {"kind": "all"}}}])
    assert wrong["status"] == "failed" and "does not match" in wrong["error"]
