"""P12 joints: add_joint writes valid *CONSTRAINED_JOINT cards and sides; check_joints finds real defects."""
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.domain.model.fields import FieldError
from ls_prepost_mcp.domain.model.joint_checks import check_joints
from ls_prepost_mcp.domain.model.joints import add_joint
from ls_prepost_mcp.domain.model.operations import check_deck, edit_deck

pytest.importorskip("ansys.dyna.core")


def _brick(pid: int, base: int, lo: tuple, hi: tuple) -> tuple[list[str], str]:
    corners = [(lo[0], lo[1], lo[2]), (hi[0], lo[1], lo[2]), (hi[0], hi[1], lo[2]), (lo[0], hi[1], lo[2]),
               (lo[0], lo[1], hi[2]), (hi[0], lo[1], hi[2]), (hi[0], hi[1], hi[2]), (lo[0], hi[1], hi[2])]
    nodes = [f"{base + i + 1:>8}" + "".join(f"{float(v):>16}" for v in c) for i, c in enumerate(corners)]
    return nodes, f"{base + 1:>8}{pid:>8}" + "".join(f"{base + i + 1:>8}" for i in range(8))


def _deck(tmp_path: Path, extra: str = "", deformable: bool = False) -> Path:
    base, e1 = _brick(1, 0, (-20, -20, 5), (20, 20, 25))
    bar, e2 = _brick(2, 100, (-5, -5, -200), (5, 5, 0))
    plate, e3 = _brick(3, 200, (30, -5, -10), (50, 5, 0))
    mat2 = "*MAT_ELASTIC\n         3   7.85e-9  210000.0       0.3\n" if deformable else ""
    text = ["*KEYWORD", "*NODE", *base, *bar, *plate, "*ELEMENT_SOLID", e1, e2, e3, "*SECTION_SOLID", f"{1:>10}{1:>10}",
            "*PART", "base", f"{1:>10}{1:>10}{1:>10}", "*PART", "bar", f"{2:>10}{1:>10}{2:>10}",
            "*PART", "plate", f"{3:>10}{1:>10}{3 if deformable else 2:>10}",
            "*MAT_RIGID", f"{1:>10}{7.85e-9:>10}{210000.0:>10}{0.3:>10}", f"{1.0:>10}{7.0:>10}{7.0:>10}", f"{0.0:>10}",
            "*MAT_RIGID", f"{2:>10}{7.85e-9:>10}{210000.0:>10}{0.3:>10}", f"{0.0:>10}", f"{0.0:>10}", mat2.rstrip("\n"),
            extra.rstrip("\n"), "*END"]
    path = tmp_path / "joints.k"
    path.write_text("\n".join(line for line in text if line) + "\n")
    return path


def _positions(deck: KeywordDeck) -> dict:
    from ls_prepost_mcp.domain.model.geometry import nodes
    ids, xyz = nodes(deck)
    return dict(zip(ids.tolist(), xyz))


@pytest.mark.parametrize("kind, extra, pairs", [
    ("spherical", {}, [(1, 2)]),
    ("revolute", {"axis": [0, 1, 0]}, [(1, 2), (3, 4)]),
    ("cylindrical", {"axis": [0, 1, 0]}, [(1, 2), (3, 4)]),
    ("planar", {"axis": [0, 0, 1]}, [(1, 2), (3, 4)]),
    ("translational", {"axis": [1, 0, 0]}, [(1, 2), (3, 4), (5, 6)]),
    ("locking", {"axis": [1, 0, 0]}, [(1, 2), (3, 4), (5, 6)]),
    ("universal", {"axis": [1, 0, 0], "second_axis": [0, 1, 0]}, [(1, 2)]),
])
def test_each_joint_kind_is_written_and_checks_clean(tmp_path: Path, kind: str, extra: dict, pairs: list) -> None:
    deck = KeywordDeck.load(_deck(tmp_path))
    out = add_joint(deck, kind, {"part": 1}, {"part": 2}, [0, 0, 0], length=40.0, **extra)
    assert out["keyword"] == f"*CONSTRAINED_JOINT_{kind.upper()}_ID" and out["jid"] == 1
    pos = _positions(deck)
    nodes = {int(k[1:]): v for k, v in out["nodes"].items()}
    for i, j in pairs:
        assert np.allclose(pos[nodes[i]], pos[nodes[j]])
    if kind == "universal":
        assert abs((pos[nodes[3]] - pos[nodes[1]]) @ (pos[nodes[4]] - pos[nodes[2]])) < 1e-9
    report = check_joints(deck)
    assert not report["errors"] and report["joints"][0]["body_a"] == ("part", 1)
    assert report["joints"][0]["body_b"] == ("part", 2)
    assert out["side_a"]["rigid_part"] == 1 and out["side_b"]["rigid_part"] == 2


