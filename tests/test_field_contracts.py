import csv
from types import SimpleNamespace

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.field_contracts import FieldSpec, ResultSelection, SamplingSpec
from ls_prepost_mcp.service import Service


def test_sampling_never_equates_native_mid_with_reader_slot_one():
    native = SamplingSpec.native("shell", "mid").describe()
    stored = SamplingSpec.stored([1], stress=True).describe()
    assert native["kind"] == "native_shell_layer" and native["native_selector"] == "MID"
    assert stored["kind"] == "stored_integration_point" and stored["value"] == [1]
    assert native["cross_backend_equivalence"] == stored["cross_backend_equivalence"] == "not_inferred"
    assert SamplingSpec.native("solid", "mid").native_selector == "0"
    assert SamplingSpec.native("solid", "1").native_selector == "1"
    assert SamplingSpec.native("node", "mid").kind == "not_applicable"
    for domain, selector in [
        ("node", "1"),
        ("node", "outer"),
        ("solid", "inner"),
        ("shell", True),
        ("solid", "0"),
    ]:
        with pytest.raises(ValueError):
            SamplingSpec.native(domain, selector)


def test_selection_is_immutable_bounded_metadata_with_ordered_identity():
    identifiers = list(range(1, 101))
    spec = ResultSelection("shell", identifiers, [2, 1])
    identifiers[0] = 999
    metadata = spec.describe()
    assert metadata["entity_count"] == 100 and len(metadata["entity_id_sample"]) == 20
    assert metadata["entity_id_sample"][0] == 1 and metadata["state_sample"] == [2, 1]
    assert (
        metadata["ordered_selection_sha256"]
        != ResultSelection("shell", list(range(1, 101)), [1, 2]).describe()["ordered_selection_sha256"]
    )
    assert ResultSelection("global", [], [1]).describe()["id_kind"] == "none"
    for domain, ids, states in [
        ("node", [True], [1]),
        ("node", [1], [0]),
        ("node", [1, 1], [1]),
        ("global", [1], [1]),
        ("node", {1: "not a list"}, [1]),
    ]:
        with pytest.raises(ValueError):
            ResultSelection(domain, ids, states)


def test_native_solid_point_mislabel_rejected_before_gui_dispatch(tmp_path):
    service = Service(Settings(tmp_path))
    for point in ("2", "8"):
        with pytest.raises(ValueError, match="can return point 1"):
            service.gui_session_action("not-started", "extract_native_stress",
                dict(element_type="solid", element_ids=[1001], states=[1],
                     integration_point=point, units="source_units"))
    assert not (tmp_path / "jobs").exists()
    # The separately named reader contract remains usable and does not silently
    # replace the rejected native operation.
    assert SamplingSpec.stored([8], stress=True).value == (8,)
    assert SamplingSpec.native("shell", "5").native_selector == "5"


def test_field_contract_preserves_units_and_rejects_backend_or_domain_confusion():
    selection = ResultSelection("shell", [7], [1])
    native = SamplingSpec.native("shell", "outer")
    spec = FieldSpec(
        "lsprepost",
        ["stress_x"],
        "MPa",
        selection,
        native,
        "native frame",
        "no additional averaging",
        "native population",
    )
    assert spec.describe()["units"] == dict(label="MPa", dimensional_validation=False, conversion="none")
    for backend, sampling in [
        ("lasso", native),
        ("lsprepost", SamplingSpec.stored([1])),
        ("lsprepost", SamplingSpec.native("solid", "mid")),
    ]:
        with pytest.raises(ValueError):
            FieldSpec(backend, ["stress_x"], "MPa", selection, sampling, "frame", "none", "stored")


