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


@pytest.mark.parametrize("stage", ["early", "late"])
@pytest.mark.parametrize("filesystem_change", ["rename", "replace"])
def test_rollback_preserves_loaded_include_blocks_parameters_and_context_without_resource_reload(
        tmp_path, monkeypatch, stage, filesystem_change):
    child = tmp_path / "child.k"
    child.write_text("*PARAMETER\nRscale,2.0\n*NODE\n1,0,0,0\n2,1,0,0\n", encoding="ascii")
    main = tmp_path / "main.k"
    main.write_text("*KEYWORD\n*INCLUDE\nchild.k\n*DEFINE_CURVE\n1\n0.0,0.0\n1.0,1.0\n*END\n",
                    encoding="ascii")
    deck = KeywordDeck.load(main)
    curve = deck.blocks("*DEFINE_CURVE")[0]
    deck.warnings.append("caller warning retained")
    before = state(deck)
    sequence, includes, scopes = tuple(deck.iter_blocks()), deck.includes, deck._scopes
    files = tuple(deck.files.items())
    parameters, warnings = tuple(deck.parameters), tuple(deck.warnings)
    lookup = deck.lookup(curve)
    if filesystem_change == "rename":
        child.rename(tmp_path / "held-child.k")  # owned fixture only; the loaded AST must remain usable
    else:
        child.write_text("*PARAMETER\nRscale,9.0\n*NODE\n99,9,9,9\n", encoding="ascii")
    if stage == "late":
        original = loads.insert_card

        def fail_after_insertion(*args, **kwargs):
            original(*args, **kwargs)
            raise FieldError("Injected final card failure")

        monkeypatch.setattr(loads, "insert_card", fail_after_insertion)
    with pytest.raises((FieldError, ValueError)):
        loads.add_nodal_load(deck, {"nodes": [1, 2]}, "z", {"points": [[0., 0.], [1., 1.]]},
                             sf="bad" if stage == "early" else 1.)
    assert state(deck) == before and tuple(deck.iter_blocks()) == sequence
    assert deck.includes is includes and deck._scopes is scopes
    assert tuple(deck.files.items()) == files and tuple(deck.parameters) == parameters
    assert tuple(deck.warnings) == warnings and deck.lookup(curve) == lookup


@pytest.mark.parametrize("consumer", ["curve", "node_set", "segment_set"])
@pytest.mark.parametrize("title", ["*INCLUDE", "*PARAMETER", "*KEYWORD"])
def test_consumed_title_cannot_turn_an_append_only_boundary_into_a_structural_edit(
        tmp_path, monkeypatch, consumer, title):
    deck = KeywordDeck.load(source_model(tmp_path / "source"))
    before = state(deck)

    def forbidden_rebuild():
        pytest.fail("An append-only boundary must not activate structural input or reload resources")

    monkeypatch.setattr(deck, "_rebuild", forbidden_rebuild)
    with pytest.raises(FieldError):
        if consumer == "curve":
            loads.ensure_curve(deck, {"points": [[0., 0.], [1., 1.]], "title": title})
        elif consumer == "node_set":
            loads.add_spc(deck, {"nodes": [1, 2], "title": title}, "all")
        else:
            loads.add_non_reflecting(deck, {"segments": [[1, 2, 3, 4]], "title": title})
    assert state(deck) == before
