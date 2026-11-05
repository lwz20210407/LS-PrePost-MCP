"""P04 internal-review regressions: no discarded definitions or lossy identities."""
import pytest

from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.domain.model.compare import compare_decks
from ls_prepost_mcp.domain.model.contact import _slave, check_penetration
from ls_prepost_mcp.domain.model.contacts import _side
from ls_prepost_mcp.domain.model.node_sets import NodeSets
from ls_prepost_mcp.domain.model.operations import edit_deck, read_fields
from tests.test_node_set_composition import deck_file


@pytest.mark.parametrize("row", ["1,2,10", "1,2,0,0,0,0,0,0,3,4"])
def test_incomplete_or_excess_generate_fields_are_not_silently_discarded(tmp_path, row):
    source = deck_file(tmp_path / "main.k", f"*SET_NODE_LIST_GENERATE\n20\n{row}\n")
    with pytest.raises(ValueError, match="range|fields|pair"):
        NodeSets(KeywordDeck.load(source)).resolve(20)


def test_compare_never_says_identical_after_discarding_an_odd_range_tail(tmp_path):
    before = deck_file(tmp_path / "a/main.k", "*SET_NODE_LIST_GENERATE\n20\n1,2,10\n")
    after = deck_file(tmp_path / "b/main.k", "*SET_NODE_LIST_GENERATE\n20\n1,2,3\n")
    with pytest.raises(ValueError):
        compare_decks(str(before), str(after), include_mesh=False)


def test_generate_default_zero_padding_cannot_pair_with_the_next_card(tmp_path):
    source = deck_file(tmp_path / "main.k", "*SET_NODE_LIST_GENERATE\n20\n1,2,0\n4,10\n")
    assert NodeSets(KeywordDeck.load(source)).resolve(20) == [1, 2, 4, 10]


@pytest.mark.parametrize("bad", [True, 1.5])
def test_node_contact_read_and_creation_never_truncate_a_set_identity(tmp_path, bad):
    source = deck_file(tmp_path / "main.k", "*SET_NODE_LIST\n1\n3,4\n")
    deck = KeywordDeck.load(source)
    with pytest.raises(ValueError, match="identity"):
        _slave(deck, dict(node_set=bad))
    with pytest.raises(ValueError, match="identity"):
        _side(deck, dict(node_set=bad), {"node_set"}, "A", [])


@pytest.mark.parametrize("keyword,sid", [("*SET_NODE_LIST", 1), ("*SET_NODE_ADD", 20)])
@pytest.mark.parametrize("bad", [True, 1.5])
def test_node_set_member_edit_never_truncates_values_before_the_shared_primitive(tmp_path, keyword, sid, bad):
    source = deck_file(tmp_path / "main.k", "*SET_NODE_LIST\n1\n2,3\n*SET_NODE_ADD\n20\n1\n")
    before = source.read_bytes()
    result = edit_deck(str(source), [dict(op="set_members", keyword=keyword, match=dict(sid=sid), members=[bad])],
                       output_dir=str(tmp_path / "out"))
    assert result["status"] == "failed" and not result["written"]
    assert source.read_bytes() == before


@pytest.mark.parametrize("master_kind", ["empty", "segment_set"])
def test_missing_node_set_member_is_a_semantic_error_not_lookup_indexerror(tmp_path, master_kind):
    # An explicitly empty master needs no optional PyDYNA table schema. The
    # slave's undefined member must still fail before the empty-surface return.
    master = dict(parts=[])
    sets = "*SET_NODE_LIST\n1\n99\n"
    if master_kind == "segment_set":
        pytest.importorskip("ansys.dyna.core")
        sets += "*SET_SEGMENT\n2\n1,2,3,4\n"
        master = dict(segment_set=2)
    source = deck_file(tmp_path / "main.k", sets)
    deck = KeywordDeck.load(source)
    with pytest.raises(ValueError, match="missing nodes|undefined nodes"):
        _slave(deck, dict(node_set=1))
    with pytest.raises(ValueError, match="missing nodes|undefined nodes"):
        check_penetration(deck, dict(node_set=1), master)


