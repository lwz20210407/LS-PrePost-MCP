"""Q05 canonical histories reuse the shared d3plot/binout readers."""

import csv

import numpy as np
import pytest

pytest.importorskip("lasso.dyna")
from lasso.dyna import ArrayType, D3plot  # noqa: E402

from ls_prepost_mcp.config import Settings  # noqa: E402
from ls_prepost_mcp.service import Service  # noqa: E402
from tests.test_field_metrics import write_synthetic  # noqa: E402
from tests.test_results_target_tools import _shard  # noqa: E402


@pytest.fixture
def history_model(tmp_path):
    folder = tmp_path / "seed"
    folder.mkdir()
    seed = write_synthetic(folder / "d3plot")
    plot = D3plot(str(seed))
    initial = np.arange(72).reshape(24, 3).astype(float)
    plot.arrays[ArrayType.node_coordinates] = initial
    plot.arrays[ArrayType.node_displacement] = (
        initial[None] + np.array([0.0, 1.0, 2.0])[:, None, None] * np.arange(1, 25)[None, :, None]
    )
    plot.arrays[ArrayType.global_kinetic_energy] = np.array([0.0, 10.0, 20.0])
    plot.arrays[ArrayType.part_kinetic_energy] = np.array(
        [[1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0], [3.0, 6.0, 9.0, 12.0]]
    )
    target = tmp_path / "model"
    target.mkdir()
    plot.write_d3plot(str(target / "d3plot"))
    return target / "d3plot"


@pytest.mark.parametrize(
    "domain,quantity,ids,expected",
    [
        ("node", "displacement_z", [2, 5], [[0.0, 2.0, 4.0], [0.0, 5.0, 10.0]]),
        ("solid", "von_mises", [10, 20], [[0.0, 0.0, 200.0], [0.0, 0.0, np.sqrt(3) * 60]]),
        ("part", "kinetic_energy", [7, 9], [[1.0, 2.0, 3.0], [2.0, 4.0, 6.0]]),
        ("global", "kinetic_energy", None, [[0.0, 10.0, 20.0]]),
    ],
)
def test_four_history_domains_emit_exact_ordered_curves(
    history_model, tmp_path, domain, quantity, ids, expected
):
    service = Service(Settings(tmp_path / "work", allowed_roots=(history_model.parent,)))
    result = service.extract_history(
        str(history_model), domain, quantity, ids, units="declared_source_units", time_units="ms"
    )
    assert result["status"] == "succeeded", result.get("error")
    assert len(result["artifacts"]) == len(expected)
    from ls_prepost_mcp.core.contracts import CurveSpec

    spec = CurveSpec.model_validate(
        service.jobs.get(result["job_id"])["parameters"]["curve_spec"], strict=False
    )
    assert (
        spec.entity_type == domain
        and spec.component == quantity
        and spec.sign == "as_stored"
        and spec.alignment == "none"
    )
    assert spec.source.units is None  # Quantity/time labels do not define the model's complete unit system.
    assert [c["entity_id"] for c in result["data"]["curves"]] == (ids or [None])
    for artifact, values in zip(result["artifacts"], expected):
        with open(artifact["path"], newline="", encoding="utf8") as stream:
            rows = list(csv.DictReader(stream))
        np.testing.assert_allclose([float(r["value"]) for r in rows], values, rtol=1e-7)
        assert [float(r["time"]) for r in rows] == [0.0, 0.5, 1.0]
        assert artifact["metadata"]["units"] == {"time": "ms", "value": "declared_source_units"}
        assert artifact["metadata"]["quantity"] == quantity
        assert artifact["metadata"]["backend"].startswith("lasso")


@pytest.mark.parametrize("domain,database,ids", [("part", "matsum", [11, 22]), ("global", "glstat", None)])
def test_explicit_binout_history_uses_shared_database_reader(tmp_path, domain, database, ids):
    source = tmp_path / "binout"
    _shard(source, database, [0.0, 1.0, 2.0], ids=ids, component="kinetic_energy")
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    result = service.extract_history(
        str(source), domain, "kinetic_energy", ids, units="J", time_units="s", source_kind="binout"
    )
    assert result["status"] == "succeeded", result.get("error")
    assert len(result["data"]["curves"]) == (len(ids) if ids else 1)
    assert result["data"]["source_kind"] == "binout"


@pytest.mark.parametrize("bad", [[], [1, 1], [True], [0], [-1], ["2"]])
def test_bad_entity_ids_never_create_a_history_job(history_model, tmp_path, bad):
    service = Service(Settings(tmp_path / "work", allowed_roots=(history_model.parent,)))
    with pytest.raises(ValueError, match="IDs"):
        service.extract_history(
            str(history_model), "node", "displacement_z", bad, units="mm", time_units="ms"
        )
    assert not service.jobs.list()


@pytest.mark.parametrize("fault", ["duplicate_ids", "global_vector"])
def test_malformed_stored_axes_are_refused_not_collapsed(history_model, tmp_path, monkeypatch, fault):
    from ls_prepost_mcp.domain.results import lasso_backend as lb

    arrays = lb._arrays(history_model)
    if fault == "duplicate_ids":
        arrays["node_ids"][1] = arrays["node_ids"][0]
        domain, quantity, ids = "node", "displacement_z", [1]
    else:
        arrays["global_kinetic_energy"] = np.ones((3, 2))
        domain, quantity, ids = "global", "kinetic_energy", None
    monkeypatch.setattr(lb, "_arrays", lambda *a, **k: arrays)
    service = Service(Settings(tmp_path / "work", allowed_roots=(history_model.parent,)))
    result = service.extract_history(str(history_model), domain, quantity, ids, units="raw", time_units="raw")
    assert result["status"] == "failed" and not result["artifacts"]


