"""P08 mesh selector scope, legacy selection modes and existing G03 refusals."""
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import Selector
from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.service import Service

pytest.importorskip("ansys.dyna.core")


def selector(entity):
    value = dict(entity_type=entity, predicate=dict(kind="parts", ids=[2]))
    assert Selector.model_validate(value).predicate.kind == "parts"
    return value


def fixture(tmp_path, duplicate):
    rows = ["*KEYWORD", "*PART", "sentinel", "         1         1         1",
            "*PART", "target", "         2         1         1", "*SECTION_SHELL",
            "         1         2", "       0.1       0.1       0.1       0.1",
            "*MAT_ELASTIC", "         1       1.0       1.0      0.25", "*NODE"]
    coordinates, connections = {}, {}
    for part, base, first, offset in ((1, 0, 11, 100), (2, 200, 21, 0)):
        if duplicate:
            points = [(0, 0), (1, 0), (1, 1), (0, 1), (1, 0), (2, 0), (2, 1), (1, 1)]
            rings = [(1, 2, 3, 4), (5, 6, 7, 8)]
        else:
            points = [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)]
            rings = [(1, 2, 5, 4), (3, 2, 5, 6)]  # second shell intentionally reversed
        for index, (x, y) in enumerate(points, 1):
            coordinates[base + index] = (float(offset + x), float(y), 0.)
        for index, ring in enumerate(rings):
            connections[first + index] = (part, *(base + n for n in ring))
    rows += [f"{nid:8d}" + "".join(f"{v:16g}" for v in xyz) for nid, xyz in coordinates.items()]
    rows += ["*ELEMENT_SHELL"]
    rows += ["".join(f"{v:8d}" for v in (eid, *row)) for eid, row in connections.items()]
    for sid, members in ((51, [5, 8] if duplicate else [5]), (52, [205, 208] if duplicate else [205])):
        rows += ["*SET_NODE_LIST", f"{sid:10d}", "".join(f"{nid:10d}" for nid in members)]
    rows += ["*BOUNDARY_SPC_NODE"]
    rows += ["".join(f"{v:10d}" for v in (nid, 0, 1, 0, 0, 0, 0, 0)) for nid in (5, 205)]
    rows += ["*END"]
    source = tmp_path / "input.k"
    source.write_text("\n".join(rows) + "\n", encoding="ascii")
    return source, Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))


def semantic(path):
    deck = KeywordDeck.load(path)
    coordinates = {key: tuple(deck.get(block, name, row=key).value for name in ("x", "y", "z"))
                   for block in deck.blocks("*NODE") for key in deck.layout(block).rows}
    shells = {key: tuple(deck.get(block, name, row=key).value for name in ("pid", "n1", "n2", "n3", "n4"))
              for block in deck.blocks("*ELEMENT_SHELL") for key in deck.layout(block).rows}
    sets = {deck.get(block, "sid").value: deck.members(block) for block in deck.blocks("*SET_NODE_LIST")}
    spc = {key: tuple(deck.get(block, name, row=key).value for name in ("cid", "dofx", "dofy", "dofz"))
           for block in deck.blocks("*BOUNDARY_SPC_NODE") for key in deck.layout(block).rows}
    report = deck.references(True)
    assert report.dangling_count == report.unverified_count == 0
    return dict(nodes=coordinates, shells=shells, sets=sets, spc=spc)


def sentinel(state):
    return dict(nodes={n: p for n, p in state["nodes"].items() if n < 200},
                shells={e: row for e, row in state["shells"].items() if row[0] == 1},
                node_set=state["sets"][51], spc={n: row for n, row in state["spc"].items() if n < 200})


def test_merge_selector_preserves_unselected_values_and_rewrites_selected_references(tmp_path):
    source, service = fixture(tmp_path, duplicate=True)
    raw, before = source.read_bytes(), semantic(source)
    result = service.mesh_ops(str(source), [dict(op="merge_duplicate_nodes", selector=selector("node"), tolerance=1e-9)])
    assert result["status"] == "succeeded", result
    after = semantic(result["data"]["main"])
    assert sentinel(after) == sentinel(before), "sentinel nodes/connections/references changed"
    assert after["nodes"] == {n: xyz for n, xyz in before["nodes"].items() if n not in (205, 208)}
    assert after["shells"][21] == (2, 201, 202, 203, 204)
    assert after["shells"][22] == (2, 202, 206, 207, 203)
    assert after["sets"][52] == [202, 203] and 202 in after["spc"] and 205 not in after["spc"]
    assert result["data"]["summaries"][0]["merged"] == 2
    assert source.read_bytes() == raw


