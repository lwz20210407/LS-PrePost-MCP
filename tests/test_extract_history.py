"""Tests for Q05 multi-entity time-history extraction across node, element, part, and global modes."""

from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.history import extract_history
from ls_prepost_mcp.service import Service


@pytest.fixture
def mock_binout_db(tmp_path):
    pytest.importorskip("lasso.dyna")
    from lasso.dyna.lsda_py3 import Lsda

    binout_path = tmp_path / "binout0000"
    f = Lsda(str(binout_path), "w")

    times = [0.0, 0.001, 0.002, 0.003]

    # 1. nodout
    f.cd("/nodout/metadata", 1)
    f.write("ids", Lsda.I4, [1001, 1002])
    for k, t in enumerate(times, start=1):
        f.cd(f"/nodout/d{k:06d}", 1)
        f.write("time", Lsda.R8, [t])
        f.write("x_displacement", Lsda.R8, [0.0, 0.0])
        f.write("y_displacement", Lsda.R8, [1.0 * (k - 1), 2.0 * (k - 1)])
        f.write("z_displacement", Lsda.R8, [3.0 * (k - 1), 4.0 * (k - 1)])

    # 2. elout (solid elements)
    f.cd("/elout/solid/metadata", 1)
    f.write("ids", Lsda.I4, [500, 501])
    for k, t in enumerate(times, start=1):
        f.cd(f"/elout/solid/d{k:06d}", 1)
        f.write("time", Lsda.R8, [t])
        f.write("sig_xx", Lsda.R8, [100.0 * (k - 1), 150.0 * (k - 1)])
        f.write("sig_yy", Lsda.R8, [50.0 * (k - 1), 60.0 * (k - 1)])
        f.write("sig_zz", Lsda.R8, [20.0 * (k - 1), 30.0 * (k - 1)])
        f.write("sig_xy", Lsda.R8, [0.0, 0.0])
        f.write("sig_yz", Lsda.R8, [0.0, 0.0])
        f.write("sig_zx", Lsda.R8, [0.0, 0.0])
        f.write("effective_stress", Lsda.R8, [80.0 * (k - 1), 110.0 * (k - 1)])

    # 3. matsum (parts)
    f.cd("/matsum/metadata", 1)
    f.write("ids", Lsda.I4, [1, 2])
    for k, t in enumerate(times, start=1):
        f.cd(f"/matsum/d{k:06d}", 1)
        f.write("time", Lsda.R8, [t])
        f.write("internal_energy", Lsda.R8, [400.0 * (k - 1), 100.0 * (k - 1)])
        f.write("kinetic_energy", Lsda.R8, [80.0 * (k - 1), 20.0 * (k - 1)])

    # 4. glstat (global)
    for k, t in enumerate(times, start=1):
        f.cd(f"/glstat/d{k:06d}", 1)
        f.write("time", Lsda.R8, [t])
        f.write("total_energy", Lsda.R8, [600.0 * (k - 1)])
        f.write("internal_energy", Lsda.R8, [500.0 * (k - 1)])
        f.write("kinetic_energy", Lsda.R8, [100.0 * (k - 1)])

    f.close()
    return binout_path


def test_extract_node_history_batch(mock_binout_db):
    summary, headers, rows = extract_history(
        source=mock_binout_db,
        entity_type="node",
        entity_ids=[1001, 1002],
        quantity="displacement",
        components=["z", "magnitude"],
        units="mm",
    )

    assert summary["entity_type"] == "node"
    assert summary["entity_ids"] == [1001, 1002]
    assert len(rows) == 4
    assert "node_1001_z" in headers
    assert "node_1002_magnitude" in headers

    # Verify values at last step (k=4, k-1=3): node 1001 z = 3 * 3 = 9.0
    z_1001_idx = headers.index("node_1001_z")
    assert rows[-1][z_1001_idx] == pytest.approx(9.0)


def test_extract_element_history(mock_binout_db):
    summary, headers, rows = extract_history(
        source=mock_binout_db,
        entity_type="element",
        entity_ids=[500],
        quantity="stress",
        components=["von_mises", "sig_xx"],
        units="MPa",
    )

    assert summary["entity_type"] == "element"
    assert "element_500_von_mises" in headers
    assert "element_500_sig_xx" in headers

    # Final step: element 500 effective stress = 80 * 3 = 240.0
    vm_idx = headers.index("element_500_von_mises")
    assert rows[-1][vm_idx] == pytest.approx(240.0)


def test_extract_part_history(mock_binout_db):
    summary, headers, rows = extract_history(
        source=mock_binout_db,
        entity_type="part",
        entity_ids=[2],
        components=["kinetic_energy"],
        units="J",
    )

    assert summary["entity_type"] == "part"
    assert "part_2_kinetic_energy" in headers
    ke_idx = headers.index("part_2_kinetic_energy")
    # Part 2 KE at step 4 = 20 * 3 = 60.0
    assert rows[-1][ke_idx] == pytest.approx(60.0)


def test_extract_global_history(mock_binout_db):
    summary, headers, rows = extract_history(
        source=mock_binout_db,
        entity_type="global",
        components=["total_energy", "internal_energy"],
        units="J",
    )

    assert summary["entity_type"] == "global"
    assert "global_total_energy" in headers
    te_idx = headers.index("global_total_energy")
    assert rows[-1][te_idx] == pytest.approx(1800.0)


def test_service_extract_history_end_to_end(mock_binout_db, tmp_path):
    service = Service(Settings(tmp_path))

    res = service.extract_history(
        source=str(mock_binout_db),
        entity_type="node",
        entity_ids=[1001],
        quantity="displacement",
        components=["z"],
        units="mm",
    )

    assert res["status"] == "succeeded"
    data = res["data"]
    assert data["entity_type"] == "node"
    assert "node_1001_z" in data["curves"]

    artifacts = res["artifacts"]
    csv_art = next(a for a in artifacts if a["kind"] == "csv")
    csv_text = Path(csv_art["path"]).read_text(encoding="utf-8")
    assert "node_1001_z" in csv_text
