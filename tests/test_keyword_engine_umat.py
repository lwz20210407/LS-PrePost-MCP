"""Keyword engine: builtin layout for *MAT_USER_DEFINED_MATERIAL_MODELS (synthetic values)."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck, Unsupported


def _f(*values: object) -> str:
    return "".join(str(v).rjust(10) for v in values) + "\n"


def _deck(tmp_path: Path, text: str) -> KeywordDeck:
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    return KeywordDeck.load(tmp_path / "main.k")


def _umat(lmc: int, iortho: int = 0, lmca: int = 0, extra: str = "") -> str:
    text = "*MAT_USER_DEFINED_MATERIAL_MODELS_TITLE\nsynthetic umat\n"
    text += _f(7, 4.43, 41, lmc, 30, iortho, 3, 2) + _f(0, 1, 0, 0, 0, lmca, 0, 1)
    if iortho:
        text += _f(2.0, 1, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0) + _f(0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0)
    values = [float(i) for i in range(1, lmc + 1)]
    for start in range(0, lmc, 8):
        text += _f(*values[start:start + 8])
    for start in range(0, lmca, 8):
        text += _f(*[0.5] * min(8, lmca - start))
    return text + extra


def test_constants_by_name(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _umat(12) + "*END\n")
    block = deck.blocks("*MAT_USER_DEFINED_MATERIAL_MODELS")[0]
    assert deck.get(block, "lmc").value == 12 and deck.get(block, "p10").value == 10.0
    deck.set(block, "p10", 950.5)
    assert block.lines[5] == _f(9.0, 950.5, 11.0, 12.0)
    with pytest.raises(KeyError):
        deck.get(block, "p13")


def test_orthotropic_and_additional_constants(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _umat(8, iortho=1, lmca=3))
    block = deck.blocks("*MAT_USER_DEFINED_MATERIAL_MODELS")[0]
    assert deck.get(block, "aopt").value == 2.0 and deck.get(block, "p8").value == 8.0
    assert deck.get(block, "pa3").value == 0.5


def test_line_count_mismatch_is_refused(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _umat(12).replace(_f(9.0, 10.0, 11.0, 12.0), ""))
    with pytest.raises(Unsupported, match="expected"):
        deck.layout(deck.blocks("*MAT_USER_DEFINED_MATERIAL_MODELS")[0])


def test_umat_material_is_a_reference_target(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, "*PART\nplate\n" + _f(1, 1, 7) + "*SECTION_SOLID\n" + _f(1, 1) + _umat(8))
    assert deck.references().dangling() == []
