"""Keyword engine: number formats, keyword spelling and block shapes found in real decks."""
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck, Unsupported
from ls_prepost_mcp.domain.model.fields import parse_number


@pytest.mark.parametrize(("text", "value"), [
    (" 1.13000-4", 1.13e-4), (" 2.1000+11", 2.1e11), ("1.0d-3", 1e-3), ("10-3", 1e-2),
    ("-5", -5), ("  ", None), (".5", 0.5), ("7.85e-9", 7.85e-9)])
def test_fortran_number_forms(text: str, value: float | None) -> None:
    assert parse_number(text) == (pytest.approx(value) if value is not None else None)


def _deck(tmp_path: Path, text: str) -> KeywordDeck:
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    return KeywordDeck.load(tmp_path / "main.k")


def test_lower_case_keyword_and_implicit_exponent(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, "*mat_elastic\n         1 7.85000-9 2.1000+05       0.3\n*end\n")
    block = deck.blocks("*MAT_ELASTIC")[0]
    assert deck.get(block, "ro").value == pytest.approx(7.85e-9)
    deck.set(block, "e", 70000.0)
    assert block.lines[1] == "         1 7.85000-9   70000.0       0.3\n"
    assert block.lines[0] == "*mat_elastic\n"


def test_repeated_card_instances_under_one_keyword(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, "*DEFINE_VECTOR\n"
                           "         1       0.0       0.0       0.0       1.0       0.0       0.0\n"
                           "         2       0.0       0.0       0.0       0.0       1.0       0.0\n")
    block = deck.blocks("*DEFINE_VECTOR")[0]
    layout = deck.layout(block)
    assert layout.key == "instance" and sorted(layout.rows) == [1, 2]
    assert deck.get(block, "vid", row=2).value == 2
    deck.set(block, "zt", 1.0, row=2)
    assert block.lines[2] == "         2       0.0       0.0       1.0       0.0       1.0       0.0\n"


