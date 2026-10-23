"""P1-9: a through-thickness arithmetic mean is not a shell layer."""
import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.results import lasso_backend as lb
from ls_prepost_mcp.service import Service


def model(tmp_path, monkeypatch, points=3):
    source = tmp_path / "d3plot"
    source.write_bytes(b"owned injected field source")
    stress = np.zeros((2, 2, points, 6))
    stress[..., 0] = np.linspace(-100., 100., points)
    plastic = np.broadcast_to(np.linspace(0., .4, points), (2, 2, points)).copy()
    data = {"timesteps": np.array([0., 1.]), "element_shell_ids": np.array([101, 102]),
            "element_shell_stress": stress, "element_shell_effective_plastic_strain": plastic,
            "element_shell_is_alive": np.array([[1., 1.], [1., 0.]])}
    monkeypatch.setattr(lb, "_arrays", lambda *a, **kw: data)
    monkeypatch.setattr(lb, "state_times", lambda *a: data["timesteps"])
    monkeypatch.setattr(lb, "header", lambda *a: {"deletion_data_stored": True})
    return Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,))), source, data


@pytest.mark.parametrize("points", [3, 5])
@pytest.mark.parametrize("quantity", ["stress", "sxx", "effective_plastic_strain"])
def test_multilayer_shell_cannot_default_to_a_zero_bending_mean(tmp_path, monkeypatch, points, quantity):
    service, source, _ = model(tmp_path, monkeypatch, points)
    result = service.extract_field(str(source), "shell", quantity, state=2, mask="all", units="declared")
    assert result["status"] == "failed", "A default layer mean silently erased bending"
    assert "stored_point" in result["error"]["message"]
    assert not result["artifacts"]


@pytest.mark.parametrize("quantity,expected", [("sxx", -100.), ("effective_plastic_strain", 0.)])
@pytest.mark.parametrize("points", [3, 5])
def test_scalar_shell_quantity_can_select_the_explicit_stored_point(tmp_path, monkeypatch, quantity, expected, points):
    service, source, _ = model(tmp_path, monkeypatch, points)
    result = service.extract_field(str(source), "shell", quantity, state=2, mask="all", units="declared", stored_point=1)
    assert result["status"] == "succeeded", result.get("error")
    assert result["data"]["values"] == [expected, expected]
    assert result["data"]["sampling"]["index"] == 1
    assert result["data"]["sampling"]["native_layer_equivalence"] == "not inferred"


def test_solid_stored_points_may_still_use_the_documented_gauss_point_mean(tmp_path, monkeypatch):
    _, _, data = model(tmp_path, monkeypatch)
    stress = data["element_shell_stress"]
    values, note = lb._element_values({"element_solid_stress": stress}, "solid", "sxx")
    assert np.all(values == 0.) and "mean" in note


@pytest.mark.parametrize("quantity", ["stress", "sxx"])
def test_scalar_and_tensor_reject_bad_state_before_creating_a_job(tmp_path, monkeypatch, quantity):
    service, source, _ = model(tmp_path, monkeypatch, points=1)
    with pytest.raises(ValueError, match="State|state"):
        service.extract_field(str(source), "shell", quantity, state=3, mask="all", units="declared")
    assert not service.jobs.list()


@pytest.mark.parametrize("quantity", ["stress", "sxx"])
def test_family_is_confined_before_even_reading_time_metadata(tmp_path, monkeypatch, quantity):
    service, source, _ = model(tmp_path, monkeypatch, points=1)
    monkeypatch.setattr(service, "_result_family", lambda *a: (_ for _ in ()).throw(ValueError("outside family")))
    monkeypatch.setattr(lb, "state_times", lambda *a: pytest.fail("Metadata read before family confinement"))
    with pytest.raises(ValueError, match="outside family"):
        service.extract_field(str(source), "shell", quantity, mask="all", units="declared")
