"""JSON operations over the keyword engine (backend for model_info / edit_keywords / save_model)."""
import hashlib
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model.operations import edit_deck, inspect_deck, read_fields

pytest.importorskip("ansys.dyna.core")

MAIN = ("*KEYWORD\n"
        "*PARAMETER\n"
        "R thick          2.0\n"
        "*INCLUDE\n"
        "mat.k\n"
        "*PART\n"
        "plate\n"
        "         1         1         1\n"
        "*SECTION_SHELL_TITLE\n"
        "plate section\n"
        "         1        16\n"
        "    &thick    &thick    &thick    &thick\n"
        "*SET_NODE_LIST\n"
        "         7\n"
        "         1         2\n"
        "*DEFINE_CURVE\n"
        "         3\n"
        "                 0.0                 0.0\n"
        "                 1.0                 1.0\n"
        "*NODE\n"
        "       1             0.0             0.0             0.0\n"
        "       2            10.0             0.0             0.0\n"
        "*END\n")
MAT = ("*MAT_ELASTIC_TITLE\n"
       "steel\n"
       "         1      7.85  210000.0       0.3\n")


@pytest.fixture
def deck_path(tmp_path: Path) -> Path:
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "main.k").write_bytes(MAIN.encode("ascii"))
    (tmp_path / "in" / "mat.k").write_bytes(MAT.encode("ascii"))
    return tmp_path / "in" / "main.k"


def _hashes(folder: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob("*.k")}


def test_inspect_deck_overview(deck_path: Path) -> None:
    info = inspect_deck(str(deck_path), include_mesh=True)
    assert info["parts"][0]["pid"] == 1 and info["parts"][0]["heading"] == "plate"
    assert info["materials"][0]["mid"] == 1 and info["materials"][0]["title"] == "steel"
    assert info["sections"][0]["title"] == "plate section"
    assert info["sets"][0]["sid"] == 7 and info["sets"][0]["members"] == 2
    assert info["curves"][0]["points"] == 2
    assert info["parameters"][0]["name"] == "thick" and info["parameters"][0]["value"] == 2.0
    assert info["references"]["dangling"] == []
    assert info["include_tree"]["includes"][0]["name"] == "mat.k"


def test_read_fields_resolves_parameters(deck_path: Path) -> None:
    result = read_fields(str(deck_path), "*SECTION_SHELL", {"secid": 1}, ["t1", "elform"])
    fields = result["results"][0]["fields"]
    assert fields["t1"]["value"] == 2.0 and fields["t1"]["parameter"] == "thick"
    assert fields["elform"]["value"] == 16


def test_dry_run_writes_nothing(deck_path: Path) -> None:
    before = _hashes(deck_path.parent)
    result = edit_deck(str(deck_path), [{"op": "set", "keyword": "*MAT_ELASTIC", "match": {"mid": 1},
                                         "field": "pr", "value": 0.33}])
    assert result["status"] == "succeeded" and not result["written"]
    assert "+         1      7.85  210000.0      0.33" in result["diff"]
    assert _hashes(deck_path.parent) == before


def test_batch_saved_to_new_directory(deck_path: Path, tmp_path: Path) -> None:
    edits = [{"op": "set_parameter", "name": "thick", "value": 3.0},
             {"op": "set_members", "keyword": "*SET_NODE_LIST", "match": {"sid": 7}, "members": [2]},
             {"op": "set_points", "keyword": "*DEFINE_CURVE", "match": {"lcid": 3}, "points": [[0, 0], [2, 4]]},
             {"op": "insert", "file": "mat.k", "text": "*MAT_ELASTIC\n         2      2.70   70000.0      0.33\n"}]
    result = edit_deck(str(deck_path), edits, output_dir=str(tmp_path / "out"))
    assert result["status"] == "succeeded" and result["written"]
    saved = inspect_deck(str(tmp_path / "out" / "main.k"))
    assert saved["parameters"][0]["value"] == 3.0 and saved["sets"][0]["members"] == 1
    assert [m["mid"] for m in saved["materials"]] == [1, 2]


def test_failing_edit_aborts_whole_batch(deck_path: Path, tmp_path: Path) -> None:
    edits = [{"op": "set_parameter", "name": "thick", "value": 3.0},
             {"op": "set", "keyword": "*MAT_ELASTIC", "match": {"mid": 42}, "field": "pr", "value": 0.3}]
    result = edit_deck(str(deck_path), edits, output_dir=str(tmp_path / "out"))
    assert result["status"] == "failed" and result["failed_edit"] == 1 and not result["written"]
    assert not (tmp_path / "out").exists()


def test_new_dangling_reference_blocks_saving(deck_path: Path, tmp_path: Path) -> None:
    edit = [{"op": "set", "keyword": "*PART", "match": {"pid": 1}, "field": "mid", "value": 9}]
    result = edit_deck(str(deck_path), edit, output_dir=str(tmp_path / "out"))
    assert result["status"] == "failed" and result["new_dangling"][0]["id"] == 9
    assert not (tmp_path / "out").exists()
    allowed = edit_deck(str(deck_path), edit, output_dir=str(tmp_path / "out"), allow_new_dangling=True)
    assert allowed["status"] == "succeeded" and allowed["written"]


def test_delete_of_referenced_material_fails(deck_path: Path) -> None:
    result = edit_deck(str(deck_path), [{"op": "delete", "keyword": "*MAT_ELASTIC", "match": {"mid": 1}}])
    assert result["status"] == "failed" and "dangling" in result["error"]
