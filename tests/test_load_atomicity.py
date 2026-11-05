"""Existing boundary-construction failures must not leave new AST dependencies."""

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck, loads
from ls_prepost_mcp.domain.model.fields import FieldError
from tests.test_load_identity_inputs import source_model

CASES = [
    ("nodal_load", dict(target={"nodes": [999]}, dof="z", sf=1.)),
    ("pressure", dict(target={"segments": [[1, 2, 3]]}, sf=1.)),
    ("nodal_load", dict(target={"nodes": [1, 2]}, dof="z", sf="not-a-number")),
    ("nodal_load", dict(target={"nodes": [1, 2]}, dof="z", sf=float("nan"))),
    ("pressure", dict(target={"segments": [[1, 2, 3, 4]]}, sf=float("inf"))),
    ("gravity", dict(direction="z", sf="not-a-number")),
    ("gravity", dict(direction="z", sf=float("nan"))),
    ("rigid_wall", dict(target={"nodes": [1, 2]}, point=[0, 0, -1], normal=[0, 0, 1], friction="bad")),
    ("rigid_wall", dict(target={"nodes": [1, 2]}, point=[0, 0, -1], normal=[0, 0, 1], friction=float("nan"))),
    ("cnrb", dict(target={"nodes": [999]}, pid=99)),
    ("spc", dict(target={"nodes": [999]}, dofs="all")),
]


def state(deck):
    return (deck.main.text(), tuple(deck.main.blocks), list(deck.changes), deck.main.modified,
            tuple(deck.modified_files()))


@pytest.mark.parametrize("kind,params", CASES)
def test_rejected_boundary_inputs_restore_all_in_memory_dependencies(tmp_path, kind, params):
    deck = KeywordDeck.load(source_model(tmp_path / "source"))
    before = state(deck)
    arguments = dict(params)
    if kind in {"nodal_load", "pressure", "gravity"}:
        arguments["curve"] = {"points": [[0., 0.], [1., 1.]]}
    with pytest.raises((FieldError, ValueError)):
        loads.KINDS[kind](deck, **arguments)
    assert state(deck) == before
    assert len(deck.blocks("*DEFINE_CURVE")) == 1


def test_ensure_curve_failure_itself_is_atomic_for_joint_and_boundary_consumers(tmp_path):
    deck = KeywordDeck.load(source_model(tmp_path / "source"))
    before = state(deck)
    with pytest.raises(FieldError):
        loads.ensure_curve(deck, {"points": [[0., 0.], [1., float("nan")]]})
    assert state(deck) == before


def test_final_card_failure_preserves_existing_edits_block_identity_and_missing_final_newline(tmp_path, monkeypatch):
    source = source_model(tmp_path / "source")
    source.write_bytes(source.read_bytes().replace(b"*END\n", b"").rstrip(b"\r\n"))
    deck = KeywordDeck.load(source)
    part = deck.blocks("*PART")[0]
    deck.set(part, "heading", "caller-owned prior edit", row=1)
    before = state(deck)
    original = loads.insert_card

    def fail_after_insertion(*args, **kwargs):
        original(*args, **kwargs)
        raise FieldError("Injected final readback rejection")

    monkeypatch.setattr(loads, "insert_card", fail_after_insertion)
    with pytest.raises(FieldError):
        loads.add_nodal_load(deck, {"nodes": [1, 2]}, "z", {"points": [[0., 0.], [1., 1.]]})
    assert state(deck) == before
    assert deck.get(part, "heading", row=1).value == "caller-owned prior edit"