def test_title_keyword_builtin(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*KEYWORD\n*TITLE\nold title\n*END\n")
    block = deck.blocks("*TITLE")[0]
    deck.set(block, "title", "new title")
    assert block.lines[1] == "new title\n"


def test_encrypted_block_is_refused(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*NODE\n-----BEGIN PGP MESSAGE-----\nabc\n-----END PGP MESSAGE-----\n")
    with pytest.raises(Unsupported):
        deck.layout(deck.blocks("*NODE")[0])


def test_unused_fields_are_not_editable(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, "*CONTROL_THERMAL_SOLVER\n"
                           "         1         0         0 1.0000E-4\n"
                           "         0       500\n")
    names = {info.name for info in deck.layout(deck.blocks("*CONTROL_THERMAL_SOLVER")[0]).fields}
    assert names and not any(name.startswith("unused") for name in names)


def test_list_set_header_and_members(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*SET_NODE_LIST_TITLE\r\n"
                           "top nodes\r\n"
                           "$#     sid       da1\r\n"
                           "        10       0.0\r\n"
                           "         1         2         3         4         5         6         7         8\r\n"
                           "$ second row\r\n"
                           "         9        11         0         0         0         0         0         0\r\n"
                           "*END\r\n")
    block = deck.blocks("*SET_NODE_LIST")[0]
    assert deck.get(block, "sid").value == 10 and deck.get(block, "title").value == "top nodes"
    assert deck.members(block) == [1, 2, 3, 4, 5, 6, 7, 8, 9, 11]
    deck.set_members(block, [21, 22, 23])
    assert deck.members(block) == [21, 22, 23]
    assert block.lines[:4] == ["*SET_NODE_LIST_TITLE\r\n", "top nodes\r\n", "$#     sid       da1\r\n",
                               "        10       0.0\r\n"]
    assert block.lines[4] == "        21        22        23\r\n" and "$ second row\r\n" in block.lines
    deck.set(block, "sid", 12)
    assert deck.get(block, "sid").value == 12


def test_empty_list_set_gets_members_after_header(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*SET_PART_LIST\n         5")
    block = deck.blocks("*SET_PART_LIST")[0]
    assert deck.members(block) == []
    deck.set_members(block, [1, 2])
    assert block.lines == ["*SET_PART_LIST\n", "         5\n", "         1         2\n"]


def test_curve_points_fixed_and_comma(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*DEFINE_CURVE_TITLE\n"
                           "ramp\n"
                           "         7         0       1.0       2.0\n"
                           "                 0.0                 0.0\n"
                           "0.001,1.0\n"
                           "*END\n")
    block = deck.blocks("*DEFINE_CURVE")[0]
    assert deck.get(block, "lcid").value == 7 and deck.get(block, "sfo").value == 2.0
    assert deck.points(block) == [(0.0, 0.0), (0.001, 1.0)]
    deck.set_points(block, [(0.0, 0.0), (5e-4, 0.5), (1e-3, 1.0)])
    assert deck.points(block) == [(0.0, 0.0), (5e-4, 0.5), (1e-3, 1.0)]
    assert block.lines[:3] == ["*DEFINE_CURVE_TITLE\n", "ramp\n", "         7         0       1.0       2.0\n"]
    assert block.lines[4] == "              0.0005                 0.5\n"


def test_members_reject_non_list_keywords(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*NODE\n       1             0.0             0.0             0.0\n")
    with pytest.raises(Unsupported):
        deck.members(deck.blocks("*NODE")[0])


def test_warm_up_runs_in_foreground_and_background() -> None:
    from ls_prepost_mcp.domain.model import warm_up

    assert warm_up(background=False) is None
    thread = warm_up()
    assert thread is not None
    thread.join(timeout=120)
    assert not thread.is_alive()


def test_include_file_name_edit_reloads_tree(tmp_path: Path) -> None:
    (tmp_path / "mat_a.k").write_bytes(b"*MAT_ELASTIC\n         1      7.85  210000.0       0.3\n")
    (tmp_path / "mat_b.k").write_bytes(b"*MAT_ELASTIC\n         1      2.70   70000.0      0.33\n")
    deck = _deck(tmp_path, "*KEYWORD\n*INCLUDE\nmat_a.k\n*END\n")
    block = deck.blocks("*INCLUDE")[0]
    assert deck.get(block, "filename").value == "mat_a.k"
    deck.set(block, "filename", "mat_b.k")
    assert block.lines[1] == "mat_b.k\n"
    assert sorted(f.path.name for f in deck.files.values()) == ["main.k", "mat_a.k", "mat_b.k"]
    assert [t["name"] for t in deck.include_tree()["includes"]] == ["mat_b.k"]


def test_save_as_writes_only_files_still_included(tmp_path: Path) -> None:
    (tmp_path / "mat_a.k").write_bytes(b"*MAT_ELASTIC\n         1      7.85  210000.0       0.3\n")
    (tmp_path / "mat_b.k").write_bytes(b"*MAT_ELASTIC\n         1      2.70   70000.0      0.33\n")
    deck = _deck(tmp_path, "*KEYWORD\n*INCLUDE\nmat_a.k\n*END\n")
    deck.set(deck.blocks("*INCLUDE")[0], "filename", "mat_b.k")
    out = tmp_path / "out"
    report = deck.save_as(out)
    assert sorted(p.name for p in out.iterdir()) == ["main.k", "mat_b.k"]
    assert report["skipped_unreferenced_edits"] == []


@pytest.mark.parametrize("encoding", ["utf-8", "gbk"])
def test_non_ascii_titles_follow_file_encoding(tmp_path: Path, encoding: str) -> None:
    text = "*KEYWORD\n$ \u6ce8\u91ca\n*PART\n\u94a2\u677f\n         1         1         1\n*END\n"
    (tmp_path / "main.k").write_bytes(text.encode(encoding))
    deck = KeywordDeck.load(tmp_path / "main.k")
    part = deck.blocks("*PART")[0]
    assert deck.get(part, "heading", row=1).value == "\u94a2\u677f"
    deck.set(part, "heading", "\u94dd\u5408\u91d1\u9776\u677f", row=1)
    out = tmp_path / "out"
    deck.save_as(out)
    expected = text.replace("\u94a2\u677f", "\u94dd\u5408\u91d1\u9776\u677f").encode(encoding)
    assert (out / "main.k").read_bytes() == expected


def test_title_with_commas_is_one_text_field(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, "*DEFINE_BOX_TITLE\n"
                           "screws (>ODB:9,  >SHELL_2,\n"
                           "  22012051 1140.6196 1149.2186 -299.5927  299.5903   11.5000   21.5468\n")
    block = deck.blocks("*DEFINE_BOX")[0]
    assert deck.get(block, "title").value == "screws (>ODB:9,  >SHELL_2,"
    assert deck.get(block, "xmx").value == pytest.approx(1149.2186)


def test_zero_link_field_matches_pydyna_unset(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, "*MAT_ADD_THERMAL_EXPANSION\n      2001         0   2.3E-05\n")
    block = deck.blocks("*MAT_ADD_THERMAL_EXPANSION")[0]
    assert deck.get(block, "lcid").value == 0 and deck.get(block, "mult").value == pytest.approx(2.3e-5)
    assert {"lcid", "lcid_2", "lcid_3"} <= {f.name for f in deck.layout(block).fields}


def test_ampersand_names_in_expressions_and_curve_points(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*PARAMETER\n"
                           "R tEnd        0.002\n"
                           "*PARAMETER_EXPRESSION\n"
                           "R tHalf    &tEnd/2\n"
                           "*DEFINE_CURVE\n"
                           "         1\n"
                           "                 0.0                 0.0\n"
                           "              &tHalf                 1.0\n"
                           "               &tEnd                 0.0\n")
    assert [r.definition.value for r in deck.parameters] == [0.002, 0.001]
    assert deck.points(deck.blocks("*DEFINE_CURVE")[0]) == [(0.0, 0.0), (0.001, 1.0), (0.002, 0.0)]


def test_inline_expressions_in_fields(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, "*PARAMETER\n"
                           "R tmax        0.004\n"
                           "*CONTROL_TERMINATION\n"
                           "<&tmax+1>\n"
                           "*DEFINE_CURVE\n"
                           "         1\n"
                           "                 0.0                 0.0\n"
                           "        &tmax*0.5                     1.0\n")
    block = deck.blocks("*CONTROL_TERMINATION")[0]
    value = deck.get(block, "endtim")
    assert value.value == pytest.approx(1.004) and value.parameter == "<&tmax+1>"
    assert deck.points(deck.blocks("*DEFINE_CURVE")[0])[1] == (pytest.approx(0.002), 1.0)
    deck.set(block, "endtim", "<&tmax*2>")
    assert deck.get(block, "endtim").value == pytest.approx(0.008)


def test_legacy_set_keywords_and_multi_line_title(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*TITLE\nfirst line\nsecond line\n*SET_PART\n         4\n         1         2\n")
    assert deck.get(deck.blocks("*TITLE")[0], "title").value == "first line"
    block = deck.blocks("*SET_PART")[0]
    assert deck.get(block, "sid").value == 4 and deck.members(block) == [1, 2]


@pytest.mark.parametrize("text", [
    # PyDYNA has no _ID option for this class: the JID line would be read as N1-N6
    "*CONSTRAINED_JOINT_REVOLUTE_ID\n         5\n   7700192   7700200   7700189   7700202         0         0\n",
    # PyDYNA puts the WID card first even without _ID
    "*CONSTRAINED_GENERALIZED_WELD_SPOT\n         4         0         0       0.0         0         0\n"
    "1.00000E20       0.0       0.0       0.0       0.0       0.0\n",
    "*CONSTRAINED_SPOTWELD\n       101       102       0.0       0.0       0.0       0.0       0.0       0.0\n"
    "       103       104       0.0       0.0       0.0       0.0       0.0       0.0\n",
])
def test_misaligned_pydyna_cards_are_refused(tmp_path: Path, text: str) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, text)
    with pytest.raises(Unsupported):
        deck.layout(next(b for b in deck.iter_blocks() if b.name))


def test_stray_text_policy() -> None:
    from ls_prepost_mcp.domain.model.fields import stray_text
    eight = [(10 * i, 10) for i in range(7)]  # a 7-field card read from an 8-field line
    assert stray_text("1,2,1e-08,0,0,0,0,0\n", eight) is None  # zero trailing field: tolerated
    assert stray_text("1,2,1e-08,0,0,0,0,5\n", eight) == "5"
    assert stray_text(f"{1:>10}{2:>10}" + " " * 50 + f"{0:>10}\n", eight) is None
    assert stray_text(f"{4:>10}{0:>10}{0:>10}\n", [(0, 10)]) == "0 0"  # ID card: nothing tolerated
    assert stray_text(f"{1:>10}{'':>10}{2:>10}\n", [(0, 10), (20, 10), (30, 10)]) is None  # blank gap
    assert stray_text(f"{1:>10}  7{'':>7}{3:>10}\n", [(0, 10), (20, 10), (30, 10)]) == "7"


def test_composite_shell_angles_with_zero_padding(tmp_path: Path) -> None:
    """NIP=1 needs one angle; LS-PrePost writes the whole 8-field angle line (public belted.k)."""
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, "*SECTION_SHELL\n       105         5     0.000         1         0         0         1\n"
                           "  0.304800  0.304800  0.304800  0.304800\n"
                           "     0.000     0.000     0.000     0.000     0.000     0.000     0.000     0.000\n")
    block = deck.blocks("*SECTION_SHELL")[0]
    assert deck.get(block, "t1").value == pytest.approx(0.3048)


def test_define_table_rows_hold_curve_ids(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*DEFINE_TABLE\n      1000\n           0.0000001                1001\n"
                           "               0.001                1002\n"
                           "*DEFINE_CURVE\n      1001\n                 0.0                 1.0\n")
    block = deck.blocks("*DEFINE_TABLE")[0]
    assert deck.get(block, "tbid").value == 1000 and deck.get(block, "sfa").value == 1.0
    assert deck.get(block, "lcid", row=2).value == 1002 and deck.get(block, "value", row=1).value == 1e-7
    report = deck.references()
    assert [(d["kind"], d["id"]) for d in report.dangling()] == [("curve", 1002)]
    deck.set(block, "lcid", 1001, row=2)
    assert deck.references().dangling_count == 0


def test_spotweld_id_uses_the_leading_wid_card(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = _deck(tmp_path, "*CONSTRAINED_SPOTWELD_ID\n        77\n"
                           "       101       102       0.0       0.0       0.0       0.0       0.0       0.0\n")
    block = deck.blocks("*CONSTRAINED_SPOTWELD_ID")[0]
    assert deck.get(block, "wid").value == 77 and deck.get(block, "n2").value == 102


def test_load_segment_rows_follow_the_manual(tmp_path: Path) -> None:
    """Several segments under one keyword; the N6-N8 line only after a segment with N5 (R11 p. 28-64)."""
    deck = _deck(tmp_path, "*LOAD_SEGMENT\n"
                           "         1    40.000                3001      3002      3003      3004\n"
                           "         1    40.000                3002      3005      3006      3003      3010\n"
                           "      3011      3012      3013\n"
                           "         2       1.0                3005      3007      3008      3006\n")
    block = deck.blocks("*LOAD_SEGMENT")[0]
    rows = deck.layout(block).rows
    assert len(rows) == 3
    assert deck.get(block, "n4", row=1).value == 3004 and deck.get(block, "sf", row=1).value == 40.0
    assert deck.get(block, "n8", row=2).value == 3013 and deck.get(block, "lcid", row=3).value == 2
    with pytest.raises(KeyError):
        deck.get(block, "n6", row=1)  # no midside line for a 4-node segment
    deck.set(block, "n1", 4001, row=3)
    assert deck.get(block, "n1", row=3).value == 4001
