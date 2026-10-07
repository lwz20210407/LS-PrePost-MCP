"""Tests for G04: 实体识别 Identify (query_entities).

Acceptance Criteria:
1. 节点 / 单元 / Part 的 ID、坐标、连接、所属 Part / 材料、指定状态的结果值
2. 结果值与 Q03 同一量一致
3. 用户故事：节点 1001 的坐标和它在第 30 个状态的位移是多少？属于哪个 Part？
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service

pytest.importorskip("lasso")
from lasso.dyna import ArrayType, D3plot  # noqa: E402


@pytest.fixture()
def identify_d3plot(tmp_path: Path) -> Path:
    """Fixture containing solid and shell elements, multiple parts, 30 states, and node 1001."""
    plot = D3plot()
    a = plot.arrays

    n_states = 30
    times = np.linspace(0.0, 3.0, n_states)
    a[ArrayType.global_timesteps] = times

    # 6 solids: IDs 1..6; Part 1 (IDs 1, 2), Part 2 (IDs 3, 4), Part 3 (IDs 5, 6)
    solid_ids = np.array([1, 2, 3, 4, 5, 6])
    solid_part_indexes = np.array([0, 0, 1, 1, 2, 2])

    # 4 shells: IDs 101, 102, 103, 104; Part 4 (IDs 101, 102), Part 5 (IDs 103, 104)
    shell_ids = np.array([101, 102, 103, 104])
    shell_part_indexes = np.array([3, 3, 4, 4])

    part_ids = np.array([1, 2, 3, 4, 5])
    a[ArrayType.part_titles_ids] = part_ids
    a[ArrayType.part_titles] = np.array([f"part_{p}".encode("latin-1").ljust(72) for p in part_ids])

    # Nodes: IDs 1..49 and node 1001
    node_ids = np.concatenate([np.arange(1, 50), np.array([1001])])
    n_nodes = len(node_ids)
    a[ArrayType.node_ids] = node_ids

    # Reference coordinates
    node_coords = np.zeros((n_nodes, 3), dtype=float)
    for i in range(n_nodes):
        node_coords[i] = [float(i * 1.5), float(i * 2.0), float(i * 0.5)]
    # Node 1001 is at index 49
    node_coords[49] = [10.0, 20.0, 30.0]
    a[ArrayType.node_coordinates] = node_coords

    # Node displacement (d3plot stores deformed coordinates)
    node_disp = np.zeros((n_states, n_nodes, 3), dtype=float)
    for s in range(n_states):
        factor = (s + 1) * 0.1
        node_disp[s] = node_coords + factor
        # Node 1001 specific displacement: e.g. dx=1.2, dy=2.4, dz=3.6 at state 30 (s=29)
        node_disp[s, 49] = node_coords[49] + np.array([0.04 * (s + 1), 0.08 * (s + 1), 0.12 * (s + 1)])
    a[ArrayType.node_displacement] = node_disp

    # Node velocities
    node_velo = np.zeros((n_states, n_nodes, 3), dtype=float)
    for s in range(n_states):
        node_velo[s, 49] = [1.5, 2.5, 3.5]
    a[ArrayType.node_velocity] = node_velo

    # Connectivity: solid 5 (in Part 3) references node 1001 (index 49)
    solid_node_indexes = np.zeros((6, 8), dtype=int)
    for e in range(6):
        solid_node_indexes[e] = np.arange(e, e + 8)
    solid_node_indexes[4, 0] = 49  # solid 5 contains node 1001
    a[ArrayType.element_solid_ids] = solid_ids
    a[ArrayType.element_solid_part_indexes] = solid_part_indexes
    a[ArrayType.element_solid_node_indexes] = solid_node_indexes

    # Shell connectivity
    shell_node_indexes = np.zeros((4, 4), dtype=int)
    for e in range(4):
        shell_node_indexes[e] = np.arange(e + 10, e + 14)
    a[ArrayType.element_shell_ids] = shell_ids
    a[ArrayType.element_shell_part_indexes] = shell_part_indexes
    a[ArrayType.element_shell_node_indexes] = shell_node_indexes

    # Solid stress: (n_states, 6 solids, 1 point, 6 components)
    solid_stress = np.zeros((n_states, 6, 1, 6))
    for s_idx in range(n_states):
        factor = (s_idx + 1) * 10.0
        for e_idx in range(6):
            solid_stress[s_idx, e_idx, 0, 0] = factor * (e_idx + 1)         # sxx
            solid_stress[s_idx, e_idx, 0, 1] = factor * (e_idx + 1) * 0.5   # syy
            solid_stress[s_idx, e_idx, 0, 2] = factor * (e_idx + 1) * 0.2   # szz
            solid_stress[s_idx, e_idx, 0, 3] = factor * 2.0                 # sxy
            solid_stress[s_idx, e_idx, 0, 4] = factor * 1.5                 # syz
            solid_stress[s_idx, e_idx, 0, 5] = factor * 1.0                 # szx
    a[ArrayType.element_solid_stress] = solid_stress
    a[ArrayType.element_solid_effective_plastic_strain] = np.ones((n_states, 6, 1)) * 0.05

    # Solid alive: element 6 deleted from state 15 onward
    solid_alive = np.ones((n_states, 6), dtype=float)
    solid_alive[15:, 5] = 0.0
    a[ArrayType.element_solid_is_alive] = solid_alive

    # Shell stress
    shell_stress = np.zeros((n_states, 4, 1, 6))
    for s_idx in range(n_states):
        factor = (s_idx + 1) * 5.0
        for e_idx in range(4):
            shell_stress[s_idx, e_idx, 0, 0] = factor * (e_idx + 1)
            shell_stress[s_idx, e_idx, 0, 1] = factor * (e_idx + 1) * 0.4
            shell_stress[s_idx, e_idx, 0, 2] = 0.0
            shell_stress[s_idx, e_idx, 0, 3] = factor * 1.2
            shell_stress[s_idx, e_idx, 0, 4] = 0.0
            shell_stress[s_idx, e_idx, 0, 5] = 0.0
    a[ArrayType.element_shell_stress] = shell_stress
    a[ArrayType.element_shell_effective_plastic_strain] = np.ones((n_states, 4, 1)) * 0.02

    shell_alive = np.ones((n_states, 4), dtype=float)
    shell_alive[20:, 3] = 0.0
    a[ArrayType.element_shell_is_alive] = shell_alive

    d3plot_path = tmp_path / "d3plot"
    plot.write_d3plot(str(d3plot_path))
    return d3plot_path


# ==============================================================================
# Acceptance Criterion 1: Node, Element, Part Identify query
# ==============================================================================

def test_acceptance_1_node_identify(identify_d3plot: Path) -> None:
    """Acceptance 1: Query node ID, coordinates, connected elements, belonging parts, and state displacement."""
    service = Service(Settings(identify_d3plot.parent, allowed_roots=(identify_d3plot.parent,)))

    res = service.query_entities(
        str(identify_d3plot),
        entity_type="node",
        entity_ids=1001,
        state=30,
        quantity="displacement",
    )
    assert res["status"] == "succeeded"
    data = res["data"]
    assert data["count"] == 1
    node = data["entity"]
    assert node["id"] == 1001

    # Coordinates
    assert node["coordinates"]["reference"] == [10.0, 20.0, 30.0]
    assert node["coordinates"]["deformed"] is not None

    # Belonging Part: connected via solid 5 to Part 3
    assert 3 in node["part_ids"]
    assert "part_3" in node["part_names"]

    # Connected elements
    connected = node["connectivity"]["connected_elements"]
    assert any(c["id"] == 5 and c["type"] == "solid" for c in connected)

    # State result values
    results = node["results"]
    assert results["state"] == 30
    assert results["displacement"] is not None
    dx, dy, dz = results["displacement"]
    assert math.isclose(dx, 0.04 * 30, abs_tol=1e-5)
    assert math.isclose(dy, 0.08 * 30, abs_tol=1e-5)
    assert math.isclose(dz, 0.12 * 30, abs_tol=1e-5)
    expected_mag = math.sqrt(dx**2 + dy**2 + dz**2)
    assert math.isclose(results["displacement_magnitude"], expected_mag, abs_tol=1e-5)
    assert results["velocity"] == [1.5, 2.5, 3.5]


def test_acceptance_1_element_identify(identify_d3plot: Path) -> None:
    """Acceptance 1: Query element ID, type, connectivity, centroid, belonging Part, material, and state results."""
    service = Service(Settings(identify_d3plot.parent, allowed_roots=(identify_d3plot.parent,)))

    # Query solid element 5
    res = service.query_entities(
        str(identify_d3plot),
        entity_type="element",
        entity_ids=5,
        state=20,
        quantity="von_mises",
    )
    assert res["status"] == "succeeded"
    elem = res["data"]["entity"]
    assert elem["id"] == 5
    assert elem["element_type"] == "solid"

    # Connectivity
    assert len(elem["connectivity"]["node_ids"]) == 8
    assert 1001 in elem["connectivity"]["node_ids"]

    # Coordinates
    assert elem["coordinates"]["centroid"] is not None
    assert len(elem["coordinates"]["node_coordinates"]) == 8

    # Belonging Part
    assert elem["part_id"] == 3
    assert elem["part_name"] == "part_3"

    # Material: explicitly notes missing from d3plot without inventing fake ID
    assert elem["material"]["material_id"] is None
    assert "unavailable in d3plot" in elem["material"]["note"].lower()

    # State results
    res_val = elem["results"]
    assert res_val["state"] == 20
    assert res_val["is_alive"] is True
    assert "stress" in res_val
    assert "sxx" in res_val["stress"]
    assert "von_mises" in res_val
    assert res_val["quantity"] == "von_mises"
    assert res_val["value"] == res_val["von_mises"]


def test_acceptance_1_part_identify(identify_d3plot: Path) -> None:
    """Acceptance 1: Query part ID, title, elements, nodes, bounding box, and active/deleted element counts."""
    service = Service(Settings(identify_d3plot.parent, allowed_roots=(identify_d3plot.parent,)))

    res = service.query_entities(
        str(identify_d3plot),
        entity_type="part",
        entity_ids=3,
        state=20,
    )
    assert res["status"] == "succeeded"
    part = res["data"]["entity"]
    assert part["id"] == 3
    assert part["name"] == "part_3"

    # Elements
    assert part["elements"]["count"] == 2
    assert part["elements"]["element_ids"] == [5, 6]
    assert part["elements"]["types"] == {"solid": 2}

    # Member nodes
    assert 1001 in part["nodes"]["node_ids"]
    assert part["nodes"]["count"] > 0

    # Coordinates
    assert part["coordinates"]["bounding_box"] is not None
    assert part["coordinates"]["centroid"] is not None

    # State 20 results: solid element 6 is deleted at state 20
    assert part["results"]["state"] == 20
    assert part["results"]["active_element_count"] == 1
    assert part["results"]["deleted_element_count"] == 1


# ==============================================================================
# Acceptance Criterion 2: Equivalence with Q03 extract_field
# ==============================================================================

def test_acceptance_2_equivalence_with_q03_solid(identify_d3plot: Path) -> None:
    """Acceptance 2: Results match Q03 extract_field for the same element, state, and quantity."""
    service = Service(Settings(identify_d3plot.parent, allowed_roots=(identify_d3plot.parent,)))

    # Solid element 5 at state 20 (1-based state 20, 0-based index 19)
    # Q03 extract_field treats state=19 as 0-based state index 19 (state_1based=20)
    q03_res = service.extract_field(
        str(identify_d3plot),
        family="solid",
        quantity="von_mises",
        state=19,
        entity_ids=[5],
    )
    assert q03_res["status"] == "succeeded"
    q03_val = q03_res["data"]["extrema"]["max"]["value"]

    # G04 query_entities at state 20 (1-based)
    g04_res = service.query_entities(
        str(identify_d3plot),
        entity_type="element",
        entity_ids=5,
        state=20,
        quantity="von_mises",
    )
    assert g04_res["status"] == "succeeded"
    g04_val = g04_res["data"]["entity"]["results"]["value"]

    assert math.isclose(g04_val, q03_val, rel_tol=1e-7, abs_tol=1e-7)

    # Check stress component sxx equivalence
    q03_sxx = service.extract_field(
        str(identify_d3plot),
        family="solid",
        quantity="sxx",
        state=19,
        entity_ids=[5],
    )["data"]["extrema"]["max"]["value"]

    g04_sxx = service.query_entities(
        str(identify_d3plot),
        entity_type="element",
        entity_ids=5,
        state=20,
        quantity="sxx",
    )["data"]["entity"]["results"]["value"]

    assert math.isclose(g04_sxx, q03_sxx, rel_tol=1e-7, abs_tol=1e-7)


def test_acceptance_2_equivalence_with_q03_shell(identify_d3plot: Path) -> None:
    """Acceptance 2: Shell element results match Q03 extract_field identically."""
    service = Service(Settings(identify_d3plot.parent, allowed_roots=(identify_d3plot.parent,)))

    # Shell element 101 at state 10 (1-based state 10, 0-based index 9)
    q03_res = service.extract_field(
        str(identify_d3plot),
        family="shell",
        quantity="von_mises",
        state=9,
        entity_ids=[101],
    )
    q03_vm = q03_res["data"]["extrema"]["max"]["value"]

    g04_res = service.query_entities(
        str(identify_d3plot),
        entity_type="shell",
        entity_ids=101,
        state=10,
        quantity="von_mises",
    )
    g04_vm = g04_res["data"]["entity"]["results"]["value"]

    assert math.isclose(g04_vm, q03_vm, rel_tol=1e-7, abs_tol=1e-7)


# ==============================================================================
# Acceptance 3 / User Story
# ==============================================================================

def test_user_story_node_1001_displacement_and_part_at_state_30(identify_d3plot: Path) -> None:
    """User Story: 节点 1001 的坐标和它在第 30 个状态的位移是多少？属于哪个 Part？"""
    service = Service(Settings(identify_d3plot.parent, allowed_roots=(identify_d3plot.parent,)))

    res = service.query_entities(
        str(identify_d3plot),
        entity_type="node",
        entity_ids=1001,
        state=30,
        quantity="displacement",
    )
    assert res["status"] == "succeeded"
    node = res["data"]["entity"]

    # 1. 节点 1001 的坐标
    assert node["coordinates"]["reference"] == [10.0, 20.0, 30.0]

    # 2. 第 30 个状态的位移
    assert node["results"]["state"] == 30
    dx, dy, dz = node["results"]["displacement"]
    assert math.isclose(dx, 1.2, abs_tol=1e-4)
    assert math.isclose(dy, 2.4, abs_tol=1e-4)
    assert math.isclose(dz, 3.6, abs_tol=1e-4)
    assert math.isclose(node["results"]["displacement_magnitude"], math.sqrt(1.2**2 + 2.4**2 + 3.6**2), abs_tol=1e-4)

    # 3. 属于哪个 Part
    assert node["part_ids"] == [3]
    assert node["part_names"] == ["part_3"]


# ==============================================================================
# Keyword Deck Entity Queries
# ==============================================================================

def test_keyword_deck_identify_nodes_and_elements(tmp_path: Path) -> None:
    """Keyword deck: Query nodes, elements, parts, materials from standard .k file."""
    k_content = """*KEYWORD