@pytest.mark.parametrize("fault", [None, "value", "missing", "duplicate", "time"])
def test_native_history_comparison_does_not_backfill_reader_values(
    history_model, tmp_path, monkeypatch, fault
):
    import hashlib

    service = Service(Settings(tmp_path / "work", allowed_roots=(history_model.parent,)))

    def native(path, domain, ids, states, fields, sampling, units):
        assert ids == [2, 5] and states == [1, 2, 3] and fields == ["disp_z"]
        directory, manifest = service.jobs.create("native-test", {})
        output = directory / "native.csv"
        rows = [[s, t, uid, float((s - 1) * uid)] for s, t in [(1, 0.0), (2, 0.5), (3, 1.0)] for uid in ids]
        if fault == "value":
            rows[0][-1] = 100
        elif fault == "missing":
            rows.pop()
        elif fault == "duplicate":
            rows.append(rows[0])
        elif fault == "time":
            rows[0][1] = 0.2
        with output.open("w", newline="", encoding="utf8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["state", "time", "entity_id", "disp_z"])
            writer.writerows(rows)
        return {
            "status": "succeeded",
            "job_id": manifest["job_id"],
            "artifacts": [
                {
                    "kind": "csv",
                    "path": str(output),
                    "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                }
            ],
        }

    monkeypatch.setattr(service, "extract_native_fields", native)
    result = service.extract_history(
        str(history_model), "node", "displacement_z", [2, 5], units="mm", time_units="ms", native_check=True
    )
    assert result["status"] == ("failed" if fault else "succeeded")
    if fault:
        assert not result["artifacts"] and result["error"]
    else:
        assert result["data"]["native_comparison"]["backend"] == "lsprepost"


def test_missing_requested_entity_and_source_change_never_return_verified_curves(
    history_model, tmp_path, monkeypatch
):
    from ls_prepost_mcp import history_tools

    service = Service(Settings(tmp_path / "work", allowed_roots=(history_model.parent,)))
    missing = service.extract_history(
        str(history_model), "node", "displacement_z", [2, 9999], units="mm", time_units="ms"
    )
    assert missing["status"] == "failed" and not missing["artifacts"]
    original = history_tools.write_csv

    def changed(*a, **k):
        result = original(*a, **k)
        history_model.write_bytes(history_model.read_bytes() + b"changed")
        return result

    monkeypatch.setattr(history_tools, "write_csv", changed)
    result = service.extract_history(
        str(history_model), "node", "displacement_z", [2], units="mm", time_units="ms"
    )
    assert result["status"] == "failed" and not result["artifacts"]


def test_duplicate_d3plot_times_are_preserved_not_resampled(history_model, tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import lasso_backend as lb

    arrays = lb._arrays(history_model)
    arrays["timesteps"] = np.array([0.0, 0.0, 1.0])
    monkeypatch.setattr(lb, "_arrays", lambda *a, **k: arrays)
    service = Service(Settings(tmp_path / "work", allowed_roots=(history_model.parent,)))
    result = service.extract_history(
        str(history_model), "global", "kinetic_energy", units="J", time_units="ms"
    )
    assert result["status"] == "succeeded"
    with open(result["artifacts"][0]["path"], newline="", encoding="utf8") as stream:
        assert [float(row["time"]) for row in csv.DictReader(stream)] == [0.0, 0.0, 1.0]


def test_binout_native_time_grid_is_not_compared_with_value_absolute_tolerance(tmp_path, monkeypatch):
    import hashlib

    source = tmp_path / "binout"
    _shard(source, "glstat", [0.0, 1.0, 2.0], component="kinetic_energy")
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))

    def native(*args, **kwargs):
        directory, manifest = service.jobs.create("native-test", {})
        output = directory / "native.csv"
        output.write_text("time,value\n0.0000005,0\n1,1\n2,2\n", encoding="utf8")
        return {
            "status": "succeeded",
            "job_id": manifest["job_id"],
            "artifacts": [
                {
                    "kind": "csv",
                    "path": str(output),
                    "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                }
            ],
        }

    monkeypatch.setattr(service, "extract_native_binout_curve", native)
    result = service.extract_history(
        str(source),
        "global",
        "kinetic_energy",
        units="J",
        time_units="s",
        source_kind="binout",
        native_check=True,
    )
    assert result["status"] == "failed" and not result["artifacts"]


def test_written_csv_is_checked_against_reader_samples_not_only_its_hash(
    history_model, tmp_path, monkeypatch
):
    import hashlib

    from ls_prepost_mcp import history_tools

    service = Service(Settings(tmp_path / "work", allowed_roots=(history_model.parent,)))
    original = history_tools.write_csv

    def corrupted(path, *a, **k):
        record = original(path, *a, **k)
        text = path.read_text(encoding="utf8").replace("0.0,0.0", "0.0,999.0", 1)
        path.write_text(text, encoding="utf8")
        record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        return record

    monkeypatch.setattr(history_tools, "write_csv", corrupted)
    result = service.extract_history(
        str(history_model), "node", "displacement_z", [2], units="mm", time_units="ms"
    )
    assert result["status"] == "failed" and not result["artifacts"]


def test_mcp_history_schema_requires_unit_declarations_and_explicit_modes(tmp_path):
    import asyncio

    from ls_prepost_mcp.server import build_server

    tools = asyncio.run(build_server(Settings(tmp_path / "work"), "full").list_tools())
    schema = next(t for t in tools if t.name == "extract_history").inputSchema
    assert {"units", "time_units"} <= set(schema["required"])
    assert set(schema["properties"]["domain"]["enum"]) == {
        "node",
        "solid",
        "shell",
        "tshell",
        "beam",
        "part",
        "global",
    }
    assert set(schema["properties"]["source_kind"]["enum"]) == {"d3plot", "binout"}
