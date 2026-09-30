import pytest

pytest.importorskip("ansys.dyna.core")

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


def test_material_round_trip_and_original_preserved(tmp_path):
    service = Service(Settings(tmp_path))
    created = service.create_elastic_material(17, 1.0, 100.0, .3, "consistent-test-units")
    assert created["status"] == "succeeded", created
    source = created["artifacts"][0]["path"]
    from pathlib import Path
    before = Path(source).read_bytes()
    updated = service.update_elastic_material(source, 17, 2.0, 200.0, .25, "consistent-test-units")
    assert updated["status"] == "succeeded", updated
    assert updated["data"]["reimport_verified"]
    assert Path(source).read_bytes() == before
    assert updated["artifacts"][0]["path"] != source


def test_material_physical_parameter_and_identity_rejection(tmp_path):
    service = Service(Settings(tmp_path))
    with pytest.raises(ValueError):
        service.create_elastic_material(1, -1, 100, .3, "test")
    created = service.create_elastic_material(1, 1, 100, .3, "test")
    missing = service.update_elastic_material(created["artifacts"][0]["path"], 2, 1, 100, .3, "test")
    assert missing["status"] == "failed"
