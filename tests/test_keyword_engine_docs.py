"""Keyword and field documentation (I05/A10 keyword-field category)."""
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import keyword_docs as kd

pytest.importorskip("ansys.dyna.core")


def test_field_doc_from_pydyna_and_engine_rules() -> None:
    sfs = kd.field_doc("*CONTACT_ERODING_SURFACE_TO_SURFACE", "SFS")  # pre-R14 name of SFSA
    assert (sfs["field"], sfs["asked"], sfs["columns"], sfs["default"]) == ("sfsa", "sfs", "1-10", 1.0)
    assert "penalty stiffness" in sfs["help"] and sfs["evidence"] == "verified"
    part = kd.field_doc("*PART", "secid")
    assert part["refers_to"] == "section" and part["columns"] == "11-20"
    joint = kd.field_doc("*CONSTRAINED_JOINT_REVOLUTE_FAILURE", "tfail")
    assert joint["option"] == "FAILURE" and str(joint["card"]).startswith("engine:")
    assert kd.field_doc("*HOURGLASS", "qb_vdc")["columns"] == "61-70"  # schema name qb/vdc
    coded = {r["field"]: r["refers_to"] for r in kd.keyword_doc("*INITIAL_VELOCITY_GENERATION")["references"]}
    assert coded["id"].startswith("by styp: 1=part_set, 2=part")
    assert kd.keyword_doc("*MAT_ORTHOTROPIC_ELASTIC")["evidence"] == "documented"
    with pytest.raises(KeyError):
        kd.field_doc("*MAT_ELASTIC", "nosuchfield")


def _manual(tmp_path: Path) -> Path:
    """A synthetic two-page manual in the layout of the real text extraction (no manual text copied)."""
    sections = {"*MAT_SAMPLE": {"volume": "II", "pdf_pages": [10, 11], "printed": ["2-1", "2-2"]},
                "*MAT": {"volume": "II", "pdf_pages": [1, 400], "printed": ["2-0"]}}
    (tmp_path / "r17_pages.json").write_text(json.dumps({"manual": "synthetic", "sections": sections}))
    pages = ["=== [pdf page 10] ===", "*MAT_SAMPLE", "R17@abc (01/01/26)", "Card 1", "Variable", "EPS0", "D1",
             "Type", "EPS0", "Card 3b.  Include this card if X = 1.", "EPS0",
             "Reference strain rate for the sample;", "EQ.0.0: none.", "D1-D5", "Damage parameters of the sample.",
             "CP", "Heat capacity.", "=== [pdf page 11] ===", "2-2 (MAT)", "TM", "Melt temperature."]
    (tmp_path / "r17_volII.txt").write_text("\n".join(pages) + "\n", encoding="utf-8")
    return tmp_path


def test_manual_section_and_field_text(tmp_path: Path) -> None:
    folder = str(_manual(tmp_path))
    section = kd.manual_section("*MAT_SAMPLE_TITLE", folder)
    assert section["section"] == "*MAT_SAMPLE" and section["pdf_pages"] == [10, 11]
    assert kd.manual_field_text("*MAT_SAMPLE", "epso", folder) == "Reference strain rate for the sample; EQ.0.0: none."
    assert kd.manual_field_text("*MAT_SAMPLE", "d4", folder) == "Damage parameters of the sample."
    assert kd.manual_field_text("*MAT_SAMPLE", "tm", folder) == "Melt temperature."
    assert kd.manual_field_text("*MAT_SAMPLE", "xx", folder) is None
    assert kd.manual_section("*MAT_SAMPLE", str(tmp_path / "missing")) is None


def test_search_ranks_the_asked_field_first() -> None:
    top = kd.search("*CONTACT_ERODING 的 SFS 字段是什么意思", limit=3)
    assert all(r["keyword"].startswith("*CONTACT_ERODING") and r["field"] == "sfsa" for r in top)
    best = kd.search("*PART 的 SECID 指向什么", limit=1)[0]  # *PART is a table group: fields come from its cards
    assert (best["keyword"], best["field"], best["evidence"]) == ("*PART", "secid", "verified")
