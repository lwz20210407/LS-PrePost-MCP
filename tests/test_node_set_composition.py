"""P04 shared node-set meaning: child set IDs are never mistaken for node IDs."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.domain.model.compare import compare_decks
from ls_prepost_mcp.domain.model.contact import _set_members
from ls_prepost_mcp.domain.model.selectors import resolve


def deck_file(path: Path, sets: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    nodes = "".join(f"{uid},{float(uid)},0,0\n" for uid in (1, 2, 3, 4, 10))
    path.write_text("*KEYWORD\n*NODE\n" + nodes + sets + "*END\n", encoding="utf8")
    return path


def test_contact_add_reads_child_node_members_not_child_set_ids(tmp_path):
    source = deck_file(tmp_path / "main.k", "*SET_NODE_LIST\n10\n2,3\n*SET_NODE_ADD\n20\n10\n")
    deck = KeywordDeck.load(source)
    assert _set_members(deck, "*SET_NODE", 20) == [2, 3]


def test_unrelated_generate_does_not_block_requested_list_set_selector(tmp_path):
    source = deck_file(tmp_path / "main.k", "*SET_NODE_LIST\n10\n2,3\n*SET_NODE_LIST_GENERATE\n20\n1,4\n")
    deck = KeywordDeck.load(source)
    selector = dict(entity_type="node", predicate=dict(kind="sets", set_type="node", ids=[10]))
    assert resolve(deck, selector).tolist() == [2, 3]


def test_compare_detects_changed_generate_range_definition(tmp_path):
    before = deck_file(tmp_path / "before/main.k", "*SET_NODE_LIST_GENERATE\n20\n1,2\n")
    after = deck_file(tmp_path / "after/main.k", "*SET_NODE_LIST_GENERATE\n20\n1,3\n")
    assert compare_decks(str(before), str(after), include_mesh=False)["identical"] is False


def test_plain_generation_uses_defined_nodes_with_gaps_and_nonexistent_limits(tmp_path):
    from ls_prepost_mcp.domain.model.node_sets import NodeSets

    source = deck_file(tmp_path / "main.k", "*SET_NODE_LIST_GENERATE\n20\n0,1000000000\n")
    assert NodeSets(KeywordDeck.load(source)).resolve(20) == [1, 2, 3, 4, 10]


def test_add_nested_forward_references_and_shared_children_have_stable_unique_order(tmp_path):
    from ls_prepost_mcp.domain.model.node_sets import NodeSets

    source = deck_file(tmp_path / "main.k", "*SET_NODE_ADD\n40\n30,20\n*SET_NODE_ADD\n30\n10,20\n"
                       "*SET_NODE_LIST\n10\n3,2\n*SET_NODE_LIST_GENERATE\n20\n1,4\n")
    deck = KeywordDeck.load(source)
    assert NodeSets(deck).resolve(40) == [3, 2, 1, 4]
    assert resolve(deck, dict(entity_type="node", predicate=dict(kind="sets", set_type="node", ids=[40]))).tolist() == [1, 2, 3, 4]


@pytest.mark.parametrize("text,message", [
    ("*SET_NODE_ADD\n20\n20\n", "cycle"),
    ("*SET_NODE_ADD\n20\n30\n*SET_NODE_ADD\n30\n20\n", "cycle"),
    ("*SET_NODE_ADD\n20\n99\n", "not defined"),
    ("*SET_NODE_LIST\n20\n99\n", "missing nodes"),
    ("*SET_NODE_LIST\n20\n1\n*SET_NODE_ADD\n20\n10\n", "duplicate"),
])
def test_bad_reachable_node_definitions_fail_explicitly(tmp_path, text, message):
    from ls_prepost_mcp.domain.model.node_sets import NodeSets

    source = deck_file(tmp_path / "main.k", text)
    with pytest.raises(ValueError, match=message):
        NodeSets(KeywordDeck.load(source)).resolve(20)


def test_create_compact_sets_through_existing_t1_and_reload(tmp_path):
    pytest.importorskip("ansys.dyna.core")
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.domain.model.node_sets import NodeSets
    from ls_prepost_mcp.service import Service

    source = deck_file(tmp_path / "source/main.k", "*SET_NODE_LIST\n10\n2,3\n")
    before = source.read_bytes()
    service = Service(Settings(tmp_path / "work", allowed_roots=(source.parent,)))
    result = service.create_entities(str(source), [
        dict(op="create_set", kind="node", representation="generate", sid=20, ranges=[[0, 1000000000]], title="limits"),
        dict(op="create_set", kind="node", representation="generate_increment", sid=30,
             ranges=[dict(begin=1, end=4, increment=1)]),
        dict(op="create_set", kind="node", representation="add", sid=40, set_ids=[20, 10]),
    ])
    assert result["status"] == "succeeded", result.get("error")
    assert source.read_bytes() == before
    saved = KeywordDeck.load(result["data"]["main"])
    assert NodeSets(saved).resolve(20) == NodeSets(saved).resolve(40) == [1, 2, 3, 4, 10]
    assert NodeSets(saved).resolve(30) == [1, 2, 3, 4]
    assert saved.blocks("*SET_NODE_ADD")[0].name == "*SET_NODE_ADD"


def test_sparse_increment_is_not_silently_given_plain_generate_hole_semantics(tmp_path):
    pytest.importorskip("ansys.dyna.core")
    from ls_prepost_mcp.domain.model.node_sets import NodeSets

    source = deck_file(tmp_path / "main.k", "*SET_NODE_LIST_GENERATE_INCREMENT\n20\n1,10,3\n")
    with pytest.raises(ValueError, match="Sparse GENERATE_INCREMENT"):
        NodeSets(KeywordDeck.load(source)).resolve(20)


def test_references_and_model_check_report_add_cycles_without_expanding_mesh(tmp_path):
    from ls_prepost_mcp.domain.model.operations import check_deck

    source = deck_file(tmp_path / "main.k", "*SET_NODE_ADD\n20\n30\n*SET_NODE_ADD\n30\n20\n")
    deck = KeywordDeck.load(source)
    assert deck.references(include_mesh=False).node_set_cycles == [[20, 30, 20]]
    result = check_deck(str(source), include_mesh=False)
    assert not result["ok"] and any(error["kind"] == "node_set_cycle" for error in result["errors"])


def test_edit_cannot_publish_new_add_cycle_even_when_every_sid_exists(tmp_path):
    from ls_prepost_mcp.domain.model.operations import edit_deck

    source = deck_file(tmp_path / "main.k", "*SET_NODE_LIST\n10\n2,3\n*SET_NODE_ADD\n20\n10\n")
    original = source.read_bytes()
    result = edit_deck(str(source), [dict(op="set_members", keyword="*SET_NODE_ADD", match=dict(sid=20), members=[20])],
                       output_dir=str(tmp_path / "out"))
    assert result["status"] == "failed" and not result["written"]
    assert "cycle" in result["error"].lower() and not (tmp_path / "out").exists()
    assert source.read_bytes() == original


@pytest.mark.parametrize("payload", [
    dict(representation="bad", ranges=[[1, 4]]),
    dict(representation="generate", ranges=[[1, 4]], ids=[1]),
    dict(representation="list", ranges=[[1, 4]]),
    dict(representation="generate_increment", ranges=[dict(begin=1, end=4, increment=0)]),
    dict(representation="generate_increment", ranges=[dict(begin=1, end=4, increment=True)]),
    dict(representation="add", set_ids=[99]),
])
def test_invalid_composition_requests_never_write_a_deck(tmp_path, payload):
    from ls_prepost_mcp.domain.model.operations import edit_deck

    source = deck_file(tmp_path / "main.k", "")
    before = source.read_bytes()
    result = edit_deck(str(source), [dict(op="create_set", kind="node", sid=50, **payload)], output_dir=str(tmp_path / "out"))
    assert result["status"] == "failed" and not result["written"]
    assert source.read_bytes() == before and not (tmp_path / "out").exists()


def test_long_format_list_generated_increment_and_add_creation(tmp_path):
    pytest.importorskip("ansys.dyna.core")
    from ls_prepost_mcp.domain.model.node_sets import NodeSets
    from ls_prepost_mcp.domain.model.operations import edit_deck

    source = deck_file(tmp_path / "main.k", "")
    source.write_text(source.read_text().replace("*KEYWORD\n", "*KEYWORD_LONG\n"))
    result = edit_deck(str(source), [
        dict(op="create_set", kind="node", sid=10, ids=[3, 1]),
        dict(op="create_set", kind="node", sid=20, representation="generate", ranges=[[1, 4]]),
        dict(op="create_set", kind="node", sid=30, representation="generate_increment",
             ranges=[dict(begin=1, end=3, increment=1)]),
        dict(op="create_set", kind="node", sid=40, representation="add", set_ids=[10, 20]),
    ], output_dir=str(tmp_path / "out"))
    assert result["status"] == "succeeded", result
    deck = KeywordDeck.load(result["save"]["main"])
    assert NodeSets(deck).resolve(40) == [3, 1, 2, 4]
    assert NodeSets(deck).resolve(30) == [1, 2, 3]


def test_include_structure_encoding_and_untouched_bytes_survive_compact_set_save(tmp_path):
    from ls_prepost_mcp.domain.model.node_sets import NodeSets
    from ls_prepost_mcp.domain.model.operations import edit_deck

    source = deck_file(tmp_path / "source/nodes.k", "")
    main = source.with_name("main.k")
    main.write_bytes(b"*KEYWORD\r\n*INCLUDE\r\nnodes.k\r\n*INCLUDE\r\nsets.k\r\n*END\r\n")
    included = source.with_name("sets.k")
    included.write_bytes("$ café\r\n*SET_NODE_LIST\r\n10\r\n3,1\r\n".encode("cp1252"))
    before = {path.name: path.read_bytes() for path in main.parent.iterdir()}
    result = edit_deck(str(main), [dict(op="create_set", kind="node", sid=20, representation="generate",
        ranges=[[0, 9]], title="generated", file="sets.k"),
        dict(op="create_set", kind="node", sid=30, representation="add", set_ids=[10, 20], file="sets.k")],
        output_dir=str(tmp_path / "out"))
    assert result["status"] == "succeeded", result
    assert {path.name: path.read_bytes() for path in main.parent.iterdir()} == before
    saved = KeywordDeck.load(result["save"]["main"])
    assert NodeSets(saved).resolve(30) == [3, 1, 2, 4]
    outputs = {item.path.name: item.path for item in saved.files.values()}
    assert outputs["main.k"].read_bytes() == before["main.k"]
    assert outputs["nodes.k"].read_bytes() == before["nodes.k"]
    assert b"$ caf\xe9\r\n" in outputs["sets.k"].read_bytes()


def test_deep_add_chain_is_iterative_and_membership_work_is_bounded(tmp_path):
    from ls_prepost_mcp.domain.model.node_sets import NodeSets

    text = "*SET_NODE_LIST\n1\n2,3\n" + "".join(f"*SET_NODE_ADD\n{sid}\n{sid-1}\n" for sid in range(2, 1200))
    source = deck_file(tmp_path / "main.k", text)
    deck = KeywordDeck.load(source)
    assert NodeSets(deck).resolve(1199) == [2, 3]
    with pytest.raises(ValueError, match="definition budget"):
        NodeSets(deck, max_definitions=500).resolve(1199)


def test_generate_work_budget_depends_on_real_nodes_not_integer_span(tmp_path):
    from ls_prepost_mcp.domain.model.node_sets import NodeSets

    source = deck_file(tmp_path / "main.k", "*SET_NODE_LIST_GENERATE\n20\n0,2000000000\n")
    deck = KeywordDeck.load(source)
    assert NodeSets(deck).resolve(20) == [1, 2, 3, 4, 10]
    with pytest.raises(ValueError, match="work budget"):
        NodeSets(deck, max_work=4).resolve(20)
