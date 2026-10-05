"""Boundary conditions, loads (P05) and control recipes (P10) at keyword level."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import FieldError, KeywordDeck
from ls_prepost_mcp.domain.model.controls import apply_recipe
from ls_prepost_mcp.domain.model.operations import edit_deck

pytest.importorskip("ansys.dyna.core")

CUBE = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]


def _model(tmp_path: Path) -> Path:
    node_text = "".join(f"{i + 1:>8}{float(x):>16}{float(y):>16}{float(z):>16}\n" for i, (x, y, z) in enumerate(CUBE))
    text = ("*KEYWORD\n*PART\nblock\n         1         1         1\n*SECTION_SOLID\n         1         1\n"
            "*MAT_ELASTIC\n         1    7.8e-9  210000.0       0.3\n*NODE\n" + node_text
            + "*ELEMENT_SOLID\n" + f"{1:>8}{1:>8}" + "".join(f"{n:>8}" for n in range(1, 9)) + "\n*END\n")
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    return tmp_path / "main.k"


def test_p05_story_and_all_nine_kinds(tmp_path: Path) -> None:
    """Fix the bottom, press the top, give an initial velocity; then every other kind once."""
    ramp = {"points": [[0.0, 0.0], [1.0, 1.0]]}
    edits = [
        {"op": "add_boundary", "kind": "spc", "units": "mm-ms-kg", "target": {"select": {"box": [-1, -1, -0.1, 2, 2, 0.1]}},
         "dofs": "all"},
        {"op": "add_boundary", "kind": "pressure", "units": "mm-ms-kg",
         "target": {"exterior": {"parts": [1], "direction": [0, 0, 1]}}, "curve": ramp, "sf": 10.0},
        {"op": "add_boundary", "kind": "initial_velocity", "units": "mm-ms-kg", "target": {"part": 1},
         "velocity": [0.0, 0.0, -800.0]},
        {"op": "add_boundary", "kind": "prescribed_motion", "units": "mm-ms-kg", "target": {"nodes": [5, 6]},
         "dof": "x", "motion": "displacement", "curve": {"lcid": 1}},
        {"op": "add_boundary", "kind": "nodal_load", "units": "mm-ms-kg", "target": {"node_set": 2}, "dof": "z",
         "curve": {"lcid": 1}, "sf": -1.0},
        {"op": "add_boundary", "kind": "gravity", "units": "mm-ms-kg", "direction": "z", "curve": {"lcid": 1},
         "sf": 9.81e-3},
        {"op": "add_boundary", "kind": "rigid_wall", "units": "mm-ms-kg", "point": [0, 0, -1], "normal": [0, 0, 1]},
        {"op": "add_boundary", "kind": "cnrb", "units": "mm-ms-kg", "target": {"nodes": [1, 2, 3, 4]}},
        {"op": "add_boundary", "kind": "non_reflecting", "units": "mm-ms-kg",
         "target": {"exterior": {"parts": [1], "direction": [1, 0, 0]}}},
    ]
    result = edit_deck(str(_model(tmp_path)), edits, output_dir=str(tmp_path / "out"))
    assert result["status"] == "succeeded" and result["new_dangling"] == [], result.get("error")
    deck = KeywordDeck.load(tmp_path / "out" / "main.k")
    names = [b.name for b in deck.iter_blocks()]
    for keyword in ("*BOUNDARY_SPC_SET", "*LOAD_SEGMENT_SET", "*INITIAL_VELOCITY_GENERATION",
                    "*BOUNDARY_PRESCRIBED_MOTION_SET", "*LOAD_NODE_SET", "*LOAD_BODY_Z", "*RIGIDWALL_PLANAR",
                    "*CONSTRAINED_NODAL_RIGID_BODY", "*BOUNDARY_NON_REFLECTING"):
        assert keyword in names
    spc = deck.blocks("*BOUNDARY_SPC_SET")[0]
    assert deck.members(deck.find("*SET_NODE_LIST", sid=deck.get(spc, "nsid").value)[0][0]) == [1, 2, 3, 4]
    assert deck.get(deck.blocks("*LOAD_SEGMENT_SET")[0], "sf").value == 10.0
    assert deck.get(deck.blocks("*INITIAL_VELOCITY_GENERATION")[0], "vz").value == -800.0
    assert deck.references().dangling_count == 0 and names[-1] == "*END"


def test_units_must_be_declared(tmp_path: Path) -> None:
    result = edit_deck(str(_model(tmp_path)), [{"op": "add_boundary", "kind": "spc", "target": {"nodes": [1]},
                                                  "dofs": "all"}])
    assert result["status"] == "failed" and "units" in result["error"]


def test_p10_recipes(tmp_path: Path) -> None:
    deck = KeywordDeck.load(_model(tmp_path))
    first = apply_recipe(deck, "termination", {"endtim": 0.05})
    second = apply_recipe(deck, "termination", {"endtim": 0.06})
    assert first[0]["action"] == "inserted" and second[0]["action"] == "updated"
    assert deck.get(deck.blocks("*CONTROL_TERMINATION")[0], "endtim").value == 0.06
    apply_recipe(deck, "d3plot", {"dt": 0.001})
    cards = apply_recipe(deck, "ascii", {"names": ["glstat", "matsum", "rcforc"], "dt": 1e-4})
    assert [c["keyword"] for c in cards] == ["*DATABASE_GLSTAT", "*DATABASE_MATSUM", "*DATABASE_RCFORC"]
    apply_recipe(deck, "hourglass", {"ihq": 4, "qh": 0.05})
    with pytest.raises(FieldError, match="needs"):
        apply_recipe(deck, "hourglass", {"ihq": 4})
    with pytest.raises(FieldError, match="does not take"):
        apply_recipe(deck, "termination", {"endtim": 1.0, "speed": 3})
    deck.insert("*CONTROL_TERMINATION\n       1.0\n")
    with pytest.raises(FieldError, match="2 \\*CONTROL_TERMINATION blocks"):
        apply_recipe(deck, "termination", {"endtim": 0.07})
