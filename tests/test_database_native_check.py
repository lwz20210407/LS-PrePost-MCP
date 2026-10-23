"""Q06 real-native adapter contract; synthetic CSVs test rejection without launching LSPP."""

import csv
import hashlib
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from tests.test_ascii_force_database import SECTION
from tests.test_ascii_force_database import contact as contact


def native_curve(tmp_path, values, *, shift=0, change_value=False):
    output = tmp_path / "native.csv"
    with output.open("w", newline="", encoding="utf8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["time", "value"])
        for t, v in zip((0, 2), values):
            writer.writerow([t + shift, v + (1 if change_value else 0)])
    return {
        "status": "succeeded",
        "job_id": "native-proof",
        "data": {"entity_id": 9},
        "artifacts": [
            {"path": str(output), "kind": "csv", "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
        ],
    }


@pytest.mark.parametrize(
    "component,code,values", [("x_force", 1, [1, 2]), ("y_force", 2, [-2, -3]), ("z_force", 3, [3, 4])]
)
def test_named_section_force_native_check_calls_real_adapter_and_preserves_reader_values(
    tmp_path, monkeypatch, component, code, values
):
    source = tmp_path / "secforc"
    source.write_text(SECTION)
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    calls = []

    def observed(path, database, component_code, units, entity_id=None, side=None):
        calls.append((path, database, component_code, units, entity_id, side))
        return native_curve(tmp_path, values)

    monkeypatch.setattr(service, "extract_native_ascii_curve", observed)
    result = service.extract_database(
        str(source), "secforc", component, "N", entity_ids=[9], time_units="s", native_check=True
    )
    assert result["status"] == "succeeded", result.get("error")
    assert calls == [(str(source), "secforc", code, "N", 9, None)]
    assert (
        result["backend"] == "ls-dyna-ascii" and result["data"]["native_comparison"]["backend"] == "lsprepost"
    )
    assert result["data"]["native_comparison"]["curves"][0]["entity_id"] == 9
    with Path(result["artifacts"][0]["path"]).open(newline="", encoding="utf8") as stream:
        assert [float(r[component]) for r in csv.DictReader(stream)] == values


@pytest.mark.parametrize("failure", ["time", "value", "sha", "source", "native_failed", "empty_native_error", "missing_csv"])
def test_native_comparison_failure_never_exposes_a_verified_reader_artifact(tmp_path, monkeypatch, failure):
    source = tmp_path / "secforc"
    source.write_text(SECTION)
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))

    def broken(*args, **kwargs):
        result = native_curve(
            tmp_path, [1, 2], shift=5e-7 if failure == "time" else 0, change_value=failure == "value"
        )
        if failure == "sha":
            result["artifacts"][0]["sha256"] = "0" * 64
        if failure == "source":
            source.write_text(SECTION + "changed\n")
        if failure == "native_failed":
            return {"status": "failed", "error": {"message": "Native ASCII command rejected"}}
        if failure == "empty_native_error":
            return {"status": "failed", "error": {"message": "  "}}
        if failure == "missing_csv":
            result["artifacts"] = []
        return result

    monkeypatch.setattr(service, "extract_native_ascii_curve", broken)
    result = service.extract_database(str(source), "secforc", "x_force", "N", native_check=True)
    assert result["status"] == "failed" and result["error"] and not result["artifacts"]


@pytest.mark.parametrize(
    "database,side,selector", [("secforc", None, "Sec-9"), ("rcforc", 0, "Sl-9"), ("rcforc", 1, "Ma-9")]
)
def test_native_ascii_uses_database_specific_entity_labels(tmp_path, monkeypatch, database, side, selector):
    from ls_prepost_mcp import native_results

    def finish(settings, jobs, action, params, source, build, parse, **kwargs):
        build(tmp_path)
        return (tmp_path / "commands.cfile").read_text(encoding="utf8")

    monkeypatch.setattr(native_results, "finish_native", finish)
    kwargs = {} if side is None else {"side": side}
    commands = native_results.native_ascii(None, None, None, database, 1, 9, "N", **kwargs)
    assert f"ascii {database} plot 1 {selector}" in commands


def test_contact_comparison_keeps_secondary_and_main_curves_separate(tmp_path, monkeypatch):
    source = tmp_path / "rcforc"
    source.write_text(contact())
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    calls = []

    def observed(path, database, component, units, entity_id=None, side=None):
        calls.append(side)
        result = native_curve(tmp_path, [1, 3] if side == 0 else [2, 6])
        result["data"] = {"entity_id": 7, "side": side}
        return result

    monkeypatch.setattr(service, "extract_native_ascii_curve", observed)
    result = service.extract_database(
        str(source), "rcforc", "x_force", "N", entity_ids=[7], native_check=True
    )
    assert result["status"] == "succeeded", result.get("error")
    assert calls == [0, 1] and result["data"]["ids"] == [7, 7]
    assert [(c["entity_id"], c["side"]) for c in result["data"]["native_comparison"]["curves"]] == [
        (7, 0),
        (7, 1),
    ]


@pytest.mark.parametrize("side", [None, True, False, 2, -1, "0"])
def test_native_contact_never_defaults_or_coerces_side(tmp_path, side):
    from ls_prepost_mcp.native_results import native_ascii

    with pytest.raises(ValueError, match="explicit side"):
        native_ascii(None, None, None, "rcforc", 1, 9, "N", side=side)


def test_unsupported_native_component_fails_before_reading_or_starting_a_job(tmp_path, monkeypatch):
    source = tmp_path / "secforc"
    source.write_text(SECTION)
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))

    def no_read(*args):
        pytest.fail("Unsupported native comparison reached the reader")

    monkeypatch.setattr(service, "_read_database", no_read)
    result = service.extract_database(str(source), "secforc", "x_moment", "N mm", native_check=True)
    assert result["status"] == "failed" and not result["artifacts"]
