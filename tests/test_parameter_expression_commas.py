"""P02 fixed-width function arguments must not be mistaken for card separators."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.domain.model.parameters import evaluate_definition, parse_definitions


@pytest.mark.parametrize("line", ["Rmaxval   max(2, min(4, 8))\r\n", "Rmaxval,max(2, min(4, 8))\r\n"])
def test_parameter_function_argument_commas_are_expression_content(line):
    definitions, problems = parse_definitions("*PARAMETER_EXPRESSION", [(0, line)])
    assert not problems and len(definitions) == 1
    definition = definitions[0]
    evaluate_definition(definition, {})
    assert definition.name == "maxval" and definition.value == 4 and not definition.error
    assert definition.raw == "max(2, min(4, 8))"


@pytest.mark.parametrize("free", [False, True])
def test_edit_nested_function_expression_preserves_name_eol_and_unrelated_bytes(tmp_path, free):
    line = "Rmaxval,  max(2, min(4, 8))\r\n" if free else "Rmaxval   max(2, min(4, 8))\r\n"
    main = tmp_path / "main.k"
    prefix, suffix = b"$ untouched\r\n*KEYWORD\r\n*PARAMETER_EXPRESSION\r\n", b"*END\r\n"
    original = prefix + line.encode() + suffix
    main.write_bytes(original)
    deck = KeywordDeck.load(main)
    assert not deck.warnings
    deck.set_parameter("maxval", "max(3, min(6, 9))")
    assert next(r.definition.value for r in deck.parameters if r.definition.name == "maxval") == 6
    saved = deck.save_as(tmp_path / "saved")
    output = Path(saved["main"]).read_bytes()
    assert output == original.replace(b"max(2, min(4, 8))", b"max(3, min(6, 9))")
    assert main.read_bytes() == original and not saved["reload_warnings"]


def test_malformed_parameter_name_is_still_reported():
    definitions, problems = parse_definitions("*PARAMETER_EXPRESSION", [(0, "R bad name,max(2,3)\n")])
    assert not definitions and problems


@pytest.mark.parametrize("value", ["max(1,2)\n*INCLUDE\noutside.k", "__import__('os').getcwd()"])
def test_expression_edits_cannot_inject_cards_or_python_calls(tmp_path, value):
    from ls_prepost_mcp.domain.model import FieldError

    main = tmp_path / "main.k"
    original = b"*KEYWORD\n*PARAMETER_EXPRESSION\nRmaxval,max(2,3)\n*END\n"
    main.write_bytes(original)
    parsed = KeywordDeck.load(main)
    with pytest.raises(FieldError):
        parsed.set_parameter("maxval", value)
    assert parsed.main.data() == original and main.read_bytes() == original
