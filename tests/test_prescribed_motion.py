import copy
from collections import Counter

import pytest

from ls_prepost_mcp.boundary_cards import inspect_boundary_cards, verify_boundary_delta
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.entity_cards import (
    check_motion_conflicts,
    check_spc_conflicts,
    motion_rows,
    node_constraint_masks,
)
from ls_prepost_mcp.gui_motion import validate_time_curve
from ls_prepost_mcp.service import Service


def test_native_named_motion_groups_keep_multiple_targets_and_zero_death_default():
    rows = motion_rows(
        "*BOUNDARY_PRESCRIBED_MOTION_NODE_ID",
        [
            "*BOUNDARY_PRESCRIBED_MOTION_NODE_ID",
            f"{500:10d}Group",
            "1,3,2,11,1.5,0,0,0.25",
            f"{500:10d}Group",
            "2,3,2,11,1.5,0,1D28,0.25",
        ],
    )
    assert [r["target_id"] for r in rows] == [1, 2]
    assert all(r["motion_id"] == 500 and r["title"] == "Group" and r["death"] == 1e28 for r in rows)
    assert rows[0]["birth"] == 0.25 and rows[0]["dof"] == 3 and rows[0]["vad"] == 2


@pytest.mark.parametrize("row", ["1,4,2,11,1,5,0,0", "1,3,4,11,1,0,0,0"])
def test_advanced_motion_semantics_are_not_misread_as_global_motion(row):
    with pytest.raises(NotImplementedError):
        motion_rows("*BOUNDARY_PRESCRIBED_MOTION_NODE", ["*BOUNDARY_PRESCRIBED_MOTION_NODE", row])


def test_advanced_extra_card_is_explicitly_unresolved():
    with pytest.raises(NotImplementedError):
        motion_rows(
            "*BOUNDARY_PRESCRIBED_MOTION_NODE_ID",
            ["*BOUNDARY_PRESCRIBED_MOTION_NODE_ID", "500,Advanced", "1,9,2,11,1,0,1e28,0", "0,0,0,0,0"],
        )


def test_motion_spc_conflicts_are_symmetric_and_axis_specific():
    motion = motion_rows(
        "*BOUNDARY_PRESCRIBED_MOTION_SET", ["*BOUNDARY_PRESCRIBED_MOTION_SET", "10,3,0,11,1,0,1e28,0"]
    )[0]
    index = dict(
        sets={("node", 10): dict(member_ids=[1, 2])},
        motions=[motion],
        spcs=[],
        coordinates={0, 7},
        unresolved=[],
    )
    check_spc_conflicts(index, [1], 0, [1, 0, 0, 0, 0, 0], 600)
    with pytest.raises(ValueError, match="motion"):
        check_spc_conflicts(index, [1], 0, [0, 0, 1, 0, 0, 0], 600)
    with pytest.raises(ValueError, match="motion"):
        check_spc_conflicts(index, [1], 7, [1, 0, 0, 0, 0, 0], 600)
    check_motion_conflicts(index, [1], 1)
    with pytest.raises(ValueError, match="overlaps"):
        check_motion_conflicts(index, [2], 3)
    index["motions"] = []
    index["spcs"] = [
        dict(
            target_type="node",
            target_id=1,
            coordinate_system=0,
            dofs=[0, 0, 1, 0, 0, 0],
            constraint_id=600,
            title="SPC",
        )
    ]
    with pytest.raises(ValueError, match="SPC"):
        check_motion_conflicts(index, [1], 3)
    check_motion_conflicts(index, [2], 3)


def test_native_curve_motion_delta_rejects_wrong_target_or_changed_samples(tmp_path):
    before_path = tmp_path / "before.k"
    before_path.write_text("*KEYWORD\n*END\n")
    after_path = tmp_path / "after.k"
    after_path.write_text(
        "*KEYWORD\n*DEFINE_CURVE_TITLE\nRamp\n11,0,1,1,0,0,0,0\n0,0\n1,2\n"
        "*BOUNDARY_PRESCRIBED_MOTION_SET_ID\n500,Motion\n10,3,2,11,1,0,1e28,0\n*END\n"
    )
    before = inspect_boundary_cards(before_path, include_motions=True)
    after = inspect_boundary_cards(after_path, include_motions=True)
    expected = copy.deepcopy(after["motions"])
    curve = copy.deepcopy(after["curves"][11])
    assert verify_boundary_delta(before, after, curve=curve, motions=expected)["actual_motions"] == expected
    wrong = copy.deepcopy(after)
    wrong["motions"][0]["target_id"] = 12
    with pytest.raises(ValueError, match="motion"):
        verify_boundary_delta(before, wrong, curve=curve, motions=expected)
    wrong = copy.deepcopy(after)
    wrong["curves"][11]["points"][1][1] = 3
    with pytest.raises(ValueError, match="samples"):
        verify_boundary_delta(before, wrong, curve=curve, motions=expected)
    assert before["other"] == Counter()


@pytest.mark.parametrize(
    "override",
    [
        dict(axis="vector"),
        dict(motion="relative"),
        dict(title="Bad, heading"),
        dict(birth=2, death=1),
        dict(time_unit="mm"),
        dict(length_unit="s"),
        dict(append_to_group=1),
        dict(node_ids=[1], node_set_id=10),
        dict(points=[[0.0, 0.0], [0.0, 1.0]], curve_title="Ramp"),
    ],
)
def test_invalid_motion_contracts_reject_before_gui_access(tmp_path, override):
    args = dict(
        session_id="missing",
        motion_id=500,
        title="Motion",
        axis="z",
        motion="displacement",
        curve_id=11,
        time_unit="ms",
        length_unit="mm",
        node_ids=[1],
    )
    args.update(override)
    with pytest.raises(ValueError):
        Service(Settings(tmp_path)).create_gui_prescribed_motion(**args)


@pytest.mark.parametrize("dattyp,sfa", [(1, 1.0), (0, -1.0)])
def test_non_time_curve_reuse_rejects(dattyp, sfa):
    with pytest.raises(ValueError, match="time-compatible"):
        validate_time_curve(dict(dattyp=dattyp, sfa=sfa, points=[[0.0, 0.0], [1.0, 2.0]]))


def test_native_zero_abscissa_scale_default_is_one():
    validate_time_curve(dict(dattyp=0, sfa=0.0, points=[[0.0, 0.0], [1.0, 2.0]]))


def test_node_constraint_codes_are_ordinal_and_join_motion_spc_checks(tmp_path):
    path = tmp_path / "nodes.k"
    path.write_text(
        "*KEYWORD\n*NODE\n" + f"{2:8d}{0.0:16g}{100.0:16g}{0.0:16g}{6:8d}{3:8d}\n" + "3,0,0,0,4,0\n*END\n"
    )
    masks = node_constraint_masks(path)
    assert masks[2] == (1 | 4 | 32)  # TC6=X/Z, RC3=RZ, not binary codes6 and3.
    assert masks[3] == 3  # TC4=X/Y.
    index = dict(spcs=[], motions=[], sets={}, coordinates={0}, unresolved=[], nodal_dofs=masks)
    check_motion_conflicts(index, [2], 2)
    with pytest.raises(ValueError, match="TC/RC"):
        check_motion_conflicts(index, [2], 1)
    with pytest.raises(ValueError, match="TC/RC"):
        check_motion_conflicts(index, [2], 7)
    with pytest.raises(ValueError, match="TC/RC"):
        check_spc_conflicts(index, [3], 0, [0, 1, 0, 0, 0, 0], 10)