def test_native_export_embeds_the_contract_and_preserves_scl_selector(tmp_path, monkeypatch):
    from ls_prepost_mcp.native_results import native_fields

    source = tmp_path / "d3plot"
    source.write_bytes(b"synthetic fixture")
    exe = tmp_path / "fake.exe"
    exe.touch()
    service = Service(Settings(tmp_path / "jobs-root", exe, allowed_roots=(tmp_path,)))
    requested_ids, requested_fields = [42], ["stress_x"]

    def execute(executable, command, directory, **kwargs):
        script = (directory / "extract.scl").read_text()
        assert '"stress_x",SOLID,0,' in script
        requested_ids[0] = 99
        requested_fields[0] = "stress_y"
        (directory / "native.csv").write_text("state,time,entity_id,stress_x\n1,0,42,2\n")
        return JobResult(operation=kwargs["operation"], job_id=directory.name, status="unverified", data=dict(returncode=0, timed_out=False))

    monkeypatch.setattr("ls_prepost_mcp.native_results.run_batch", execute)
    result = native_fields(
        service.settings, service.jobs, source, "solid", requested_ids, [1], requested_fields, "mid", "MPa"
    )
    assert result["status"] == "succeeded", result
    assert result["data"]["field_spec"] == result["parameters"]["field_spec"]
    assert result["data"]["field_spec"]["sampling"]["kind"] == "native_default"
    assert result["parameters"]["entity_ids"] == [42]
    assert result["parameters"]["fields"] == ["stress_x"]
    assert source.read_bytes() == b"synthetic fixture"


def test_reader_stress_and_scalar_slice_share_provenance_without_reinterpreting_axes(tmp_path, monkeypatch):
    source = tmp_path / "d3plot"
    source.write_bytes(b"synthetic reader fixture")
    values = np.zeros((1, 2, 2, 6))
    values[0, 1, 1, 0] = 100
    db = SimpleNamespace(
        arrays=dict(
            element_shell_stress=values, element_shell_ids=np.array([10, 70]), timesteps=np.array([0.5])
        )
    )
    monkeypatch.setattr("ls_prepost_mcp.post_tools.selected_database", lambda *args, **kwargs: (db, {2: 0}))
    monkeypatch.setattr("ls_prepost_mcp.post_tools.field_domain", lambda field: "shell")
    service = Service(Settings(tmp_path))
    tensor = service.extract_d3plot_stress(str(source), "shell", [70], [2], 2, "MPa")
    scalar = service.extract_d3plot_field(str(source), "element_shell_stress", [2], "MPa", [70], [2, 1])
    assert tensor["status"] == scalar["status"] == "succeeded", (tensor, scalar)
    tensor_spec = tensor["data"]["field_spec"]
    scalar_spec = scalar["data"]["field_spec"]
    assert tensor_spec["selection"] == scalar_spec["selection"]
    assert tensor_spec["sampling"]["kind"] == "stored_integration_point"
    assert scalar_spec["sampling"]["kind"] == "stored_axes"
    assert scalar_spec["sampling"]["value"] == [2, 1]
    with open(scalar["artifacts"][0]["path"]) as stream:
        row = next(csv.DictReader(stream))
    assert row["entity_id"] == "70" and float(row["value"]) == 100


def test_displacement_contract_records_the_actual_reference_subtraction(tmp_path, monkeypatch):
    pytest.importorskip("lasso.dyna")
    source = tmp_path / "d3plot"
    source.write_bytes(b"synthetic displacement")
    db = SimpleNamespace(
        arrays=dict(
            node_ids=np.array([91]),
            node_coordinates=np.array([[10.0, 20.0, 30.0]]),
            node_displacement=np.array([[[11.0, 22.0, 33.0]]]),
            timesteps=np.array([0.0]),
        )
    )
    monkeypatch.setattr("ls_prepost_mcp.post_tools.selected_database", lambda *args, **kwargs: (db, {1: 0}))
    monkeypatch.setattr("ls_prepost_mcp.post_tools.field_domain", lambda field: "node")
    result = Service(Settings(tmp_path)).extract_d3plot_field(
        str(source), "node_displacement", [1], "mm", [91], [1]
    )
    assert result["status"] == "succeeded", result
    assert result["data"]["field_spec"]["transformations"] == ["state_coordinates_minus_reference_nodes"]
    with open(result["artifacts"][0]["path"]) as stream:
        row = next(csv.DictReader(stream))
    assert float(row["value"]) == 1
