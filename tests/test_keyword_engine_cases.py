"""Parameter-study case generation at keyword level."""
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.domain.model.cases import generate_cases

pytest.importorskip("ansys.dyna.core")

MAIN = ("*KEYWORD\n"
        "*PARAMETER\n"
        "R vel          800.0\n"
        "*INCLUDE\n"
        "mat.k\n"
        "*INITIAL_VELOCITY_GENERATION\n"
        "         1         2       0.0       0.0       0.0   -&vel\n"
        "*END\n")
MAT = "*MAT_ELASTIC\n         1      7.85  210000.0       0.3\n"


@pytest.fixture
def base(tmp_path: Path) -> Path:
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "main.k").write_bytes(MAIN.encode("ascii"))
    (tmp_path / "base" / "mat.k").write_bytes(MAT.encode("ascii"))
    return tmp_path / "base" / "main.k"


def test_velocity_sweep(base: Path, tmp_path: Path) -> None:
    cases = [{"name": f"v{v}", "parameters": {"vel": float(v)}} for v in (600, 700, 900)]
    result = generate_cases(str(base), cases, str(tmp_path / "cases"))
    assert result["succeeded"] == 3 and result["failed"] == 0
    for v in (600, 700, 900):
        deck = KeywordDeck.load(tmp_path / "cases" / f"v{v}" / "main.k")
        assert [r.definition.value for r in deck.parameters] == [float(v)]
        assert (tmp_path / "cases" / f"v{v}" / "mat.k").read_bytes() == MAT.encode("ascii")
    first = result["cases"][0]["difference_from_base"]
    assert first["parameters"] == {"vel": {"a": 800.0, "b": 600.0}} and first["entities"] == {}
    assert json.loads((tmp_path / "cases" / "cases.json").read_text(encoding="utf-8"))["succeeded"] == 3


def test_failing_case_does_not_stop_others(base: Path, tmp_path: Path) -> None:
    cases = [{"name": "ok", "parameters": {"vel": 500.0}},
             {"name": "bad", "parameters": {"missing_parameter": 1.0}},
             {"name": "steel", "edits": [{"op": "set", "keyword": "*MAT_ELASTIC", "match": {"mid": 1},
                                          "field": "e", "value": 200000.0}]}]
    result = generate_cases(str(base), cases, str(tmp_path / "cases"))
    assert [c["status"] for c in result["cases"]] == ["succeeded", "failed", "succeeded"]
    assert result["cases"][2]["difference_from_base"]["entities"] == {"material": {"added_count": 0,
                                                                                  "removed_count": 0,
                                                                                  "changed_count": 1}}
    assert not (tmp_path / "cases" / "bad").exists()


def test_names_must_be_unique_and_output_empty(base: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        generate_cases(str(base), [{"name": "a"}, {"name": "a"}], str(tmp_path / "x"))
    (tmp_path / "busy").mkdir()
    (tmp_path / "busy" / "file.txt").write_text("x")
    with pytest.raises(FileExistsError):
        generate_cases(str(base), [{"name": "a"}], str(tmp_path / "busy"))
