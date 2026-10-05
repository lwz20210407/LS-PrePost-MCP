import copy

import pytest

from ls_prepost_mcp.boundary_cards import inspect_boundary_cards, verify_boundary_delta
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.nodal_load_cards import distribution_scale, load_overlap, nodal_load_rows
from ls_prepost_mcp.service import Service


def test_equal_total_and_per_node_distributions_have_different_force_sums():
    assert distribution_scale(1.0, 3, "total_equal") * 90.0 == 30.0
    assert distribution_scale(1.0, 3, "per_node") * 90.0 == 90.0
    with pytest.raises(ValueError, match="underflows"):
        distribution_scale(5e-324, 100, "total_equal")
    with pytest.raises(ValueError, match="overflows"):
        distribution_scale(1e308, 100, "per_node")


def test_nodal_load_rows_keep_global_local_and_follower_semantics():
    rows = nodal_load_rows(
        "*LOAD_NODE_POINT", ["*LOAD_NODE_POINT", "7,3,10,0.25,0,0,0,0", "8,8,10,-2,5,11,12,13"]
    )
    assert rows[0]["target_id"] == 7 and rows[0]["scale"] == 0.25
    assert rows[1]["coordinate_system"] == 5 and rows[1]["m3"] == 13
    with pytest.raises(NotImplementedError):
        nodal_load_rows("*LOAD_NODE_SET_ID", [])


def test_overlap_resolves_set_members_and_does_not_guess_local_axes():
    rows = nodal_load_rows("*LOAD_NODE_SET", ["*LOAD_NODE_SET", "55,3,10,1,0,0,0,0"])
    entities = dict(sets={("node", 55): dict(member_ids=[1, 2])}, unresolved=[])
    assert load_overlap(rows, entities, [2, 3], 3)[0]["overlapping_node_count"] == 1
    assert not load_overlap(rows, entities, [2], 1)
    rows[0]["coordinate_system"] = 5
    with pytest.raises(ValueError, match="local/follower"):
        load_overlap(rows, entities, [2], 1)


def test_duplicate_load_superposition_preserved_by_multiset_readback(tmp_path):
    before = tmp_path / "before.k"
    after = tmp_path / "after.k"
    row = "1,3,10,0.3333333,0,0,0,0\n"
    before.write_text("*KEYWORD\n*LOAD_NODE_POINT\n" + row + "*END\n")
    after.write_text("*KEYWORD\n*LOAD_NODE_POINT\n" + row + row + "*END\n")
    a = inspect_boundary_cards(before, include_nodal_loads=True)
    b = inspect_boundary_cards(after, include_nodal_loads=True)
    expected = dict(a["nodal_loads"][0], scale=1 / 3)
    assert len(verify_boundary_delta(a, b, nodal_loads=[expected])["actual_nodal_loads"]) == 1
    wrong = copy.deepcopy(b)
    wrong["nodal_loads"][1]["target_id"] = 99
    with pytest.raises(ValueError, match="nodal-load"):
        verify_boundary_delta(a, wrong, nodal_loads=[expected])
    with pytest.raises(ValueError, match="Unexpected"):
        verify_boundary_delta(a, b)


def test_large_nodal_load_readback_is_order_independent_and_preserves_multiplicity(tmp_path):
    path = tmp_path / "empty.k"
    path.write_text("*KEYWORD\n*END\n")
    before = inspect_boundary_cards(path, include_nodal_loads=True)
    record = nodal_load_rows("*LOAD_NODE_POINT", ["*LOAD_NODE_POINT", "1,3,10,1,0,0,0,0"])[0]
    expected = [dict(record, target_id=i) for i in range(1, 20001)]
    after = copy.deepcopy(before)
    after["nodal_loads"] = list(reversed(expected))
    assert verify_boundary_delta(before, after, nodal_loads=expected)["actual_nodal_loads"] == expected
    after["nodal_loads"][-1] = dict(record, target_id=2)
    with pytest.raises(ValueError, match="nodal-load"):
        verify_boundary_delta(before, after, nodal_loads=expected)


@pytest.mark.parametrize(
    "changes",
    [
        dict(axis="vector"),
        dict(distribution="auto"),
        dict(value_unit="MPa"),
        dict(axis="rx", value_unit="N"),
        dict(time_unit="N"),
        dict(scale=0.0),
        dict(scale=float("nan")),
        dict(allow_superposition=1),
        dict(node_set_id=55),
        dict(points=[[0.0, 0.0], [0.0, 1.0]], curve_title="Curve"),
    ],
)
def test_bad_load_contracts_reject_before_session_access(tmp_path, changes):
    args = dict(
        session_id="missing",
        axis="z",
        curve_id=10,
        time_unit="s",
        value_unit="N",
        distribution="per_node",
        node_ids=[1],
    )
    args.update(changes)
    with pytest.raises(ValueError):
        Service(Settings(tmp_path)).create_gui_nodal_load(**args)
