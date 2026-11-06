"""Contact IDs must not turn flags/fractions into another existing target."""
import copy
import json
from collections import UserDict
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model import KeywordDeck, contacts
from ls_prepost_mcp.domain.model.fields import FieldError
from ls_prepost_mcp.service import Service

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests/data/p06-contact-identity-golden.json"
MODEL_TEXT = """*KEYWORD
*PART
solid
1,1,1
*PART
shell
2,2,1
*SECTION_SOLID
1,1
*SECTION_SHELL
2,2
0.2,0.2,0.2,0.2
*MAT_ELASTIC
1,1,1,0.3
*NODE
1,0,0,0
2,1,0,0
3,0,1,0
4,0,0,1
*ELEMENT_SOLID
1,1,1,2,3,4,4,4,4,4
*ELEMENT_SHELL
100,2,1,2,3,3
*SET_PART_LIST
1
1,2
*SET_SEGMENT
1
1,2,3,3
*SET_SHELL_LIST
1
100
*SET_NODE_LIST
1
1,2
*END
"""
GOLDEN_CASES = [
    dict(recipe="automatic_surface_to_surface", a={"part": 1}, b={"part": 2}, params={"fs": .2, "fd": .15}),
    dict(recipe="automatic_single_surface", a={"parts": [1, 2]}, params={"fs": .2, "fd": .15,
         "sst": .25, "mst": .5, "sfst": .75, "sfmt": 1.25, "sfs": .8, "sfm": .9}),
    dict(recipe="eroding_surface_to_surface", a={"parts": [1]}, b={"part_set": 1}, params={"fs": 0., "fd": .1, "erosop": 1}),
    dict(recipe="tied_surface_to_surface_offset", a={"exterior": {"parts": [1]}}, b={"part": 2}, params={}),
    dict(recipe="automatic_nodes_to_surface", a={"select": {"parts": [1]}}, b={"segment_set": 1}, params={"fs": .3, "fd": .2}),
]


