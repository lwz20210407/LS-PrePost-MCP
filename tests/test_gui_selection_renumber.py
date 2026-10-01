import copy

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.gui_renumber import renumber_map, verify_renumber
from ls_prepost_mcp.gui_selection import available_ids, in_parts, verify_selection
from ls_prepost_mcp.service import Service


def mesh():
    return dict(
        nodes=[[10, 0, 0, 0], [20, 1, 0, 0], [30, 0, 1, 0], [40, 2, 2, 0]],
        elements=[dict(type="shell", id=50, nodes=[10, 20, 30, 30])],
        part_ids=[7],
        part_elements={"7": [50]},
        selection_ids=[],
    )


def test_part_selection_uses_connectivity_and_rejects_ambiguous_domains():
    state = mesh()
    assert in_parts(state, "node", [7]) == {10, 20, 30}
    assert in_parts(state, "shell", [7]) == {50}
    state["elements"].append(dict(type="beam", id=50, nodes=[10, 40]))
    with pytest.raises(ValueError, match="globally unique"):
        available_ids(state, "element")


def test_selection_verifies_exact_ids_and_unchanged_mesh():
    a, b = mesh(), mesh()
    b["selection_ids"] = [10, 20]
    assert verify_selection(a, b, {10, 20}, "node")["selected_count"] == 2
    with pytest.raises(ValueError, match="selected IDs"):
        verify_selection(a, b, {10}, "node")
    b["nodes"][0][1] = 1
    with pytest.raises(ValueError, match="coordinates"):
        verify_selection(a, b, {10, 20}, "node")


def test_selection_predicates_and_invalid_inputs(tmp_path, monkeypatch):
    s = Service(Settings(tmp_path))
    monkeypatch.setattr(s, "_select_gui", lambda sid, action, args, kind, choose, **kwargs: choose(mesh()))
    assert s.select_gui_entities("s", "node", [10], invert=True) == {20, 30, 40}
    assert s.select_gui_entities("s", "node", part_ids=[7]) == {10, 20, 30}
    assert s.select_gui_entities("s", "node", []) == set()
    assert s.select_gui_nodes_by_box("s", [0, 0, 0, 1, 1, 0], "mm") == {10, 20, 30}
    assert s.select_gui_nodes_by_sphere("s", [0, 0, 0], 1, "mm") == {10, 20, 30}
    assert s.select_gui_nodes_by_sphere("s", [0, 0, 0], 1, "mm", inside=False) == {40}
    for ids in ("", {}, 0):
        with pytest.raises(ValueError, match="list"):
            s.select_gui_entities("s", "node", ids)
    with pytest.raises(ValueError, match="Unknown"):
        s.select_gui_entities("s", "node", [99])


def test_native_mapping_selects_complete_block_not_repeated_identity_section(tmp_path):
    log = tmp_path / "map.txt"
    log.write_text("*NODE\n10 100\n20 101\n*NODE\n1 1\n")
    assert renumber_map(log, "*NODE", [10, 20], [100, 101]) == {10: 100, 20: 101}
    log.write_text(log.read_text() + "*NODE\n10 101\n20 100\n")
    with pytest.raises(ValueError, match="unique complete"):
        renumber_map(log, "*NODE", [10, 20], [100, 101])


@pytest.mark.parametrize(
    "kind,header,start", [("node", "*NODE", 100), ("shell", "*ELEMENT_SHELL", 200), ("part", "*PART", 300)]
)
def test_renumber_checks_mapping_coordinates_connectivity_and_parts(tmp_path, kind, header, start):
    before = mesh()
    after = copy.deepcopy(before)
    old_ids = [10, 20, 30, 40] if kind == "node" else [50] if kind == "shell" else [7]
    mapping = {old: start + i for i, old in enumerate(old_ids)}
    if kind == "node":
        for row in after["nodes"]:
            row[0] = mapping[row[0]]
        after["elements"][0]["nodes"] = [mapping[n] for n in after["elements"][0]["nodes"]]
    elif kind == "shell":
        after["elements"][0]["id"] = start
        after["part_elements"] = {"7": [start]}
    else:
        after["part_ids"] = [start]
        after["part_elements"] = {str(start): [50]}
    log = tmp_path / "map.txt"
    log.write_text(header + "\n" + "".join(f"{a} {b}\n" for a, b in mapping.items()))
    assert verify_renumber(before, after, kind, start, log)["count"] == len(old_ids)
    after["nodes"][0][1] = 42
    with pytest.raises(ValueError, match="coordinates"):
        verify_renumber(before, after, kind, start, log)