def test_valid_node_set_with_explicitly_empty_master_has_no_penetration(tmp_path):
    source = deck_file(tmp_path / "main.k", "*SET_NODE_LIST\n1\n1,2\n")
    result = check_penetration(KeywordDeck.load(source), dict(node_set=1), dict(parts=[]))
    assert result["slave_nodes"] == 2 and result["master_faces"] == 0
    assert result["penetrating"] == 0 and result["nodes"] == []


@pytest.mark.parametrize("existing,wanted", [(1, True), (1, 1.0000000001), (1000000000, 1000000001)])
def test_node_set_match_sid_uses_exact_integer_identity_not_float_tolerance(tmp_path, existing, wanted):
    source = deck_file(tmp_path / "main.k", f"*SET_NODE_LIST\n{existing}\n2,3\n")
    result = edit_deck(str(source), [dict(op="set_members", keyword="*SET_NODE_LIST", match=dict(sid=wanted), members=[4])],
                       output_dir=str(tmp_path / "out"))
    assert result["status"] == "failed" and not result["written"]
    if type(wanted) is int:
        assert read_fields(str(source), "*SET_NODE_LIST", dict(sid=wanted))["count"] == 0
    else:
        with pytest.raises(ValueError, match="identity"):
            read_fields(str(source), "*SET_NODE_LIST", dict(sid=wanted))


@pytest.mark.parametrize("form", ["generate", "add", "list"])
def test_large_node_id_limit_and_set_id_differences_are_not_continuous_float_tolerance(tmp_path, form):
    def content(value):
        if form == "generate":
            return f"*SET_NODE_LIST_GENERATE\n20\n0,{value}\n"
        if form == "add":
            return f"*SET_NODE_LIST\n1000000000\n2\n*SET_NODE_LIST\n1000000001\n3\n*SET_NODE_ADD\n20\n{value}\n"
        return f"*SET_NODE_LIST\n20\n{value}\n"
    before = deck_file(tmp_path / "a/main.k", content(1000000000))
    after = deck_file(tmp_path / "b/main.k", content(1000000001))
    assert compare_decks(str(before), str(after), include_mesh=False)["identical"] is False


def test_node_set_continuous_attributes_keep_existing_float_tolerance(tmp_path):
    before = deck_file(tmp_path / "a/main.k", "*SET_NODE_LIST\n20,1000000000\n2\n")
    after = deck_file(tmp_path / "b/main.k", "*SET_NODE_LIST\n20,1000000001\n2\n")
    assert compare_decks(str(before), str(after), include_mesh=False)["identical"] is True


@pytest.mark.parametrize("key", ["sid", "SID", "sId"])
@pytest.mark.parametrize("keyword", ["*SET_NODE_LIST", "*SET_*"])
@pytest.mark.parametrize("operation", ["read", "set_members", "delete"])
@pytest.mark.parametrize("existing,wanted", [(1, True), (1, 1.0000000001), (1000000000, 1000000001)])
def test_node_set_sid_exact_matching_depends_on_actual_block_not_input_spelling(tmp_path, key, keyword, operation, existing, wanted):
    source = deck_file(tmp_path / "main.k", f"*SET_NODE_LIST\n{existing}\n2,3\n")
    before = source.read_bytes()
    match = {key: wanted}
    if operation == "read":
        if type(wanted) is int:
            assert read_fields(str(source), keyword, match)["count"] == 0
        else:
            with pytest.raises(ValueError, match="identity"):
                read_fields(str(source), keyword, match)
    else:
        edit = dict(op=operation, keyword=keyword, match=match)
        if operation == "set_members":
            edit["members"] = [4]
        result = edit_deck(str(source), [edit], output_dir=str(tmp_path / "out"))
        assert result["status"] == "failed" and not result["written"]
    assert source.read_bytes() == before and not (tmp_path / "out").exists()


def test_glob_int_identities_are_exact_across_node_and_other_set_families(tmp_path):
    source = deck_file(tmp_path / "main.k", "*SET_NODE_LIST\n1000000000\n2,3\n*SET_PART_LIST\n1000000000\n1\n")
    result = read_fields(str(source), "*SET_*", {"SID": 1000000001})
    assert result["count"] == 0
