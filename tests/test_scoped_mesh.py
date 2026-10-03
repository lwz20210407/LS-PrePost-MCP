import copy
from types import SimpleNamespace

import numpy as np
import pytest

from ls_prepost_mcp.embedded import scoped_mesh_state
from ls_prepost_mcp.gui_mesh import verify_mesh_digest, verify_reverse, verify_transform
from ls_prepost_mcp.gui_node_edit import verify_coordinates
from ls_prepost_mcp.gui_selection import verify_selection


def native_model():
    return dict(nodes={11: [0., 0., 0.], 22: [1., 0., 0.], 33: [0., 1., 0.]},
                elements={1: {101: [11, 22, 33, 33]}, 2: {}, 3: {}},
                parts={7: [101]}, selected=[22], visible={7: True})


def snapshot(model, output_directory=None, **parameters):
    def get(key, **kw):
        if key == "node_ids":
            return list(model["nodes"])
        if key in ("node_x", "node_y", "node_z"):
            index = {"node_x": 0, "node_y": 1, "node_z": 2}[key]
            return [row[index] for row in model["nodes"].values()]
        if key == "element_ids":
            return list(model["elements"][kw["type"]])
        if key == "element_connectivity":
            return model["elements"][kw["type"]][kw["id"]]
        if key == "num_elements":
            return sum(len(es) for es in model["elements"].values())
        if key == "validpart_ids":
            return list(model["parts"])
        if key == "elemofpart_ids":
            return model["parts"][kw["id"]]
        if key == "num_selection":
            return len(model["selected"])
        if key == "selection_ids":
            return model["selected"]
        raise AssertionError(key)

    dc = SimpleNamespace(get_data=get, Type=SimpleNamespace(NODE=0, SHELL=1, SOLID=2, BEAM=3))
    lp = SimpleNamespace(check_if_part_is_active_u=lambda pid: model["visible"][pid],
                         check_if_element_is_active_u=lambda uid, kind: list(model["elements"][kind]).index(uid) % 2 == 0)
    result = scoped_mesh_state(dc, lp, parameters, output_directory)
    result.update(counts=dict(nodes=len(model["nodes"]), elements=get("num_elements")), current_state=1)
    return result


def test_visibility_bridge_streams_multiple_binary_chunks_without_json_rows(tmp_path):
    from ls_prepost_mcp.gui_visibility import flags
    model = native_model()
    model["elements"][1] = {i: [11, 22, 33, 33] for i in range(101, 5102)}
    model["parts"][7] = list(model["elements"][1])
    result = snapshot(model, output_directory=tmp_path, visibility_readback=True)
    assert "visibility_rows" not in result
    assert result["visibility_binary"]["byte_count"] == 50010
    visible = flags(result, tmp_path)
    assert len(visible) == 5001
    assert visible[("shell", 101)] is True and visible[("shell", 102)] is False
    assert visible[("shell", 5101)] is True


def test_selected_coordinates_change_but_every_other_entity_is_protected():
    model = native_model()
    before = snapshot(model, node_ids=[22])
    assert before["nodes"] == [[22, 1., 0., 0.]] and not before["elements"]
    model["nodes"][22][0] = 3.
    after = snapshot(model, node_ids=[22])
    assert verify_coordinates(before, after, {22: np.array([3, 0, 0])}, 1e-6)["affected_element_count"] == 1
    verify_transform(before, after, {22}, lambda xyz: xyz + [2, 0, 0])
    with pytest.raises(ValueError, match="coordinates"):
        verify_mesh_digest(before, after)
    model["nodes"][33][2] = 1e-12
    with pytest.raises(ValueError, match="unselected"):
        verify_coordinates(before, snapshot(model, node_ids=[22]), {22: np.array([3, 0, 0])}, 1e-6)


