"""I03: discovery reports conflicts; execution refuses them before dispatch."""

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.native import versions
from ls_prepost_mcp.service import Service


def resource(file="4.10.0.1", product="4.10.0.1", fixed="4.10.0.1"):
    return dict(file_version=file, product_version=product, fixed_file_version=fixed, product_name="LS-PrePost")


def test_configured_label_conflict_is_reported_and_rejected_at_dispatch(tmp_path, monkeypatch):
    executable = tmp_path / "actual410.exe"
    executable.touch()
    monkeypatch.setattr(versions, "read_version_resource", lambda _: resource())
    service = Service(Settings(tmp_path / "work", executable, profiles={"4.13": executable}))
    listing = service.list_installations()["profiles"][0]
    assert listing["capabilities"]["configured_label_conflict"] is True
    monkeypatch.setattr(Service, "probe_environment", lambda *a, **k: pytest.fail("Must reject before dispatch"))
    with pytest.raises(ValueError, match="label conflicts"):
        service.run_on_version("4.13", "probe_environment", {})
    assert not (tmp_path / "work/jobs").exists()


def test_disagreeing_resource_does_not_break_discovery_but_blocks_execution(tmp_path, monkeypatch):
    executable = tmp_path / "disagree.exe"
    executable.touch()
    monkeypatch.setattr(versions, "read_version_resource", lambda _: resource(product="4.13.0.1"))
    service = Service(Settings(tmp_path / "work", executable, profiles={"4.10": executable}))
    rows = service.list_installations()["profiles"]
    assert len(rows) == 1 and rows[0]["capabilities"]["resource_conflict"] is True
    assert versions.profile(executable)["resource_conflict"] is True
    with pytest.raises(ValueError, match="strings disagree"):
        versions.require_installation(executable)
