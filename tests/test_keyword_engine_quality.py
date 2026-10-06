"""Keyword-level element quality and model checks (engine definitions, synthetic meshes)."""
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.domain.model.layouts import Unsupported
from ls_prepost_mcp.domain.model.operations import check_deck
from ls_prepost_mcp.domain.model.quality import check_quality, coincident_nodes

pytest.importorskip("ansys.dyna.core")

CUBE = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]


def _node(nid: int, x: float, y: float, z: float) -> str:
    return f"{nid:>8}{x:>16}{y:>16}{z:>16}\n"


def _deck(tmp_path: Path, text: str) -> KeywordDeck:
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    return KeywordDeck.load(tmp_path / "main.k")


def _cube(order: tuple[int, ...]) -> str:
    text = "*NODE\n" + "".join(_node(i + 1, *map(float, p)) for i, p in enumerate(CUBE))
    return text + "*ELEMENT_SOLID\n" + f"{1:>8}{1:>8}" + "".join(f"{n:>8}" for n in order) + "\n"


def test_unit_cube_and_inverted_hexahedron(tmp_path: Path) -> None:
    good = check_quality(_deck(tmp_path, _cube((1, 2, 3, 4, 5, 6, 7, 8))))
    hexa = good["solids"]["hexahedra"]
    assert good["ok"] and hexa["min_scaled_jacobian"]["min"] == pytest.approx(1.0)
    assert hexa["volume"]["min"] == pytest.approx(1.0) and hexa["aspect_ratio"]["max"] == pytest.approx(1.0)
    (tmp_path / "bad").mkdir()
    bad = check_quality(_deck(tmp_path / "bad", _cube((5, 6, 7, 8, 1, 2, 3, 4))))
    assert not bad["ok"] and bad["errors"][0]["kind"] == "inverted_or_degenerate_hexahedra"


def test_tetrahedron_volume_sign(tmp_path: Path) -> None:
    text = ("*NODE\n" + _node(1, 0.0, 0.0, 0.0) + _node(2, 1.0, 0.0, 0.0) + _node(3, 0.0, 1.0, 0.0)
            + _node(4, 0.0, 0.0, 1.0) + "*ELEMENT_SOLID\n" + f"{1:>8}{1:>8}" + "".join(f"{n:>8}" for n in
            (1, 2, 3, 4, 4, 4, 4, 4)) + "\n")
    report = check_quality(_deck(tmp_path, text))
    assert report["ok"] and report["solids"]["tetrahedra"]["volume"]["min"] == pytest.approx(1 / 6)


def test_shell_metrics_and_thresholds(tmp_path: Path) -> None:
    text = ("*NODE\n" + _node(1, 0.0, 0.0, 0.0) + _node(2, 1.0, 0.0, 0.0) + _node(3, 1.0, 1.0, 0.0)
            + _node(4, 0.0, 1.0, 0.0) + _node(5, 2.0, 0.0, 0.0) + _node(6, 4.0, 1.0, 0.3)
            + "*ELEMENT_SHELL\n" + "       1       1       1       2       3       4\n"
            + "       2       1       2       5       6       3\n" + "       3       1       1       2       3       3\n")
    report = check_quality(_deck(tmp_path, text), thresholds={"aspect_ratio": 1.5, "warpage_deg": 1.0})
    shells = report["shells"]
    assert shells["count"] == 3 and shells["triangles"] == 1
    # square: 90 deg, aspect 1; right triangle: area 0.5, aspect sqrt(2); quad 2 is skewed and warped
    assert shells["min_angle_deg"]["max"] == pytest.approx(90.0) and shells["area"]["min"] == pytest.approx(0.5)
    assert shells["aspect_ratio"]["min"] == pytest.approx(1.0) and shells["warpage_deg"]["min"] == pytest.approx(0.0)
    assert shells["warpage_deg"]["failing_ids"] == [2] and shells["aspect_ratio"]["failing_ids"] == [2]
    assert report["ok"]


def test_coincident_nodes_across_grid_borders() -> None:
    ids = np.array([1, 2, 3])
    xyz = np.array([[0.9999999, 0.0, 0.0], [1.0000001, 0.0, 0.0], [5.0, 0.0, 0.0]])
    pairs = coincident_nodes(ids, xyz, 1e-6)
    assert [(a, b) for a, b, _ in pairs] == [(1, 2)]


