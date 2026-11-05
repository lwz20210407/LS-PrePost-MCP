"""P1-5: function commas agree across evaluation, named fields and validation."""
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.domain.model.operations import check_deck
from ls_prepost_mcp.service import Service


def expression_deck(tmp_path, free):
    line = b"Rmaxval,max(2, min(4, 8))\r\n" if free else b"Rmaxval   max(2, min(4, 8))\r\n"
    path = tmp_path / "main.k"
    path.write_bytes(b"*KEYWORD\r\n*PARAMETER_EXPRESSION\r\n" + line
                     + b"*NODE\r\n1,&maxval,0,0\r\n*END\r\n")
    return path


@pytest.mark.parametrize("free", [False, True], ids=["fixed", "free"])
def test_check_deck_does_not_invent_free_format_width_errors_for_function_arguments(tmp_path, free):
    path = expression_deck(tmp_path, free)
    report = check_deck(str(path), include_mesh=False)
    assert not report["errors"], report["errors"]


@pytest.mark.parametrize("free", [False, True], ids=["fixed", "free"])
def test_named_expression_field_and_set_preserve_nested_arguments(tmp_path, free):
    path = expression_deck(tmp_path, free)
    original = path.read_bytes()
    deck = KeywordDeck.load(path)
    block = deck.blocks("*PARAMETER_EXPRESSION")[0]
    fields = {f.name: f for f in deck.fields(block, row=1)}
    assert fields["prmr"].value == "Rmaxval"
    assert fields["expression"].value == "max(2, min(4, 8))"
    deck.set(block, "expression", "max(3, min(6, 9))", row=1)
    assert next(r.definition.value for r in deck.parameters if r.definition.name == "maxval") == 6
    saved = deck.save_as(tmp_path / "output")
    assert Path(saved["main"]).read_bytes() == original.replace(b"max(2, min(4, 8))", b"max(3, min(6, 9))")
    assert path.read_bytes() == original


@pytest.mark.parametrize("free", [False, True], ids=["fixed", "free"])
def test_edit_keywords_can_set_a_function_expression_by_its_named_field(tmp_path, free):
    path = expression_deck(tmp_path, free)
    original = path.read_bytes()
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    result = service.edit_keywords(str(path), [{"op": "set", "keyword": "*PARAMETER_EXPRESSION", "match": {"prmr": "Rmaxval"},
                                              "field": "expression", "value": "max(3, min(6, 9))"}])
    assert result["status"] == "succeeded", result.get("error")
    reloaded = KeywordDeck.load(result["data"]["main"])
    assert next(r.definition.value for r in reloaded.parameters if r.definition.name == "maxval") == 6
    assert path.read_bytes() == original


@pytest.mark.parametrize("value", ["__import__('os').getcwd()", "max(1,2)\n*INCLUDE\noutside.k", "1/0"])
def test_named_expression_edit_retains_the_whitelisted_evaluator_and_is_atomic(tmp_path, value):
    from ls_prepost_mcp.domain.model import FieldError

    path = expression_deck(tmp_path, False)
    original = path.read_bytes()
    deck = KeywordDeck.load(path)
    block = deck.blocks("*PARAMETER_EXPRESSION")[0]
    with pytest.raises(FieldError):
        deck.set(block, "expression", value, row=1)
    assert deck.main.data() == original and path.read_bytes() == original
