"""Named numeric writes validate declared types before mutating the AST."""
from decimal import Decimal
from fractions import Fraction

import numpy as np
import pytest

from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.domain.model.fields import FieldError


@pytest.fixture
def model(tmp_path):
    source = tmp_path / "main.k"
    source.write_text("*KEYWORD\n*PARAMETER\nRfraction,1.5\nRwhole,2.0\nIvalid,2\n"
                      "*NODE\n1,0,0,0\n*PART\noriginal heading\n1,1,1\n*END\n", encoding="ascii")
    deck = KeywordDeck.load(source)
    return deck, deck.blocks("*PART")[0], deck.blocks("*NODE")[0]


@pytest.mark.parametrize("value", ["1.5", "NaN", "Inf", "1.0", "1e0", "1_0", "１２", "&fraction",
                                  np.bool_(True), np.array(1), Decimal("1.5"), Fraction(3, 2)])
def test_invalid_integer_writes_cannot_bypass_the_type_contract_or_change_memory(model, value):
    deck, part, _ = model
    before = deck.main.text()
    with pytest.raises(FieldError):
        deck.set(part, "mid", value, row=1)
    assert deck.main.text() == before


@pytest.mark.parametrize("value", ["NaN", "Inf", "-Inf", "1e9999", "not-a-number", np.bool_(True), np.array(2.5), 1+2j])
def test_float_writes_require_finite_real_scalars_or_supported_numeric_text(model, value):
    deck, _, node = model
    before = deck.main.text()
    with pytest.raises(FieldError):
        deck.set(node, "x", value, row=1)
    assert deck.main.text() == before


@pytest.mark.parametrize("value", [2, 2.0, "2", "+2", " 002 ", np.int64(2), np.float32(2), Decimal("2"), Fraction(2, 1), "&valid", "&whole"])
def test_valid_integer_scalars_literals_and_integral_parameter_results_stay_supported(model, value):
    deck, part, _ = model
    deck.set(part, "mid", value, row=1)
    assert deck.get(part, "mid", row=1).value == 2
    assert deck.get(part, "secid", row=1).value == 1


@pytest.mark.parametrize("value,expected", [(2.5, 2.5), ("2.5", 2.5), ("2.5d0", 2.5), ("2.5+0", 2.5),
    ("1.13000-4", 1.13e-4), (np.float32(2.5), 2.5), (Decimal("2.5"), 2.5), (Fraction(5, 2), 2.5),
    (2, 2), ("&fraction", 1.5)])
def test_continuous_fields_keep_fortran_text_parameters_and_numeric_scalar_forms(model, value, expected):
    deck, _, node = model
    deck.set(node, "x", value, row=1)
    assert deck.get(node, "x", row=1).value == expected
    assert deck.get(node, "y", row=1).value == 0


def test_blank_clear_and_text_fields_do_not_become_numeric_validation_targets(model):
    deck, part, node = model
    deck.set(part, "mid", "", row=1)
    assert deck.get(part, "mid", row=1).raw.strip() == ""
    deck.set(node, "x", "", row=1)
    assert deck.get(node, "x", row=1).raw.strip() == ""
    deck.set(part, "heading", "NaN is a title", row=1)
    assert deck.get(part, "heading", row=1).value == "NaN is a title"


def test_blank_row_identity_is_rejected_before_any_ast_mutation(model):
    deck, _, node = model
    before = deck.main.text()
    with pytest.raises(FieldError):
        deck.set(node, "nid", "", row=1)
    assert deck.main.text() == before


@pytest.mark.parametrize("value", ["1.5", "NaN"])
def test_public_edit_rejects_invalid_integer_text_without_publishing_an_output(tmp_path, value):
    pytest.importorskip("ansys.dyna.core")
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.service import Service

    source = tmp_path / "source" / "main.k"
    source.parent.mkdir()
    source.write_text("*KEYWORD\n*MAT_ELASTIC\n1,1,100,0.3\n*SECTION_SOLID\n1,1\n"
                      "*PART\noriginal\n1,1,1\n*END\n", encoding="ascii")
    before = source.read_bytes()
    service = Service(Settings(tmp_path / "work", allowed_roots=(source.parent,)))
    result = service.edit_keywords(str(source), [dict(op="set", keyword="*PART", match=dict(pid=1), field="mid", value=value)])
    assert result["status"] == "failed", "The named write must not publish an invalid integer field"
    assert result["data"].get("written", []) == []
    assert source.read_bytes() == before