*PART
Plate
         1         1         1         0         0         0         0         0
*SECTION_SHELL
         1         1    0.0000         0         0         0         0         0
    1.0000    1.0000    1.0000    1.0000    0.0000    0.0000    0.0000         0
*MAT_ELASTIC
         1   7.85e-9    210000       0.3         0         0         0         0
*NODE
       101       0.0       0.0       0.0       0       0
       102      10.0       0.0       0.0       0       0
       103      10.0      10.0       0.0       0       0
       104       0.0      10.0       0.0       0       0
*ELEMENT_SHELL
         1         1       101       102       103       104
*END
"""
    k_file = tmp_path / "model.k"
    k_file.write_text(k_content, encoding="latin1")

    service = Service(Settings(tmp_path, allowed_roots=(tmp_path,)))

    # Node query
    node_res = service.query_entities(str(k_file), entity_type="node", entity_ids=101)
    assert node_res["status"] == "succeeded"
    n101 = node_res["data"]["entity"]
    assert n101["id"] == 101
    assert n101["coordinates"]["reference"] == [0.0, 0.0, 0.0]
    assert n101["part_ids"] == [1]
    assert n101["part_names"] == ["Plate"]
    assert n101["connectivity"]["connected_elements"] == [{"type": "shell", "id": 1}]

    # Element query
    elem_res = service.query_entities(str(k_file), entity_type="element", entity_ids=1)
    assert elem_res["status"] == "succeeded"
    e1 = elem_res["data"]["entity"]
    assert e1["id"] == 1
    assert e1["element_type"] == "shell"
    assert e1["connectivity"]["node_ids"] == [101, 102, 103, 104]
    assert e1["part_id"] == 1
    assert e1["part_name"] == "Plate"
    assert e1["material"]["material_id"] == 1
    assert e1["coordinates"]["centroid"] == [5.0, 5.0, 0.0]

    # Part query
    part_res = service.query_entities(str(k_file), entity_type="part", entity_ids=1)
    assert part_res["status"] == "succeeded"
    p1 = part_res["data"]["entity"]
    assert p1["id"] == 1
    assert p1["name"] == "Plate"
    assert p1["material"]["material_id"] == 1
    assert p1["elements"]["count"] == 1
    assert p1["nodes"]["count"] == 4
    assert p1["coordinates"]["bounding_box"] == {"min": [0.0, 0.0, 0.0], "max": [10.0, 10.0, 0.0]}


# ==============================================================================
# Error Handling and Edge Cases
# ==============================================================================

def test_missing_entities_raise_error(identify_d3plot: Path) -> None:
    """Missing node/element/part IDs raise explicit ValueError; never invent fake IDs."""
    service = Service(Settings(identify_d3plot.parent, allowed_roots=(identify_d3plot.parent,)))

    with pytest.raises(ValueError, match="Node ID.*not found"):
        service.query_entities(str(identify_d3plot), entity_type="node", entity_ids=999999)

    with pytest.raises(ValueError, match="Element ID.*not found"):
        service.query_entities(str(identify_d3plot), entity_type="element", entity_ids=888888)

    with pytest.raises(ValueError, match="Part ID.*not found"):
        service.query_entities(str(identify_d3plot), entity_type="part", entity_ids=777777)


def test_invalid_state_raises_error(identify_d3plot: Path) -> None:
    """Invalid 1-based state raises ValueError."""
    service = Service(Settings(identify_d3plot.parent, allowed_roots=(identify_d3plot.parent,)))

    with pytest.raises(ValueError, match="State must be 1.."):
        service.query_entities(str(identify_d3plot), entity_type="node", entity_ids=1001, state=0)

    with pytest.raises(ValueError, match="State must be 1.."):
        service.query_entities(str(identify_d3plot), entity_type="node", entity_ids=1001, state=999)


def test_network_path_refused(tmp_path: Path) -> None:
    """Network UNC paths are strictly refused."""
    service = Service(Settings(tmp_path, allowed_roots=(tmp_path,)))
    with pytest.raises(ValueError, match="Network path"):
        service.query_entities(r"\\remote_server\share\d3plot", entity_type="node")


def test_paging_all_entities(identify_d3plot: Path) -> None:
    """Paging with offset and limit correctly pages through entities."""
    service = Service(Settings(identify_d3plot.parent, allowed_roots=(identify_d3plot.parent,)))

    # Query all nodes paged
    p1 = service.query_entities(str(identify_d3plot), entity_type="node", offset=0, limit=5)
    assert p1["data"]["count"] == 5
    assert p1["data"]["total"] == 50
    ids_p1 = [e["id"] for e in p1["data"]["entities"]]

    p2 = service.query_entities(str(identify_d3plot), entity_type="node", offset=5, limit=5)
    assert p2["data"]["count"] == 5
    ids_p2 = [e["id"] for e in p2["data"]["entities"]]

    assert set(ids_p1).isdisjoint(set(ids_p2))


# ==============================================================================
# Public Corpus Tests
# ==============================================================================

def test_public_corpus_d3plot_projectile() -> None:
    """Validate on real public corpus d3plot_projectile: projectile (Part 1) vs target plate (Part 2)."""
    corpus_file = Path(r"F:\PythonWoking\temp\20260930-lsprepost-mcp-development\corpus\public-results\ansys__example-data\result_files\d3plot_projectile\d3plot")
    if not corpus_file.exists():
        pytest.skip(f"Public corpus file not found: {corpus_file}")

    service = Service(Settings(corpus_file.parent, allowed_roots=(corpus_file.parent,)))

    # Query Part 1 (projectile) and Part 2 (plate)
    parts_res = service.query_entities(str(corpus_file), entity_type="part")
    assert parts_res["status"] == "succeeded"
    assert parts_res["data"]["total"] >= 2
    p_ids = [p["id"] for p in parts_res["data"]["entities"]]
    assert 1 in p_ids
    assert 2 in p_ids

    # Query a solid element in Part 1 (e.g. element 100) at state 5
    el_res = service.query_entities(
        str(corpus_file),
        entity_type="solid",
        entity_ids=100,
        state=6,
        quantity="von_mises",
    )
    assert el_res["status"] == "succeeded"
    elem = el_res["data"]["entity"]
    assert elem["id"] == 100
    assert elem["part_id"] == 1
    assert elem["results"]["von_mises"] > 0.0

    # Cross-check with Q03 extract_field on element 100 at state 5 (0-based)
    q03_res = service.extract_field(
        str(corpus_file),
        family="solid",
        quantity="von_mises",
        state=5,
        entity_ids=[100],
    )
    q03_vm = q03_res["data"]["extrema"]["max"]["value"]
    assert math.isclose(elem["results"]["von_mises"], q03_vm, rel_tol=1e-6, abs_tol=1e-6)