def test_normals_selector_preserves_unselected_values_and_orients_selected_patch(tmp_path):
    source, service = fixture(tmp_path, duplicate=False)
    raw, before = source.read_bytes(), semantic(source)
    result = service.mesh_ops(str(source), [dict(op="unify_shell_normals", selector=selector("shell"), direction=[0, 0, 1])])
    assert result["status"] == "succeeded", result
    after = semantic(result["data"]["main"])
    assert sentinel(after) == sentinel(before), "sentinel shell connections changed"
    assert after["nodes"] == before["nodes"] and after["sets"] == before["sets"] and after["spc"] == before["spc"]
    assert after["shells"][21] == (2, 201, 202, 205, 204)
    assert after["shells"][22] == (2, 202, 203, 206, 205)
    assert result["data"]["summaries"][0]["reversed"] == 1
    assert source.read_bytes() == raw


@pytest.mark.parametrize("operation", ["merge_duplicate_nodes", "unify_shell_normals"])
@pytest.mark.parametrize("mode", ["ids", "select", "global"])
def test_legacy_selection_modes_and_omitted_global_are_preserved(tmp_path, operation, mode):
    duplicate = operation == "merge_duplicate_nodes"
    source, service = fixture(tmp_path, duplicate)
    raw, before = source.read_bytes(), semantic(source)
    edit = dict(op=operation, **({"tolerance": 1e-9} if duplicate else {"direction": [0, 0, 1]}))
    if mode == "ids":
        edit["ids"] = list(range(201, 209)) if duplicate else [21, 22]
    elif mode == "select":
        edit["select"] = {"parts": [2]}
    result = service.mesh_ops(str(source), [edit])
    assert result["status"] == "succeeded", result
    after = semantic(result["data"]["main"])
    summary = result["data"]["summaries"][0]
    if mode != "global":
        assert sentinel(after) == sentinel(before)
    if duplicate:
        removed = {5, 8, 205, 208} if mode == "global" else {205, 208}
        assert after["nodes"] == {n: xyz for n, xyz in before["nodes"].items() if n not in removed}
        assert after["shells"][22] == (2, 202, 206, 207, 203)
        assert after["sets"][52] == [202, 203]
        assert summary["merged"] == (4 if mode == "global" else 2)
        if mode == "global":
            assert after["shells"][12] == (1, 2, 6, 7, 3) and after["sets"][51] == [2, 3]
    else:
        assert after["nodes"] == before["nodes"] and after["sets"] == before["sets"] and after["spc"] == before["spc"]
        assert after["shells"][22] == (2, 202, 203, 206, 205)
        assert summary["reversed"] == (2 if mode == "global" else 1)
        if mode == "global":
            assert after["shells"][12] == (1, 2, 3, 6, 5)
    assert source.read_bytes() == raw


@pytest.mark.parametrize("operation,entity", [("merge_duplicate_nodes", "node"), ("unify_shell_normals", "shell")])
def test_explicit_empty_selector_never_becomes_global(tmp_path, operation, entity):
    duplicate = operation == "merge_duplicate_nodes"
    source, service = fixture(tmp_path, duplicate)
    before, raw = semantic(source), source.read_bytes()
    empty = dict(entity_type=entity, predicate=dict(kind="none"))
    assert Selector.model_validate(empty).predicate.kind == "none"
    edit = dict(op=operation, selector=empty, **({"tolerance": 1e-9} if duplicate else {"direction": [0, 0, 1]}))
    result = service.mesh_ops(str(source), [edit])
    assert result["status"] == "succeeded", result
    assert semantic(result["data"]["main"]) == before
    assert source.read_bytes() == raw


@pytest.mark.parametrize("operation,entity", [("merge_duplicate_nodes", "node"), ("unify_shell_normals", "shell")])
@pytest.mark.parametrize("bad", [False, None, "unknown", {"entity_type": "node", "predicate": {"kind": "unknown"}}])
def test_invalid_selector_uses_shared_g03_validation_without_editing(tmp_path, operation, entity, bad):
    duplicate = operation == "merge_duplicate_nodes"
    source, service = fixture(tmp_path, duplicate)
    raw = source.read_bytes()
    edit = dict(op=operation, selector=bad, **({"tolerance": 1e-9} if duplicate else {"direction": [0, 0, 1]}))
    result = service.mesh_ops(str(source), [edit])
    assert result["status"] == "failed" and not result["artifacts"]
    assert source.read_bytes() == raw


@pytest.mark.parametrize("operation,wrong_entity", [("merge_duplicate_nodes", "shell"), ("unify_shell_normals", "node")])
def test_selector_entity_mismatch_refuses_in_shared_ids(tmp_path, operation, wrong_entity):
    duplicate = operation == "merge_duplicate_nodes"
    source, service = fixture(tmp_path, duplicate)
    raw = source.read_bytes()
    edit = dict(op=operation, selector=selector(wrong_entity), **({"tolerance": 1e-9} if duplicate else {"direction": [0, 0, 1]}))
    result = service.mesh_ops(str(source), [edit])
    assert result["status"] == "failed" and not result["artifacts"]
    assert source.read_bytes() == raw
