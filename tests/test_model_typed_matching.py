"""Integer identities are discrete even when nearby floats share a tolerance."""
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.domain.model.matching import scalar_equal
from ls_prepost_mcp.domain.model.operations import edit_deck, read_fields
from ls_prepost_mcp.service import Service


def source_file(folder: Path, *, family="part", identity=1000000000):
    folder.mkdir(parents=True, exist_ok=True)
    text = (f"*PART\npublic audit part\n{identity},1,1\n*SECTION_SOLID\n1,1\n*MAT_ELASTIC\n1,1,1000000000,0.3\n"
            if family == "part" else f"*MAT_ELASTIC\n{identity},1,1000000000,0.3\n")
    path = folder / "model.k"
    path.write_text("*KEYWORD_LONG\n" + text + "*END\n", encoding="ascii")
    return path


@pytest.mark.parametrize("family,keyword,identity", [("part", "*PART", "pid"), ("material", "*MAT_ELASTIC", "mid")])
@pytest.mark.parametrize("mode", ["find", "read", "set", "delete"])
def test_missing_part_or_material_id_never_matches_a_nearby_integer(tmp_path, family, keyword, identity, mode):
    source = source_file(tmp_path / "input", family=family)
    before = source.read_bytes()
    match = {identity.upper(): 1000000001}
    if mode == "find":
        assert KeywordDeck.load(source).find(keyword, **match) == []
    elif mode == "read":
        assert read_fields(str(source), keyword, match)["count"] == 0
    else:
        edit = dict(op=mode, keyword=keyword, match=match)
        if mode == "set":
            edit.update(field="heading" if family == "part" else "e", value="wrong target" if family == "part" else 42)
        result = edit_deck(str(source), [edit], output_dir=str(tmp_path / "saved"))
        assert result["status"] == "failed" and not result["written"]
        assert not (tmp_path / "saved").exists()
    assert source.read_bytes() == before


@pytest.mark.parametrize("bad", [True, 1.0000000001])
def test_integer_mat_field_rejects_boolean_or_fractional_identity(tmp_path, bad):
    source = source_file(tmp_path, family="material", identity=1)
    with pytest.raises(ValueError, match="integer identity"):
        KeywordDeck.load(source).find("*MAT_*", MID=bad)


@pytest.mark.parametrize("legal", [1, 1.0, "1"])
def test_exact_legacy_integer_input_forms_are_preserved(tmp_path, legal):
    source = source_file(tmp_path, family="material", identity=1)
    assert len(KeywordDeck.load(source).find("*MAT_ELASTIC", mid=legal)) == 1


def test_public_edit_keywords_cannot_publish_wrong_nearby_material(tmp_path):
    source = source_file(tmp_path / "input", family="material")
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    result = service.edit_keywords(str(source), [dict(op="set", keyword="*MAT_ELASTIC", match=dict(mid=1000000001), field="e", value=42)])
    assert result["status"] == "failed" and not result["artifacts"]


def test_integer_text_in_real_float_field_keeps_field_type_and_tolerance(tmp_path):
    source = source_file(tmp_path, family="material", identity=1)
    deck = KeywordDeck.load(source)
    block = deck.blocks("*MAT_ELASTIC")[0]
    assert deck.layout(block).lookup("e").kind == "float"
    assert type(deck.get(block, "e").value) is int  # lexical spelling cannot choose the policy
    assert deck.find("*MAT_ELASTIC", e=1000000001) == [(block, None)]
    assert not deck.find("*MAT_ELASTIC", e=1000000010)


def test_text_and_none_policies_do_not_change_between_callers():
    assert scalar_equal(" AbC ", "abc", "str", mode="find")
    assert not scalar_equal(" AbC ", "abc", "str", mode="compare")
    assert scalar_equal(" AbC ", "AbC", "str", mode="compare")
    assert scalar_equal(1000, "1000", "float", mode="find")
    assert not scalar_equal(1000, "1e3", "float", mode="find")
    assert not scalar_equal(1000, "1000", "float", mode="compare")
    assert scalar_equal(None, None, "int") and not scalar_equal(None, 0, "int")
    assert not scalar_equal(0, None, "int")


def test_discrete_zero_negative_codes_are_not_subject_to_id_range_policy():
    for value in (-1, 0, 2):
        assert scalar_equal(value, str(value), "int")
    assert not scalar_equal(1000000000, 1000000001, "int", rel_tol=1)
    assert scalar_equal(1000000000, 1000000001, "float")


def test_boolean_operation_flags_are_not_integer_field_inputs(tmp_path):
    source = source_file(tmp_path, family="material", identity=1)
    result = edit_deck(str(source), [dict(op="set", keyword="*MAT_ELASTIC", match=dict(mid=1), field="e", value=1000000000)],
                       in_place=False, check_mesh=True, allow_new_dangling=False)
    assert result["status"] == "succeeded" and not result["written"]