def test_native_node_set_zero_padding_is_not_a_node_reference(tmp_path):
    pytest.importorskip("ansys.dyna.core")
    from ls_prepost_mcp.model_deck import validate_references

    path = tmp_path / "padded.k"
    path.write_text("*KEYWORD\n*NODE\n10,0,0,0\n20,1,0,0\n*SET_NODE_LIST\n7\n10,20,0,0,0,0,0,0\n*END\n")
    assert validate_references(path)["valid_within_scope"]
    path.write_text(path.read_text().replace("10,20,0", "10,99,0"))
    assert validate_references(path)["errors"][0]["ids"] == [99]


def test_plane_selection_normalization_tolerance_and_sides(tmp_path, monkeypatch):
    s = Service(Settings(tmp_path))
    monkeypatch.setattr(s, "_select_gui", lambda sid, action, args, kind, choose, **kwargs: choose(mesh()))
    assert s.select_gui_nodes_by_plane("s", [0, 0, 0], [1e300, 0, 0], "mm") == {10, 30}
    assert s.select_gui_nodes_by_plane("s", [0, 0, 0], [1, 0, 0], "mm", "positive") == {20, 40}
    assert s.select_gui_nodes_by_plane("s", [0, 0, 0], [-1, 0, 0], "mm", "negative") == {20, 40}
    with pytest.raises(ValueError, match="Nonzero"):
        s.select_gui_nodes_by_plane("s", [0, 0, 0], [0, 0, 0], "mm")


def test_selection_boolean_operations_validate_even_cancelled_unknown_ids(tmp_path, monkeypatch):
    s = Service(Settings(tmp_path))
    monkeypatch.setattr(s, "_select_gui", lambda sid, action, args, kind, choose, **kwargs: choose(mesh()))
    for op, expected in [
        ("union", {10, 20, 30}),
        ("intersection", {20}),
        ("difference", {10}),
        ("xor", {10, 30}),
    ]:
        assert s.combine_gui_selections("s", "node", [10, 20], [20, 30], op) == expected
    with pytest.raises(ValueError, match="Unknown operand"):
        s.combine_gui_selections("s", "node", [99], [99], "xor")


def test_buffer_slots_and_model_signature():
    from ls_prepost_mcp.gui_selection import buffer_slot, mesh_signature

    assert buffer_slot(1) == 0 and buffer_slot(10) == 9
    for invalid in (0, 11, True, 1.0):
        with pytest.raises(ValueError):
            buffer_slot(invalid)
    before, after = mesh(), mesh()
    after["nodes"].reverse()
    after["selection_ids"] = [10]
    assert mesh_signature(before) == mesh_signature(after)
    after["nodes"][0][1] += 1
    assert mesh_signature(before) != mesh_signature(after)


def test_stale_buffer_rejected_before_native_input(tmp_path, monkeypatch):
    from contextlib import nullcontext

    from ls_prepost_mcp.gui_selection import mesh_signature

    s = Service(Settings(tmp_path))

    class Manager:
        def lock(self, sid):
            return nullcontext()

        def read(self, sid):
            return {
                "selection_buffers": {
                    "1": dict(entity_type="node", entity_ids=[10], model_signature=mesh_signature(mesh()))
                }
            }

    monkeypatch.setattr(s, "_session_manager", Manager)

    def edit(sid, action, params, commands, verify, precheck, **kwargs):
        state = mesh()
        state["nodes"][0][1] = 5
        precheck(state)
        pytest.fail("A stale buffer must not reach native dispatch")

    monkeypatch.setattr(s, "_gui_mesh_edit", edit)
    with pytest.raises(ValueError, match="stale"):
        s.load_gui_selection_buffer("s", 1)


def test_result_selection_requires_stable_native_state():
    a, b = mesh(), mesh()
    a["current_state"] = 1
    b["current_state"] = 2
    with pytest.raises(ValueError, match="state changed"):
        verify_selection(a, b, [], "node")


def test_part_selection_uses_native_bulk_command_with_exact_postcondition(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))

    def edit(sid, action, params, commands, verify, precheck, **kwargs):
        before = mesh()
        precheck(before)
        generated = commands(before, tmp_path)
        assert generated == ["pall", "genselect clear", "genselect target node", "genselect node add part 7"]
        after = copy.deepcopy(before)
        after["selection_ids"] = [10, 20, 30]
        result = verify(before, after)
        assert result["command_strategy"] == "native_part"
        after["selection_ids"].append(40)
        with pytest.raises(ValueError, match="selected IDs"):
            verify(before, after)
        return result

    monkeypatch.setattr(service, "_gui_mesh_edit", edit)
    assert service.select_gui_entities("s", "node", part_ids=[7])["selected_count"] == 3
