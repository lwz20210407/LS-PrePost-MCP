"""Byte-preserving keyword engine (tasks.yaml I07): include tree, parameters, edits, save."""
import hashlib
import os
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import FieldError, KeywordDeck, Unsupported, persist
from ls_prepost_mcp.domain.model.blocks import parse_blocks
from ls_prepost_mcp.domain.model.fields import FieldSlot, format_value, write_text
from ls_prepost_mcp.domain.model.parameters import evaluate, parse_definitions
from ls_prepost_mcp.domain.model.text import decode, split_lines

MAIN = (
    "$ fixture main deck\n"
    "*KEYWORD\n"
    "*TITLE\n"
    "keyword engine fixture\n"
    "*PARAMETER\n"
    "R thick          2.0I nipp             3\n"
    "*PARAMETER_EXPRESSION\n"
    "R thick2   thick*2\n"
    "*INCLUDE_PATH\n"
    "lib\n"
    "*INCLUDE\n"
    "parts/parts.k\n"
    "*INCLUDE\n"
    "mat.k\n"
    "*SECTION_SHELL_TITLE\n"
    "plate\n"
    "$#   secid    elform      shrf       nip     propt   qr/irid     icomp     setyp\n"
    "         1        16  0.833333     &nipp       1.0         0         0         1\n"
    "$#      t1        t2        t3        t4      nloc     marea      idof    edgset\n"
    "    &thick    &thick    &thick    &thick       0.0       0.0       0.0         0\n"
    "*CONTROL_TERMINATION\n"
    "$#  endtim    endcyc     dtmin    endeng    endmas     nosol\n"
    "     0.001         0       0.0       0.0       0.0         0\n"
    "*END\n"
    "text after *END is ignored by LS-DYNA\n"
)
PARTS = (  # CRLF file
    "*PART\r\n"
    "plate part\r\n"
    "         1         1         1\r\n"
    "target part\r\n"
    "         2         1         2         0         0\r\n"
    "*INCLUDE\r\n"
    "mesh.k\r\n"
)
MESH = (
    "*NODE\n"
    "       1             0.0             0.0             0.0       0       0\n"
    "       2            10.0             0.0             0.0       0       0\n"
    "       3            10.0            10.0             0.0\n"
    "       4             0.0            10.0             0.0\n"
    "*ELEMENT_SHELL\n"
    "       1       1       1       2       3       4\n"
    "*END"  # no trailing newline
)
MAT = (
    "*MAT_PIECEWISE_LINEAR_PLASTICITY_TITLE\n"
    "steel\n"
    "$#     mid        ro         e        pr      sigy      etan      fail      tdel\n"
    "         1   7.85e-9  210000.0       0.3     350.0       0.0\n"
    "$#       c         p      lcss      lcsr        vp\n"
    "       0.0       0.0         0         0       0.0\n"
    "*MAT_ELASTIC\n"
    "2,7.85e-9,&E2,0.3\n"
    "*PARAMETER_LOCAL\n"
    "R E2         70000.0\n"
)
GBK_COMMENT = "$ 中文注释：靶板\n".encode("gbk")


@pytest.fixture
def deck_dir(tmp_path: Path) -> Path:
    (tmp_path / "parts").mkdir()
    (tmp_path / "lib").mkdir()
    (tmp_path / "main.k").write_bytes(MAIN.encode("ascii"))
    (tmp_path / "parts" / "parts.k").write_bytes(PARTS.encode("ascii"))
    (tmp_path / "parts" / "mesh.k").write_bytes(GBK_COMMENT + MESH.encode("ascii"))
    (tmp_path / "lib" / "mat.k").write_bytes(MAT.encode("ascii"))
    return tmp_path