def test_motor_parm_card_failure_and_local_cards_read_back(tmp_path: Path) -> None:
    deck = KeywordDeck.load(_deck(tmp_path))
    out = add_joint(deck, "rotational_motor", {"part": 1}, {"part": 2}, [0, 0, 0], axis=[0, 1, 0], length=40.0,
                    motor={"curve": {"points": [[0, 6.28], [1, 6.28]]}, "type": "velocity"},
                    failure={"tfail": 0.3}, local={"raid": 1})
    block = next(b for b in deck.iter_blocks() if b.name.startswith("*CONSTRAINED_JOINT_ROTATIONAL_MOTOR"))
    assert block.name == "*CONSTRAINED_JOINT_ROTATIONAL_MOTOR_ID_LOCAL_FAILURE"
    assert deck.get(block, "lcid").value == out["lcid"] and deck.get(block, "type").value == 0
    assert deck.get(block, "tfail").value == pytest.approx(0.3) and deck.get(block, "raid").value == 1
    assert any("penalty" in w for w in out["warnings"])  # no *CONTROL_RIGID LMF=1


def test_motor_warning_disappears_with_lagrange_multipliers(tmp_path: Path) -> None:
    deck = KeywordDeck.load(_deck(tmp_path, "*CONTROL_RIGID\n         1"))
    out = add_joint(deck, "rotational_motor", {"part": 1}, {"part": 2}, [0, 0, 0], axis=[0, 1, 0], length=40.0,
                    motor={"curve": {"points": [[0, 1.0], [1, 1.0]]}})
    assert "warnings" not in out


def test_deformable_side_needs_nodes_and_gets_a_nodal_rigid_body(tmp_path: Path) -> None:
    deck = KeywordDeck.load(_deck(tmp_path, deformable=True))
    with pytest.raises(FieldError, match="not a rigid part"):
        add_joint(deck, "revolute", {"part": 1}, {"part": 3}, [40, 0, 0], axis=[0, 1, 0], length=20.0)
    held = [205, 206, 207, 208]  # top face of the plate
    out = add_joint(deck, "revolute", {"part": 1}, {"nodes": held}, [40, 0, 0], axis=[0, 1, 0], length=20.0)
    cnrb = out["side_b"]["nodal_rigid_body"]
    assert cnrb not in (1, 2, 3) and out["side_b"]["held_nodes"] == 4
    assert check_joints(deck)["joints"][0]["body_b"] == ("cnrb", cnrb)
    with pytest.raises(FieldError, match="already belong to a rigid body"):
        add_joint(deck, "spherical", {"part": 1}, {"nodes": [205]}, [40, 0, 0])


def test_existing_nodal_rigid_body_side_keeps_its_members(tmp_path: Path) -> None:
    extra = "*SET_NODE_LIST\n        50\n       205       206\n*CONSTRAINED_NODAL_RIGID_BODY\n        90         0        50"
    deck = KeywordDeck.load(_deck(tmp_path, extra, deformable=True))
    out = add_joint(deck, "spherical", {"part": 1}, {"nodal_rigid_body": 90}, [40, 0, 0])
    assert out["side_b"]["previous_node_set"] == 50
    block = next(b for b in deck.iter_blocks() if b.name == "*CONSTRAINED_NODAL_RIGID_BODY")
    assert deck.get(block, "nsid", row=90).value == out["side_b"]["node_set"]
    report = check_joints(deck)
    assert not report["errors"] and report["joints"][0]["body_b"] == ("cnrb", 90)


def test_invalid_requests_are_refused(tmp_path: Path) -> None:
    deck = KeywordDeck.load(_deck(tmp_path))
    with pytest.raises(FieldError, match="perpendicular"):
        add_joint(deck, "universal", {"part": 1}, {"part": 2}, [0, 0, 0], axis=[1, 0, 0], second_axis=[1, 1, 0])
    with pytest.raises(FieldError, match="same rigid part"):
        add_joint(deck, "spherical", {"part": 2}, {"part": 2}, [0, 0, 0])
    with pytest.raises(FieldError, match="needs motor"):
        add_joint(deck, "rotational_motor", {"part": 1}, {"part": 2}, [0, 0, 0], axis=[0, 1, 0])
    with pytest.raises(FieldError, match="axis"):
        add_joint(deck, "revolute", {"part": 1}, {"part": 2}, [0, 0, 0])


JOINT = "*CONSTRAINED_JOINT_{kind}\n{nodes}\n"


def _joint_deck(tmp_path: Path, extra_nodes: str, joints: str, sets: str = "") -> KeywordDeck:
    text = (f"*NODE\n{extra_nodes}*SET_NODE_LIST\n        60\n       301       303       305\n"
            "*SET_NODE_LIST\n        61\n       302       304       306\n"
            "*CONSTRAINED_EXTRA_NODES_SET\n         1        60\n         2        61\n" + sets + joints)
    return KeywordDeck.load(_deck(tmp_path, text))