@pytest.mark.parametrize("change", ["connectivity", "part_membership", "node_ids", "scope"])
def test_unrequested_structure_changes_cannot_hide_behind_same_counts(change):
    model = native_model()
    before = snapshot(model, node_ids=[22])
    arguments = dict(node_ids=[22])
    if change == "connectivity":
        model["elements"][1][101] = [11, 33, 22, 22]
    elif change == "part_membership":
        model["parts"][7] = []
    elif change == "node_ids":
        model["nodes"][44] = model["nodes"].pop(33)
    else:
        arguments["node_ids"] = [33]
    with pytest.raises(ValueError):
        verify_mesh_digest(before, snapshot(model, **arguments), True)


def test_explicit_selection_is_verified_without_materializing_mesh():
    model = native_model()
    before = snapshot(model, entity_type="node", entity_ids=[22])
    assert not before["nodes"] and not before["elements"]
    verify_selection(before, copy.deepcopy(before), {22}, "node")
    model["selected"] = [11]
    with pytest.raises(ValueError, match="selected IDs"):
        verify_selection(before, snapshot(model, entity_type="node", entity_ids=[22]), {22}, "node")
    model["elements"][2][101] = [11, 22, 33, 33]
    with pytest.raises(ValueError, match="ambiguous"):
        snapshot(model, entity_type="shell", entity_ids=[101])


def test_large_population_does_not_leak_unrequested_rows():
    model = native_model()
    model["nodes"] = {i: [float(i), 0., 0.] for i in range(1, 100002)}
    model["elements"] = {1: {}, 2: {}, 3: {i: [i, i + 1] for i in range(1, 100001)}}
    model["parts"][7] = list(range(1, 100001))
    result = snapshot(model, node_ids=[99999])
    assert result["nodes"] == [[99999, 99999., 0., 0.]]
    assert result["elements"] == [] and result["affected_element_count"] == 2
    assert all(len(value) == 64 for value in result["mesh_digest"].values())


@pytest.mark.parametrize("query,expected", [
    (dict(kind="box", lower=[0., 0., 0.], upper=[1., 0., 0.], inside=True), [11, 22]),
    (dict(kind="box", lower=[0., 0., 0.], upper=[1., 0., 0.], inside=False), [33]),
    (dict(kind="sphere", center=[0., 0., 0.], radius=1., inside=True), [11, 22, 33]),
    (dict(kind="sphere", center=[0., 0., 0.], radius=.5, inside=False), [22, 33]),
    (dict(kind="plane", point=[0., 0., 0.], direction=[1., 0., 0.], side="band", tolerance=0.), [11, 33]),
    (dict(kind="plane", point=[0., 0., 0.], direction=[1., 0., 0.], side="positive", tolerance=0.), [22]),
    (dict(kind="plane", point=[1., 0., 0.], direction=[1., 0., 0.], side="negative", tolerance=0.), [11, 33]),
])
def test_streamed_spatial_predicates_include_boundaries_and_outside(query, expected):
    result = snapshot(native_model(), selection_query=query)
    assert result["registry_matches"] == expected and result["query_selected_ids"] == expected
    assert result["nodes"] == [] and result["elements"] == []
    assert result["mesh_digest"] == snapshot(native_model())["mesh_digest"]


def test_large_spatial_query_bounds_selection_not_model_population():
    model = native_model()
    model["nodes"] = {i: [float(i), 0., 0.] for i in range(1, 100002)}
    query = dict(kind="box", lower=[1., 0., 0.], upper=[3., 0., 0.], inside=True)
    result = snapshot(model, selection_query=query)
    assert result["query_selected_ids"] == [1, 2, 3]
    query["upper"][0] = 100000.
    with pytest.raises(ValueError, match="selected nodes per operation"):
        snapshot(model, selection_query=query)


def shared_parts():
    model = native_model()
    model["nodes"].update({44: [1., 1., 0.], 55: [9., 9., 9.]})
    model["elements"][1][102] = [22, 44, 33, 33]
    model["parts"][8] = [102]
    model["visible"][8] = False
    return model


