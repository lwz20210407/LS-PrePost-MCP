"""Rules R11 enforces at read time (free-format item width) or mishandles silently (short motion curves)."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.domain.model.operations import check_deck
from ls_prepost_mcp.domain.model.solver_rules import long_free_items, short_motion_curves

pytest.importorskip("ansys.dyna.core")

NODES = "*NODE\n       1             0.0             0.0             0.0\n       2             1.0             0.0             0.0\n"


def _deck(tmp_path: Path, text: str) -> Path:
    (tmp_path / "main.k").write_bytes(("*KEYWORD\n" + text + "*END\n").encode("ascii"))
    return tmp_path / "main.k"


def test_comma_items_wider_than_their_field_are_found(tmp_path: Path) -> None:
    path = _deck(tmp_path, NODES + "*MAT_ELASTIC\n1,7.85e-9,210000.123456789,0.3\n"
                 "*INITIAL_VELOCITY_NODE\n1,0.005405604,2.0,3.0\n2,1.0,2.0,3.0\n")
    count, sample = long_free_items(KeywordDeck.load(path))
    assert count == 2
    assert {(s["keyword"], s["field"], s["text"], s["width"]) for s in sample} == {
        ("*MAT_ELASTIC", "e", "210000.123456789", 10), ("*INITIAL_VELOCITY_NODE", "vx", "0.005405604", 10)}
    checked = check_deck(str(path), include_mesh=False)
    assert not checked["ok"] and checked["errors"][0]["kind"] == "free_format_item_too_long"


def test_commas_in_comment_lines_are_not_items(tmp_path: Path) -> None:
    path = _deck(tmp_path, "$ plate (part 1) and block (part 2), mm\n" + NODES
                 + "*MAT_ELASTIC\n$ steel, 1/2 scale\n1,7.85e-9,210000.0,0.3\n")
    assert long_free_items(KeywordDeck.load(path)) == (0, [])


def test_items_that_fit_and_parameters_are_not_flagged(tmp_path: Path) -> None:
    path = _deck(tmp_path, NODES + "*PARAMETER\nR youngs_modulus_ab 210000.0\n"
                 "*MAT_ELASTIC\n1,7.85e-9,&youngs_mod,0.3\n*INITIAL_VELOCITY_NODE\n1,0.0054056,2.0,3.0\n")
    assert long_free_items(KeywordDeck.load(path)) == (0, [])


MOTION = ("*BOUNDARY_PRESCRIBED_MOTION_NODE\n         1         1         2         1       1.0         0{death:>10}\n"
          "*DEFINE_CURVE\n         1         0{sfa:>10}       1.0{offa:>10}\n0.0,0.0\n{end},1.0\n"
          "*CONTROL_TERMINATION\n{endtim:>10}\n")


@pytest.mark.parametrize(("end", "endtim", "death", "sfa", "offa", "warned"), [
    (1.0, 2.0, "", "", "", True),      # curve stops at 1.0, run goes on to 2.0
    (3.0, 2.0, "", "", "", False),     # curve covers the run
    (1.0, 2.0, "0.5", "", "", False),  # motion dies before the curve ends
    (1.0, 2.0, "", "2.0", "", False),  # abscissa scaled to 2.0
    (1.0, 2.0, "", "", "0.5", True),   # offset to 1.5, still short
])
def test_prescribed_motion_curve_shorter_than_the_motion(tmp_path: Path, end: float, endtim: float, death: str,
                                                         sfa: str, offa: str, warned: bool) -> None:
    path = _deck(tmp_path, NODES + MOTION.format(end=end, endtim=endtim, death=death, sfa=sfa, offa=offa))
    found = short_motion_curves(KeywordDeck.load(path))
    assert bool(found) is warned
    if warned:
        assert found[0]["lcid"] == 1 and found[0]["active_until"] == endtim
        assert any("ends at" in w for w in check_deck(str(path), include_mesh=False)["warnings"])