def _nodes(*rows: tuple) -> str:
    return "".join(f"{n:>8}" + "".join(f"{float(v):>16}" for v in p) + "\n" for n, p in rows)


def _row(*ids: int) -> str:
    return "".join(f"{i:>10}" for i in ids)


def test_check_finds_offsets_collinear_nodes_and_axis_errors(tmp_path: Path) -> None:
    pts = _nodes((301, (0, 0, 0)), (302, (0, 0.01, 0)), (303, (0, 40, 0)), (304, (0, 40, 0)),
                 (305, (40, 0, 0)), (306, (80, 0, 0)))
    joints = (JOINT.format(kind="REVOLUTE", nodes=_row(301, 302, 303, 304))
              + JOINT.format(kind="TRANSLATIONAL", nodes=_row(301, 302, 303, 304, 303, 304))
              + JOINT.format(kind="PLANAR", nodes=_row(301, 302, 305, 306)))
    report = check_joints(_joint_deck(tmp_path, pts, joints))
    kinds = [(f["kind"], f["keyword"]) for f in report["errors"]]
    assert ("joint_collinear_nodes", "*CONSTRAINED_JOINT_TRANSLATIONAL") in kinds
    assert ("joint_nodes_not_coincident", "*CONSTRAINED_JOINT_PLANAR") in kinds  # 3/4 are 40 apart
    # 1/2 are 0.01 apart: above the solver's 1e-4 x |N1N3| = 0.004, below the error level 0.4
    assert any(w["kind"] == "joint_nodes_not_coincident" for w in report["warnings"])


def test_check_blank_undefined_and_unattached_nodes(tmp_path: Path) -> None:
    pts = _nodes((301, (0, 0, 0)), (302, (0, 0, 0)), (303, (0, 40, 0)), (304, (0, 40, 0)), (309, (0, 0, 0)))
    joints = (JOINT.format(kind="REVOLUTE", nodes=_row(301, 302, 303))
              + JOINT.format(kind="SPHERICAL", nodes=_row(301, 999))
              + JOINT.format(kind="SPHERICAL", nodes=_row(309, 302)))
    report = check_joints(_joint_deck(tmp_path, pts, joints))
    assert {f["kind"] for f in report["errors"]} == {"joint_nodes_missing", "joint_node_not_on_rigid_body"}
    assert any("not defined" in u["reason"] for u in report["unverified"])


def test_several_joints_in_one_keyword_and_overconstraint(tmp_path: Path) -> None:
    pts = _nodes((301, (0, 0, 0)), (302, (0, 0, 0)), (303, (0, 40, 0)), (304, (0, 40, 0)),
                 (305, (40, 0, 0)), (306, (40, 0, 0)))
    joints = ("*CONSTRAINED_JOINT_REVOLUTE_ID\n         7    first\n" + _row(301, 302, 303, 304) + "\n"
              "         8   second\n" + _row(301, 302, 305, 306) + "\n")
    report = check_joints(_joint_deck(tmp_path, pts, joints))
    assert [j["jid"] for j in report["joints"]] == [7, 8]
    assert any(w["kind"] == "joint_overconstrained" for w in report["warnings"])


def test_joint_between_merged_rigid_bodies_is_a_warning(tmp_path: Path) -> None:
    pts = _nodes((301, (0, 0, 0)), (302, (0, 0, 0)), (303, (0, 40, 0)), (304, (0, 40, 0)), (305, (1, 0, 0)),
                 (306, (1, 0, 0)))
    merge = "*CONSTRAINED_RIGID_BODIES\n         1         2\n"
    report = check_joints(_joint_deck(tmp_path, pts, JOINT.format(kind="REVOLUTE", nodes=_row(301, 302, 303, 304)),
                                      merge))
    assert not report["errors"]
    assert [w["kind"] for w in report["warnings"]] == ["joint_same_body"] and "merged" in report["warnings"][0]["message"]


def test_add_joint_through_edit_deck_and_check_deck(tmp_path: Path) -> None:
    path = _deck(tmp_path)
    out = edit_deck(str(path), [{"op": "add_joint", "kind": "revolute", "a": {"part": 1}, "b": {"part": 2},
                                 "origin": [0, 0, 0], "axis": [0, 1, 0], "length": 40.0}],
                    output_dir=str(tmp_path / "out"))
    assert out["status"] == "succeeded" and out["summaries"][0]["constrained_dof"] == 5
    checked = check_deck(out["save"]["main"], include_mesh=False)
    assert checked["ok"] and checked["joints"]["checked"] == 1
    failed = edit_deck(str(path), [{"op": "add_joint", "kind": "revolute", "a": {"part": 1}, "b": {"part": 9},
                                    "origin": [0, 0, 0], "axis": [0, 1, 0]}], output_dir=str(tmp_path / "bad"))
    assert failed["status"] == "failed" and not failed.get("written")