@pytest.mark.parametrize("arguments,expected,strategy", [
    ({}, [11, 22, 33, 44, 55], "whole"),
    (dict(scope="active_parts"), [11, 22, 33], "parts"),
    (dict(part_ids=[8]), [22, 33, 44], "parts"),
    (dict(part_ids=[8], scope="active_parts"), [22, 33], None),
    (dict(part_ids=[8], scope="active_parts", invert=True), [11], None),
    (dict(part_ids=[7], invert=True), [44, 55], None),
    (dict(entity_ids=[44], scope="active_parts"), [], None),
    (dict(entity_ids=[], invert=True), [11, 22, 33, 44, 55], "whole"),
    (dict(part_ids=[]), [], "parts"),
])
def test_part_scope_shared_nodes_orphans_and_scoped_inversion(arguments, expected, strategy):
    query = dict(part_ids=None, entity_ids=None, scope="all", invert=False)
    query.update(arguments)
    result = snapshot(shared_parts(), entity_type="node", registry_query=query)
    assert result["query_selected_ids"] == expected
    plan = result["native_selection_plan"]
    assert (plan["strategy"] if plan else None) == strategy
    assert not result["nodes"] and not result["elements"]


def test_typed_part_query_cannot_bulk_select_other_domains():
    model = shared_parts()
    model["elements"][2][201] = [11, 22, 33, 44, 44, 44, 44, 44]
    model["parts"][9] = [201]
    model["visible"][9] = True
    query = dict(part_ids=[7, 9], entity_ids=None, scope="all", invert=False)
    result = snapshot(model, entity_type="solid", registry_query=query)
    assert result["query_selected_ids"] == [201]
    assert result["native_selection_plan"] is None
    query["part_ids"] = [9]
    result = snapshot(model, entity_type="solid", registry_query=query)
    assert result["native_selection_plan"] == dict(strategy="parts", target="element", part_ids=[9])


def test_large_bulk_part_selection_has_no_20000_global_or_selected_bound():
    model = native_model()
    model["nodes"] = {i: [float(i), 0., 0.] for i in range(1, 100003)}
    model["elements"] = {1: {}, 2: {}, 3: {i: [i, i + 1] for i in range(1, 100001)}}
    model["parts"][7] = list(range(1, 100001))
    model["selected"] = list(range(1, 100002))
    query = dict(part_ids=[7], entity_ids=None, scope="all", invert=False)
    result = snapshot(model, entity_type="node", registry_query=query)
    assert result["query_selected_ids"] == model["selected"]
    assert result["selection_ids"] == model["selected"]
    assert result["native_selection_plan"] == dict(strategy="parts", target="node", part_ids=[7])
    assert result["selection_limit"] == 1000000


def test_streamed_normal_scope_allows_cyclic_reversal_and_preserves_other_shells():
    model = shared_parts()
    before = snapshot(model, normal_scope=dict(shell_ids=[101]))
    model["elements"][1][101] = [33, 22, 11, 11]
    after = snapshot(model, normal_scope=dict(shell_ids=[101]))
    assert verify_reverse(before, after, [101])["reversed_shells"] == 1
    model["elements"][1][102] = [22, 33, 44, 44]
    with pytest.raises(ValueError, match="unselected_connectivity"):
        verify_reverse(before, snapshot(model, normal_scope=dict(shell_ids=[101])), [101])


def test_streamed_normal_noop_coordinate_and_scope_errors_are_rejected():
    model = native_model()
    before = snapshot(model, normal_scope=dict(shell_ids=None))
    with pytest.raises(ValueError, match="not reversed"):
        verify_reverse(before, before)
    model["elements"][1][101] = [11, 33, 22, 22]
    model["nodes"][33][2] = .001
    with pytest.raises(ValueError, match="coordinates"):
        verify_reverse(before, snapshot(model, normal_scope=dict(shell_ids=None)))
    with pytest.raises(ValueError, match="unknown"):
        snapshot(model, normal_scope=dict(shell_ids=[999]))
    model["elements"][1][101] = [11, 11, 33, 33]
    with pytest.raises(ValueError, match="noncollapsed"):
        snapshot(model, normal_scope=dict(shell_ids=None))