def test_check_deck_reports_objective_errors(tmp_path: Path) -> None:
    text = ("*KEYWORD\n*PART\nplate\n         1         1         9\n*SECTION_SOLID\n         1         1\n"
            + _cube((1, 2, 3, 4, 5, 6, 7, 8)) + "*INCLUDE\nmissing.k\n*END\n")
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    result = check_deck(str(tmp_path / "main.k"), coincident_tol=1e-6)
    kinds = {e["kind"] for e in result["errors"]}
    assert not result["ok"] and kinds == {"include", "dangling_references"}
    assert result["quality"]["coincident_nodes"]["count"] == 0


def _shell_thickness(eight: bool) -> str:
    nodes = "".join(_node(i + 1, float(i % 3), float(i // 3), 0.0) for i in range(9))
    corners = ((1, 2, 5, 4, 7, 8, 9, 3) if eight else (1, 2, 5, 4, 0, 0, 0, 0), (2, 3, 6, 5, 0, 0, 0, 0))
    text = "*NODE\n" + nodes + "*ELEMENT_SHELL_THICKNESS\n"
    for eid, conn in enumerate(corners[:1] if eight else corners, 1):
        text += f"{eid:>8}{1:>8}" + "".join(f"{n:>8}" for n in conn) + "\n"
        text += f"{0.5 + eid:>16}{0.5:>16}{0.5:>16}{0.5:>16}{0.0:>16}\n"
        if eight:
            text += f"{0.7:>16}{0.7:>16}{0.7:>16}{0.7:>16}\n"
    return text


def test_shell_thickness_rows_and_quality(tmp_path: Path) -> None:
    deck = _deck(tmp_path, _shell_thickness(eight=False))
    block = deck.blocks("*ELEMENT_SHELL_THICKNESS")[0]
    assert deck.get(block, "thic1", row=2).value == pytest.approx(2.5)
    with pytest.raises(KeyError, match="thic5"):  # 4-node element: the thic5-8 line is absent
        deck.get(block, "thic5", row=2)
    report = check_quality(deck)
    assert report["shells"]["count"] == 2 and report["unchecked_mesh_blocks"] == []
    assert report["nodes_not_in_solid_or_shell_elements"]["count"] == 3  # nodes 7-9 are unused
    (tmp_path / "eight").mkdir()
    deck = _deck(tmp_path / "eight", _shell_thickness(eight=True))
    block = deck.blocks("*ELEMENT_SHELL_THICKNESS")[0]
    # PyDYNA decides on the thic5-8 card before reading rows, so 8-node rows fail its self-check:
    # refused (and reported as unchecked) rather than read without verification.
    with pytest.raises(Unsupported, match="PyDYNA"):
        deck.layout(block)
    assert check_quality(deck)["unchecked_mesh_blocks"]


def test_unread_element_variants_are_reported(tmp_path: Path) -> None:
    text = (_cube((1, 2, 3, 4, 5, 6, 7, 8)) + "*ELEMENT_SOLID_PERI\n       2       1       1       2       3       4"
            "       5       6       7       8\n")
    deck = _deck(tmp_path, text)
    report = check_quality(deck)
    assert report["solids"]["hexahedra"]["count"] == 1
    assert len(report["unchecked_mesh_blocks"]) == 1 and "*ELEMENT_SOLID_PERI" in report["unchecked_mesh_blocks"][0]
    assert "incomplete" in report["nodes_not_in_solid_or_shell_elements"]["note"]
    from ls_prepost_mcp.domain.model.geometry import select_elements
    with pytest.raises(Unsupported):
        select_elements(deck, "*ELEMENT_SOLID", parts=[1])


def test_parameter_depending_on_failed_definition_says_so(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "*PARAMETER_EXPRESSION\nR        a &missing+1\nR        b &a*2\n")
    errors = {r.definition.name: r.definition.error for r in deck.parameters}
    assert "Undefined parameter 'missing'" in errors["a"]
    assert "has no value" in errors["b"]


def test_check_deck_detects_six_injected_error_kinds(tmp_path: Path) -> None:
    """P09 acceptance: include, parameter, dangling, duplicate, inverted and undefined-node errors."""
    solid = "*ELEMENT_SOLID\n" + "".join(f"{eid:>8}{1:>8}" + "".join(f"{n:>8}" for n in conn) + "\n" for eid, conn in
                                         ((1, (5, 6, 7, 8, 1, 2, 3, 4)), (2, (1, 2, 3, 4, 5, 6, 7, 99))))
    text = ("*KEYWORD\n*PARAMETER_EXPRESSION\nR      bad &nope*2\n"
            "*PART\nplate\n         1         1         9\n"
            "*SECTION_SOLID\n         1         1\n*SECTION_SOLID\n         1         1\n"
            + _cube((1, 2, 3, 4, 5, 6, 7, 8)).split("*ELEMENT_SOLID")[0] + solid + "*INCLUDE\nmissing.k\n*END\n")
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    result = check_deck(str(tmp_path / "main.k"))
    kinds = {e["kind"] for e in result["errors"]}
    assert {"include", "parameter", "dangling_references", "duplicate_ids", "inverted_or_degenerate_hexahedra",
            "solids_with_undefined_nodes"} <= kinds
    assert not result["ok"] and result["read_only"]
    assert (tmp_path / "main.k").read_bytes() == text.encode("ascii")


def test_check_deck_survives_unreadable_node_block(tmp_path: Path) -> None:
    text = ("*KEYWORD\n" + _cube((1, 2, 3, 4, 5, 6, 7, 8)).replace("*ELEMENT_SOLID", "*NODE\n  x?  bad\n*ELEMENT_SOLID")
            + "*END\n")
    (tmp_path / "main.k").write_bytes(text.encode("ascii"))
    result = check_deck(str(tmp_path / "main.k"))
    assert not result["complete"] and any("*NODE" in item for item in result["unchecked"])
    assert result["quality"]["solids"]["hexahedra"]["count"] == 1


def test_missing_nodes_are_not_graded_when_a_node_block_is_unread(tmp_path: Path) -> None:
    text = (_cube((1, 2, 3, 4, 5, 6, 7, 99)) + "*NODE\n  x?  bad\n")
    report = check_quality(_deck(tmp_path, text))
    assert report["errors"] == [] and report["not_graded"][0]["kind"] == "solids_with_undefined_nodes"


def test_duplicate_element_ids_keep_their_ids(tmp_path: Path) -> None:
    line = f"{7:>8}{1:>8}" + "".join(f"{n:>8}" for n in (1, 2, 3, 4, 5, 6, 7, 8)) + "\n"
    text = _cube((1, 2, 3, 4, 5, 6, 7, 8)).split("*ELEMENT_SOLID")[0] + "*ELEMENT_SOLID\n" + line + line
    report = check_quality(_deck(tmp_path, text), thresholds={"aspect_ratio": 0.5})
    assert report["solids"]["hexahedra"]["aspect_ratio"]["failing_ids"] == [7, 7]


def test_cese_parts_and_unverified_references(tmp_path: Path) -> None:
    cube = _cube((1, 2, 3, 4, 5, 6, 7, 8)).replace(f"{1:>8}{1:>8}", f"{1:>8}{5:>8}", 1)
    deck = _deck(tmp_path, "*CESE_PART\n         5         1         1\n" + cube)
    report = deck.references()
    assert report.dangling_count == 0 and 5 in report.defined["part"]
    (tmp_path / "u").mkdir()
    text = ("*KEYWORD\n*PART\nplate\n         1         1         9\n*SECTION_SOLID\n         1         1\n"
            "*MAT_ELASTIC_UNKNOWNOPTION\n         9    7.8e-9  210000.0       0.3\n*END\n")
    (tmp_path / "u" / "main.k").write_bytes(text.encode("ascii"))
    result = check_deck(str(tmp_path / "u" / "main.k"), include_mesh=False)
    assert "dangling_references" not in {e["kind"] for e in result["errors"]}
    assert result["references"]["unverified_dangling"] == 1 and not result["complete"]
    assert any("could not be verified" in w for w in result["warnings"])


def test_coincident_nodes_is_exact() -> None:
    """Pairs straddling every cell border and non-adjacent pairs in one cell are found (brute force check)."""
    tol = 1.0
    straddle = coincident_nodes(np.array([1, 2]), np.array([[0.45, 0.0, 0.0], [1.05, 0.0, 0.0]]), tol)
    assert [(a, b) for a, b, _ in straddle] == [(1, 2)]
    cell = coincident_nodes(np.array([1, 2, 3]), np.array([[0.0, 0.0, 0.0], [0.9, 0.9, 0.9], [0.1, 0.1, 0.1]]), 0.5)
    assert [(a, b) for a, b, _ in cell] == [(1, 3)]
    rng = np.random.default_rng(7)
    xyz = rng.uniform(-5.0, 5.0, size=(400, 3))
    ids = np.arange(1, 401)
    tol = 0.6
    brute = {(int(ids[i]), int(ids[j])) for i in range(400) for j in range(i + 1, 400)
             if np.linalg.norm(xyz[i] - xyz[j]) <= tol}
    assert {(a, b) for a, b, _ in coincident_nodes(ids, xyz, tol)} == brute and brute