def source_model(directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "model.k"
    path.write_text(MODEL_TEXT, encoding="ascii", newline="\n")
    return path


@pytest.fixture
def source(tmp_path):
    pytest.importorskip("ansys.dyna.core")
    return source_model(tmp_path / "source")


@pytest.mark.parametrize("kind", ["part", "part_set", "segment_set", "shell_set"])
@pytest.mark.parametrize("side", ["a", "b"])
@pytest.mark.parametrize("bad", [True, 1.5])
def test_public_contact_creation_refuses_nonidentity_target_instead_of_binding_existing_one(source, tmp_path, kind, side, bad):
    service = Service(Settings(tmp_path / "jobs", allowed_roots=(source.parent,)))
    before = source.read_bytes()
    entity = dict(op="add_contact", recipe="automatic_surface_to_surface", a={"part": 1}, b={"part": 2}, params={"fs": 0.})
    entity[side] = {kind: bad}
    result = service.create_entities(str(source), [entity])
    assert result["status"] == "failed", result
    assert not result["artifacts"] and not list((tmp_path / "jobs").rglob("*.k"))
    assert source.read_bytes() == before


@pytest.mark.parametrize("selection", ["parts", "exterior", "select"])
@pytest.mark.parametrize("bad", [True, 1.5])
def test_nested_contact_part_identities_are_rejected_before_selection_or_set_allocation(source, monkeypatch, selection, bad):
    deck = KeywordDeck.load(source)
    target = {selection: [bad]} if selection == "parts" else {selection: {"parts": [bad]}}
    original = copy.deepcopy(target)

    def forbidden(*args, **kwargs):
        pytest.fail("An invalid identity reached selection or dependency allocation")

    monkeypatch.setattr(contacts.sets, "create_set", forbidden)
    monkeypatch.setattr(contacts.geometry, "exterior_segments", forbidden)
    monkeypatch.setattr(contacts.geometry, "select_nodes", forbidden)
    with pytest.raises(FieldError, match="integer identity"):
        contacts.add_contact(deck, "automatic_surface_to_surface" if selection != "select" else "automatic_nodes_to_surface",
                             target, {"part": 2}, params={"fs": .2})
    assert target == original and not deck.changes and deck.main.text() == MODEL_TEXT


@pytest.mark.parametrize("bad", [True, 1.5])
def test_public_contact_id_is_not_truncated_or_taken_from_a_flag(source, tmp_path, bad):
    service = Service(Settings(tmp_path / "jobs", allowed_roots=(source.parent,)))
    result = service.create_entities(str(source), [dict(op="add_contact", recipe="automatic_surface_to_surface",
        a={"part": 1}, b={"part": 2}, params={"fs": .2}, cid=bad)])
    assert result["status"] == "failed", result
    assert not result["artifacts"] and not list((tmp_path / "jobs").rglob("*.k"))


@pytest.mark.parametrize("value,accepted", [(True, False), (1.5, False), (1.0, True), ("1", True)])
def test_existing_node_set_identity_contract_is_kept(source, tmp_path, value, accepted):
    service = Service(Settings(tmp_path / "jobs", allowed_roots=(source.parent,)))
    result = service.create_entities(str(source), [dict(op="add_contact", recipe="automatic_nodes_to_surface",
        a={"node_set": value}, b={"part": 2}, params={"fs": .2})])
    if accepted:
        assert result["status"] == "succeeded"
        assert result["data"]["summaries"][0]["sides"]["a"] == [1, 4]
    else:
        assert result["status"] == "failed" and not result["artifacts"]
        assert not list((tmp_path / "jobs").rglob("*.k"))


@pytest.mark.parametrize("invalid", ["b", "cid"])
def test_all_contact_identity_validation_precedes_dependency_creation(source, monkeypatch, invalid):
    deck = KeywordDeck.load(source)
    deck.set(deck.blocks("*PART")[0], "heading", "prior caller edit", row=1)
    before = deck.main.text(), tuple(deck.main.blocks), tuple(deck.changes), deck.main.modified
    entity = dict(a={"parts": [1]}, b={"part": 2}, params={"fs": .2}, cid=77)
    if invalid == "b":
        entity["b"] = {"part": 1.5}
    else:
        entity["cid"] = True

    def forbidden(*args, **kwargs):
        pytest.fail("A dependency was created before all identities were checked")

    monkeypatch.setattr(contacts.sets, "create_set", forbidden)
    with pytest.raises(FieldError, match="integer identity"):
        contacts.add_contact(deck, "automatic_surface_to_surface", **entity)
    assert (deck.main.text(), tuple(deck.main.blocks), tuple(deck.changes), deck.main.modified) == before


@pytest.mark.parametrize("bad", [True, 1.5])
def test_invalid_contact_identity_needs_no_keyword_provider_or_deck_lookup(monkeypatch, bad):
    def forbidden(*args, **kwargs):
        pytest.fail("Bad identity reached a provider or deck lookup")

    monkeypatch.setattr(contacts.links, "field_names", forbidden)
    deck = SimpleNamespace(references=forbidden)
    with pytest.raises(FieldError, match="integer identity"):
        contacts.add_contact(deck, "automatic_surface_to_surface", {"part": bad}, {"part": 2}, params={"fs": .2})


@pytest.mark.parametrize("value", [1, 1.0, "1", " 1 ", np.int64(1), np.float64(1.), Decimal("1"), Fraction(1, 1)])
def test_exact_integer_input_forms_keep_the_same_contact_bytes(source, value):
    expected = json.loads(GOLDEN.read_text(encoding="utf8"))["cases"][0]["deck_text"]
    deck = KeywordDeck.load(source)
    result = contacts.add_contact(deck, "automatic_surface_to_surface", {"part": value}, {"part": 2},
                                  params={"fs": .2, "fd": .15}, cid=77.0, title="literal pair")
    assert result["sides"] == {"a": [1, 3], "b": [2, 3]}
    assert deck.main.text() == expected


@pytest.mark.parametrize("number", range(5))
def test_all_five_existing_contact_definitions_keep_baseline_bytes_and_physical_inputs(source, number):
    fixture = json.loads(GOLDEN.read_text(encoding="utf8"))["cases"][number]
    case = copy.deepcopy(GOLDEN_CASES[number])
    before = copy.deepcopy(case)
    deck = KeywordDeck.load(source)
    result = contacts.add_contact(deck, **case, cid=77, title="literal pair")
    assert case == before
    assert deck.main.text() == fixture["deck_text"]
    block = deck.blocks(result["keyword"])[0]
    for key, value in case["params"].items():
        assert deck.get(block, key).value == pytest.approx(value)
    assert source.read_text(encoding="ascii") == MODEL_TEXT


def test_explicit_zero_contact_id_keeps_its_existing_meaning(source):
    deck = KeywordDeck.load(source)
    result = contacts.add_contact(deck, "automatic_surface_to_surface", {"part": 1}, {"part": 2},
                                  params={"fs": 0.}, cid=0.)
    assert result["keyword"].endswith("_ID")
    assert deck.get(deck.blocks(result["keyword"])[0], "cid").value == 0


@pytest.mark.parametrize("shape", ["text", "mapping", "bytes"])
def test_public_contact_parts_requires_id_sequence_not_an_ambiguous_scalar_container(source, tmp_path, shape):
    value = {"text": "12", "mapping": {"1": "ignored", "2": "ignored"}, "bytes": bytes([1, 2])}[shape]
    service = Service(Settings(tmp_path / "jobs", allowed_roots=(source.parent,)))
    result = service.create_entities(str(source), [dict(op="add_contact", recipe="automatic_surface_to_surface",
        a={"parts": value}, b={"part": 2}, params={"fs": 0.})])
    assert result["status"] == "failed", result
    assert not result["artifacts"] and not list((tmp_path / "jobs").rglob("*.k"))


@pytest.mark.parametrize("selection", ["nodes", "exterior", "select"])
@pytest.mark.parametrize("value", ["12", {"1": "ignored", "2": "ignored"}, bytes([1, 2])])
def test_contact_identity_sequences_are_shape_checked_before_provider_lookup(monkeypatch, selection, value):
    target = {"nodes": value} if selection == "nodes" else {selection: {"parts": value}}

    def forbidden(*args, **kwargs):
        pytest.fail("Ambiguous identity collection reached provider or references")

    monkeypatch.setattr(contacts.links, "field_names", forbidden)
    with pytest.raises(FieldError, match="sequence"):
        contacts.add_contact(SimpleNamespace(references=forbidden), "automatic_nodes_to_surface" if selection in ("nodes", "select")
                             else "automatic_surface_to_surface", target, {"part": 2}, params={"fs": 0.})


@pytest.mark.parametrize("container", [list, tuple, np.asarray])
def test_existing_part_id_sequence_forms_remain_supported_without_caller_mutation(source, container):
    deck = KeywordDeck.load(source)
    target = {"parts": container([1., 2.])}
    original = copy.deepcopy(target["parts"])
    result = contacts.add_contact(deck, "automatic_surface_to_surface", target, {"part": 2}, params={"fs": .2})
    assert result["sides"]["a"] == [2, 2]
    assert deck.members(deck.blocks("*SET_PART_LIST")[1]) == [1, 2]
    assert np.array_equal(target["parts"], original)


@pytest.mark.parametrize("selection", ["select", "exterior"])
def test_nested_mapping_filter_cannot_bypass_contact_part_identity_checks(source, selection):
    deck = KeywordDeck.load(source)
    target = {selection: UserDict(parts=[True])}
    with pytest.raises(FieldError, match="integer identity"):
        contacts.add_contact(deck, "automatic_nodes_to_surface" if selection == "select" else "automatic_surface_to_surface",
                             target, {"part": 2}, params={"fs": .2})
    assert not deck.changes and deck.main.text() == MODEL_TEXT


@pytest.mark.parametrize("selection", ["select", "exterior"])
def test_legal_nested_mapping_filter_is_preserved_without_mutating_the_caller(source, selection):
    deck = KeywordDeck.load(source)
    filtering = UserDict(parts=[1.0])
    before = copy.deepcopy(filtering)
    result = contacts.add_contact(deck, "automatic_nodes_to_surface" if selection == "select" else "automatic_surface_to_surface",
                                  {selection: filtering}, {"part": 2}, params={"fs": .2})
    assert filtering == before
    assert result["created_sets"][0]["kind"] == ("node_set" if selection == "select" else "segment_set")
    if selection == "select":
        assert deck.members(deck.blocks("*SET_NODE_LIST")[1]) == [1, 2, 3, 4]