def _digests(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*.k"))}


# ---------------------------------------------------------------- text and blocks
def test_blocks_join_back_to_identical_text() -> None:
    text = "$c\r\n*NODE\r\n 1,0,0,0\n*END\rtail\x85x"
    blocks = parse_blocks(text)
    assert "".join(b.text() for b in blocks) == text
    assert [b.kind for b in blocks] == ["preamble", "keyword", "keyword", "after_end"]


def test_split_lines_keeps_every_ending() -> None:
    assert split_lines("a\r\nb\nc\rd") == ["a\r\n", "b\n", "c\r", "d"]


def test_unedited_deck_round_trips_byte_for_byte(deck_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    deck = KeywordDeck.load(deck_dir / "main.k")
    assert deck.modified_files() == []
    out = tmp_path_factory.mktemp("out")
    report = deck.save_as(out)
    assert _digests(out) == _digests(deck_dir)
    assert report["reload_files"] == 4


# ---------------------------------------------------------------- includes and parameters
def test_include_tree_records_resolution_rules(deck_dir: Path) -> None:
    deck = KeywordDeck.load(deck_dir / "main.k")
    tree = deck.include_tree()["includes"]
    rules = {entry["name"]: entry["rule"] for entry in tree if entry["kind"] == "file"}
    assert rules == {"parts/parts.k": "including_dir", "mat.k": "include_path"}
    nested = [e for e in tree if e["name"] == "parts/parts.k"][0]["includes"]
    assert nested[0]["name"] == "mesh.k" and nested[0]["rule"] == "including_dir"
    assert deck.warnings == []


def test_reading_order_expands_includes_in_place(deck_dir: Path) -> None:
    names = [b.name for b in KeywordDeck.load(deck_dir / "main.k").iter_blocks()]
    assert names.index("*PART") < names.index("*NODE") < names.index("*MAT_ELASTIC") < names.index("*SECTION_SHELL_TITLE")


def test_missing_and_cyclic_includes_are_warnings(tmp_path: Path) -> None:
    (tmp_path / "a.k").write_text("*INCLUDE\nb.k\n*INCLUDE\nnone.k\n")
    (tmp_path / "b.k").write_text("*INCLUDE\na.k\n")
    deck = KeywordDeck.load(tmp_path / "a.k")
    assert any("Missing include 'none.k'" in w for w in deck.warnings)
    assert any("cycle" in w for w in deck.warnings)


def test_ambiguous_include_is_reported(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "main.k").write_text("*INCLUDE\nsub/child.k\n")
    (tmp_path / "sub" / "child.k").write_text("*INCLUDE\nshared.k\n")
    (tmp_path / "sub" / "shared.k").write_text("*NODE\n")
    (tmp_path / "shared.k").write_text("*NODE\n")
    deck = KeywordDeck.load(tmp_path / "main.k")
    assert any(w.startswith("Ambiguous include 'shared.k'") for w in deck.warnings)


def test_long_include_name_with_continuation(tmp_path: Path) -> None:
    (tmp_path / "a_very_long_directory_name").mkdir()
    (tmp_path / "a_very_long_directory_name" / "part.k").write_text("*NODE\n")
    (tmp_path / "main.k").write_text("*INCLUDE\na_very_long_directory_name/ +\npart.k\n")
    deck = KeywordDeck.load(tmp_path / "main.k")
    assert len(deck.files) == 2 and deck.warnings == []


def test_parameters_global_local_and_expressions(deck_dir: Path) -> None:
    deck = KeywordDeck.load(deck_dir / "main.k")
    values = {r.definition.name: r.definition.value for r in deck.parameters}
    assert values == {"thick": 2.0, "nipp": 3, "thick2": 4.0, "E2": 70000.0}
    main_block = deck.blocks("*SECTION_SHELL")[0]
    mat_block = deck.blocks("*MAT_ELASTIC")[0]
    assert "e2" not in deck.lookup(main_block)
    assert deck.lookup(mat_block)["e2"] == 70000.0


def test_parameter_syntax_variants() -> None:
    data = [(1, "rterm, 0.2, istaTES, 80\n"), (2, "r E          12.3\n"), (3, "cpaR1, foo\n")]
    definitions, problems = parse_definitions("*PARAMETER", data)
    assert problems == []
    assert [(d.type, d.name, d.raw) for d in definitions] == [
        ("real", "term", "0.2"), ("integer", "staTES", "80"), ("real", "E", "12.3"), ("character", "paR1", "foo")]
    assert evaluate("tErm/(States-30)", {"term": 0.2, "states": 80}) == pytest.approx(0.004)
    assert evaluate("sqrt(a)+max(1,2)^2+1.d1", {"a": 4}) == pytest.approx(16.0)


def test_expression_rejects_unsafe_constructs() -> None:
    for source in ("__import__('os')", "a.b", "[1]", "lambda: 1"):
        with pytest.raises(FieldError):
            evaluate(source, {"a": 1})


def test_bad_parameter_name_is_a_warning_not_a_crash(tmp_path: Path) -> None:
    (tmp_path / "main.k").write_text("*PARAMETER\nX bad           1.0\n*END\n")
    deck = KeywordDeck.load(tmp_path / "main.k")
    assert any("Invalid parameter name field" in w for w in deck.warnings)


# ---------------------------------------------------------------- fields
def test_format_value_fits_width_and_reports_precision() -> None:
    assert format_value(210000.0, 10) == ("210000.0", True)
    assert format_value(7.85e-09, 10) == ("7.85e-09", True)
    assert format_value(1e21, 10) == ("1e+21", True)
    text, exact = format_value(1.0 / 3.0, 10)
    assert len(text) <= 10 and not exact
    with pytest.raises(FieldError):
        format_value(12345678901, 10, "int")


def test_write_text_changes_only_the_field() -> None:
    line = "         1   7.85e-9  210000.0       0.3     350.0       0.0\r\n"
    new = write_text(line, FieldSlot(0, 40, 10), "420.5")
    assert new[:40] == line[:40] and new[50:] == line[50:] and new[40:50] == "     420.5"


def test_named_read_with_parameter_references(deck_dir: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = KeywordDeck.load(deck_dir / "main.k")
    section = deck.blocks("*SECTION_SHELL")[0]
    nip = deck.get(section, "nip")
    assert (nip.value, nip.parameter) == (3, "nipp")
    assert deck.get(section, "t1").value == 2.0
    assert deck.get(section, "title").value == "plate"


def test_named_edit_touches_only_one_field_in_one_file(deck_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = KeywordDeck.load(deck_dir / "main.k")
    block, _ = deck.find("*MAT_*", mid=1)[0]
    change = deck.set(block, "sigy", 420.5)
    assert change.exact and change.after[40:50] == "     420.5"
    out = tmp_path_factory.mktemp("out")
    deck.save_as(out)
    before, after = _digests(deck_dir), _digests(out)
    assert {k for k in before if before[k] != after[k]} == {str(Path("lib") / "mat.k")}
    old = (deck_dir / "lib" / "mat.k").read_bytes().splitlines(keepends=True)
    new = (out / "lib" / "mat.k").read_bytes().splitlines(keepends=True)
    assert [i for i, (a, b) in enumerate(zip(old, new)) if a != b] == [3]


def test_comma_line_edit_replaces_one_token(deck_dir: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = KeywordDeck.load(deck_dir / "main.k")
    block = deck.blocks("*MAT_ELASTIC")[0]
    assert deck.get(block, "e").value == 70000.0
    deck.set(block, "pr", 0.33)
    assert block.lines[1] == "2,7.85e-9,&E2,0.33\n"


def test_part_row_edit_keeps_crlf(deck_dir: Path) -> None:
    deck = KeywordDeck.load(deck_dir / "main.k")
    (block, row), = deck.find("*PART", pid=2)
    deck.set(block, "mid", 7, row=row)
    assert block.lines[4] == "         2         1         7         0         0\r\n"
    assert deck.get(block, "heading", row=2).value == "target part"


def test_node_row_edit_uses_16_character_coordinates(deck_dir: Path) -> None:
    deck = KeywordDeck.load(deck_dir / "main.k")
    block = deck.blocks("*NODE")[0]
    deck.set(block, "x", 12.5, row=3)
    assert block.lines[3] == "       3            12.5            10.0             0.0\n"
    assert deck.get(block, "y", row=3).value == 10.0


def test_parameter_reference_can_be_written(deck_dir: Path) -> None:
    pytest.importorskip("ansys.dyna.core")
    deck = KeywordDeck.load(deck_dir / "main.k")
    section = deck.blocks("*SECTION_SHELL")[0]
    deck.set(section, "t2", "&thick2")
    assert deck.get(section, "t2").value == 4.0
    with pytest.raises(FieldError):
        deck.set(section, "t3", "&undefined")


def test_unsupported_keyword_falls_back_to_positional(deck_dir: Path) -> None:
    deck = KeywordDeck.load(deck_dir / "main.k")
    block = deck.blocks("*ELEMENT_SHELL")[0]
    with pytest.raises((Unsupported, KeyError)):
        deck.set(block, "pid", 2)
    deck.set_position(block, 0, "2", field_index=1, width=8)
    assert block.lines[1] == "       1       2       1       2       3       4\n"


def test_i10_format_blocks_are_positional_only(tmp_path: Path) -> None:
    (tmp_path / "main.k").write_bytes(b"*NODE%\n         1               0.0\n*END\n")
    deck = KeywordDeck.load(tmp_path / "main.k")
    with pytest.raises(Unsupported):
        deck.layout(deck.blocks("*NODE")[0])


# ---------------------------------------------------------------- blocks and saving
def test_insert_before_end_uses_file_newline_and_keeps_other_bytes(deck_dir: Path) -> None:
    deck = KeywordDeck.load(deck_dir / "main.k")
    parts = [f for f in deck.files.values() if f.path.name == "parts.k"][0]
    new = deck.insert("*SET_NODE_LIST\n         1\n         1         2\n", file=parts)
    assert new[0].lines[0] == "*SET_NODE_LIST\r\n"
    assert parts.data().startswith(PARTS.encode("ascii"))


def test_insert_into_file_without_trailing_newline(deck_dir: Path) -> None:
    deck = KeywordDeck.load(deck_dir / "main.k")
    mesh = [f for f in deck.files.values() if f.path.name == "mesh.k"][0]
    deck.insert("*SET_PART_LIST\n         1\n         1\n", file=mesh)
    text = decode(mesh.data())
    assert text.endswith("*SET_PART_LIST\n         1\n         1\n*END")
    assert mesh.data().startswith(GBK_COMMENT)


def test_delete_block(deck_dir: Path) -> None:
    deck = KeywordDeck.load(deck_dir / "main.k")
    deck.delete(deck.blocks("*CONTROL_TERMINATION")[0])
    assert "*CONTROL_TERMINATION" not in deck.main.text()
    assert "text after *END" in deck.main.text()


def test_inserting_an_include_updates_the_tree(deck_dir: Path) -> None:
    (deck_dir / "extra.k").write_text("*NODE\n")
    deck = KeywordDeck.load(deck_dir / "main.k")
    deck.insert("*INCLUDE\nextra.k\n")
    assert len(deck.files) == 5


def test_save_in_place_writes_backup_once(deck_dir: Path) -> None:
    deck = KeywordDeck.load(deck_dir / "main.k")
    original = (deck_dir / "parts" / "parts.k").read_bytes()
    (block, row), = deck.find("*PART", pid=1)
    deck.set(block, "secid", 3, row=row)
    report = deck.save_in_place()
    assert [Path(r["path"]).name for r in report["written"]] == ["parts.k"]
    assert (deck_dir / "parts" / "parts.k.orig").read_bytes() == original
    deck.set(block, "secid", 4, row=row)
    with pytest.raises(FileExistsError):
        deck.save_in_place()


def _deny_replace(monkeypatch, name: str, times: int) -> list[float]:
    """Make ``os.replace`` onto ``name`` fail like a Windows reader holding it; return the backoff."""
    replace, delays, left = os.replace, [], [times]

    def flaky(source, destination):
        if Path(destination).name == name and left[0]:
            left[0] -= 1
            error = PermissionError("Temporarily denied by a Windows reader")
            error.winerror = 5
            raise error
        replace(source, destination)

    monkeypatch.setattr(persist.os, "replace", flaky)
    monkeypatch.setattr(persist.time, "sleep", delays.append)
    return delays


def test_atomic_write_retries_brief_windows_sharing_denials(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "a.k"
    target.write_bytes(b"old")
    delays = _deny_replace(monkeypatch, "a.k", 2)
    persist.atomic_write(target, b"new")
    assert target.read_bytes() == b"new" and delays == [0.02, 0.04]
    assert [p.name for p in tmp_path.iterdir()] == ["a.k"]


def test_atomic_write_gives_up_without_leaving_a_temporary(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "a.k"
    target.write_bytes(b"old")
    delays = _deny_replace(monkeypatch, "a.k", 99)
    with pytest.raises(PermissionError):
        persist.atomic_write(target, b"new")
    assert delays == list(persist.SHARING_DELAYS)
    assert target.read_bytes() == b"old" and [p.name for p in tmp_path.iterdir()] == ["a.k"]


def test_atomic_write_does_not_retry_errors_without_a_sharing_code(tmp_path: Path, monkeypatch) -> None:
    delays: list[float] = []

    def denied(source, destination):
        raise PermissionError("POSIX EACCES")

    monkeypatch.setattr(persist.os, "replace", denied)
    monkeypatch.setattr(persist.time, "sleep", delays.append)
    with pytest.raises(PermissionError):
        persist.atomic_write(tmp_path / "a.k", b"new")
    assert delays == [] and list(tmp_path.iterdir()) == []


def test_failed_save_in_place_keeps_the_file_and_can_be_retried(deck_dir: Path, monkeypatch) -> None:
    deck = KeywordDeck.load(deck_dir / "main.k")
    original = (deck_dir / "parts" / "parts.k").read_bytes()
    (block, row), = deck.find("*PART", pid=1)
    deck.set(block, "secid", 3, row=row)
    _deny_replace(monkeypatch, "parts.k", 99)
    with pytest.raises(PermissionError):
        deck.save_in_place()
    assert (deck_dir / "parts" / "parts.k").read_bytes() == original
    assert sorted(p.name for p in (deck_dir / "parts").iterdir()) == ["mesh.k", "parts.k"]
    monkeypatch.undo()
    report = deck.save_in_place()
    assert [Path(r["path"]).name for r in report["written"]] == ["parts.k"]
    assert (deck_dir / "parts" / "parts.k.orig").read_bytes() == original


def test_save_in_place_keeps_the_backup_when_the_file_was_replaced(deck_dir: Path, monkeypatch) -> None:
    deck = KeywordDeck.load(deck_dir / "main.k")
    original = (deck_dir / "parts" / "parts.k").read_bytes()
    (block, row), = deck.find("*PART", pid=1)
    deck.set(block, "secid", 3, row=row)
    replace = os.replace

    def replaced_then_failed(source, destination):  # e.g. a network share reporting late
        replace(source, destination)
        if Path(destination).name == "parts.k":
            raise OSError("reported after the rename")

    monkeypatch.setattr(persist.os, "replace", replaced_then_failed)
    with pytest.raises(OSError) as raised:
        deck.save_in_place()
    assert (deck_dir / "parts" / "parts.k").read_bytes() != original
    assert (deck_dir / "parts" / "parts.k.orig").read_bytes() == original
    assert "parts.k.orig was kept" in "".join(raised.value.__notes__)


def test_failed_second_file_keeps_the_first_backup(deck_dir: Path, monkeypatch) -> None:
    deck = KeywordDeck.load(deck_dir / "main.k")
    deck.set(deck.blocks("*CONTROL_TERMINATION")[0], "endtim", 0.002)
    (block, row), = deck.find("*PART", pid=1)
    deck.set(block, "secid", 3, row=row)
    first, second = (f.path for f in persist.modified_files(deck))
    before = {path: path.read_bytes() for path in (first, second)}
    _deny_replace(monkeypatch, second.name, 99)
    with pytest.raises(PermissionError):
        deck.save_in_place()
    assert Path(str(first) + ".orig").read_bytes() == before[first]
    assert second.read_bytes() == before[second] and not Path(str(second) + ".orig").exists()
    monkeypatch.undo()
    report = deck.save_in_place()
    assert [r["path"] for r in report["written"]] == [str(second)]
    assert Path(str(second) + ".orig").read_bytes() == before[second]


def test_save_as_refuses_to_overwrite_inputs(deck_dir: Path) -> None:
    deck = KeywordDeck.load(deck_dir / "main.k")
    with pytest.raises(ValueError):
        deck.save_as(deck_dir)


def test_diff_lists_only_changed_lines(deck_dir: Path) -> None:
    deck = KeywordDeck.load(deck_dir / "main.k")
    (block, row), = deck.find("*PART", pid=1)
    deck.set(block, "mid", 5, row=row)
    diff = deck.diff()
    changed = [line for line in diff.splitlines() if line[:1] in "+-" and line[:3] not in ("+++", "---")]
    assert changed == ["-         1         1         1", "+         1         1         5"]
