"""Q06 SPCFORC Service preserves literal node vectors and explicit source boundaries."""
import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service

TEXT = """Synthetic SPC service contract
output at time = 0
node= 90 local x,y,z forces = 1 -2 3 setid= 7
node= 10 local x,y,z forces = -10 20 -30 setid= 0
node= 90 local x,y,z moments= 4 -5 6 setid= 7
node= 10 local x,y,z moments= -40 50 -60 setid= 0
force resultants = 0 0 0
output at time = 2
node= 10 local x,y,z moments= 41 -51 61 setid= 0
node= 10 local x,y,z forces = 0 -21 31 setid= 0
node= 90 local x,y,z moments= -7 8 -9 setid= 7
node= 90 local x,y,z forces = -0.0 11 -12 setid= 7
force resultants = 0 0 0
"""
EXPECTED = {"x_force": [1, -10, -0.0, 0], "y_force": [-2, 20, 11, -21], "z_force": [3, -30, -12, 31],
            "x_moment": [4, -40, -7, 41], "y_moment": [-5, 50, 8, -51], "z_moment": [6, -60, -9, 61]}


def extract(tmp_path, component="x_force", text=TEXT, **options):
    source = tmp_path / "spcforc"
    source.write_text(text, encoding="utf8")
    result = Service(Settings(tmp_path)).extract_database(str(source), "spcforc", component, "declared_quantity",
                                                         time_units="declared_time", **options)
    return source, result


@pytest.mark.parametrize("component", list(EXPECTED))
def test_spcforc_service_named_components_export_literal_values(tmp_path, component):
    source, result = extract(tmp_path, component)
    assert result["status"] == "succeeded", result["error"]
    data = result["data"]
    assert result["backend"] == "ls-dyna-ascii" and data["source_kind"] == "ascii"
    assert data["source_format"] == "spcforc" and data["ids"] == [90, 10]
    assert data["stored_columns"] == [0, 1] and data["state_count"] == 2 and data["row_count"] == 4
    assert data["units"] == "declared_quantity" and data["time_units"] == "declared_time"
    assert data["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert data["entity_metadata"]["setid"] == [7, 0]
    meta = data["entity_metadata"]
    assert meta["raw_node_id_tokens"] == [["90"], ["10"]]
    assert meta["raw_setid_tokens"] == [["7"], ["0"]]
    assert meta["frame"] == "local as printed; basis unidentified; no transform"
    assert "coordinate_system_ids" not in meta and meta["deletion_validity"] == "unknown"
    assert not meta["alive_mask_available"] and meta["validity"] == "raw_unmasked"
    assert not meta["summary_exported"] and meta["summary_records_validated"] == 2
    kind = "forces" if component.endswith("force") else "moments"
    assert meta["record_kind"] == kind and meta["component_axis"] == component[0]
    assert data["source_column_names"]["value"] == [f"local x,y,z {kind}"]
    assert not data["shards"] and data["repeated_times_dropped"] == 0
    with Path(result["artifacts"][0]["path"]).open(newline="", encoding="utf8") as stream:
        rows = list(csv.DictReader(stream))
    assert list(rows[0]) == ["time", "entity_id", component]
    assert [float(row[component]) for row in rows] == EXPECTED[component]
    assert [int(row["entity_id"]) for row in rows] == [90, 10, 90, 10]
    if component == "x_force":
        assert rows[2][component] == "-0.0"


def test_spcforc_service_selection_keeps_requested_id_order(tmp_path):
    _, result = extract(tmp_path, entity_ids=[10, 90])
    assert result["status"] == "succeeded", result["error"]
    assert result["data"]["ids"] == [10, 90] and result["data"]["stored_columns"] == [1, 0]
    with Path(result["artifacts"][0]["path"]).open(newline="", encoding="utf8") as stream:
        assert [int(row["entity_id"]) for row in csv.DictReader(stream)] == [10, 90, 10, 90]


def test_spcforc_service_hash_is_recorded_in_job_manifest(tmp_path):
    source, result = extract(tmp_path)
    assert result["status"] == "succeeded", result["error"]
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    job = json.loads(next(tmp_path.rglob("job.json")).read_text(encoding="utf8"))
    assert job["inputs"] == [{"path": str(source), "sha256": expected}]


@pytest.mark.parametrize("options", [{"native_check": True}, {"native_check": "false"}, {"branch": "node"},
                                     {"shard": "binout0000"}])
def test_spcforc_service_inapplicable_modes_fail_before_creating_a_job(tmp_path, monkeypatch, options):
    service = Service(Settings(tmp_path))
    source = tmp_path / "spcforc"
    source.write_text(TEXT, encoding="utf8")

    def forbidden(*args, **kwargs):
        pytest.fail("invalid mode must be rejected before a job/native process is created")

    monkeypatch.setattr(service.jobs, "create", forbidden)
    result = service.extract_database(str(source), "spcforc", "x_force", "units", **options)
    assert result["status"] == "failed" and not result["artifacts"]
    assert result["backend"] == "ls-dyna-ascii"


def test_spcforc_service_source_mutation_leaves_no_verified_artifact(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import ascii_spcforc

    original = ascii_spcforc.parse

    def changed(lines, component):
        data = original(lines, component)
        with (tmp_path / "spcforc").open("a", encoding="utf8") as stream:
            stream.write("changed")
        return data

    monkeypatch.setattr(ascii_spcforc, "parse", changed)
    _, result = extract(tmp_path)
    assert result["status"] == "failed" and not result["artifacts"]
    assert "changed" in result["error"]["message"]


@pytest.mark.parametrize("component", ["x_force", "y_force", "z_force", "x_moment", "y_moment", "z_moment"])
def test_spcforc_force_only_all_named_components_have_explicit_availability(tmp_path, component):
    text = "\n".join(line for line in TEXT.splitlines() if "moments=" not in line) + "\n"
    _, result = extract(tmp_path, component=component, text=text)
    if component.endswith("force"):
        assert result["status"] == "succeeded", result["error"]
        assert result["data"]["entity_metadata"]["moment_records_available"] is False
    else:
        assert result["status"] == "failed" and not result["artifacts"]
        assert "not stored; missing values are unknown" in result["error"]["message"]


def test_spcforc_needs_no_lasso_and_never_reads_binary_or_model_siblings(tmp_path, monkeypatch):
    for name in [key for key in sys.modules if key == "lasso" or key.startswith("lasso.")]:
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setitem(sys.modules, "lasso", None)

    def forbidden(*args, **kwargs):
        pytest.fail("ASCII SPCFORC must not read a binary sibling or model")

    monkeypatch.setattr("ls_prepost_mcp.domain.results.lasso_backend.binout_curves", forbidden)
    (tmp_path / "binout").write_bytes(b"not a binary database")
    (tmp_path / "model.k").write_text("not a keyword deck", encoding="utf8")
    assert extract(tmp_path)[1]["status"] == "succeeded"


def test_spcforc_imports_only_its_selected_ascii_reader(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain import results

    for suffix in ("ascii_glstat", "ascii_matsum", "ascii_nodout", "ascii_sleout", "ascii_forces"):
        monkeypatch.delattr(results, suffix, raising=False)
        monkeypatch.setitem(sys.modules, f"ls_prepost_mcp.domain.results.{suffix}", None)
    assert extract(tmp_path)[1]["status"] == "succeeded"


@pytest.mark.parametrize("limit", ["MAX_BYTES", "MAX_RECORD_CHARS", "MAX_ROWS"])
def test_spcforc_service_resource_budgets_fail_without_verified_artifacts(tmp_path, monkeypatch, limit):
    from ls_prepost_mcp.domain.results import ascii_spcforc

    monkeypatch.setattr(ascii_spcforc, limit, 1)
    _, result = extract(tmp_path)
    assert result["status"] == "failed" and not result["artifacts"]
    assert result["backend"] == "ls-dyna-ascii"


def test_spcforc_size_is_checked_before_hashing(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import ascii_spcforc

    monkeypatch.setattr(ascii_spcforc, "MAX_BYTES", 1)

    def forbidden(*args, **kwargs):
        pytest.fail("oversized ASCII must fail before hashing source bytes")

    monkeypatch.setattr("ls_prepost_mcp.results_target_tools._sha256", forbidden)
    assert extract(tmp_path)[1]["status"] == "failed"


def test_spcforc_growth_fails_before_reading_extra_bytes(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import ascii_records, ascii_spcforc

    original_validate, original_lines = ascii_spcforc.validate_size, ascii_records.bounded_lines
    observed = dict(validations=0, chars=0)
    limit = len(TEXT.encode()) + 50
    monkeypatch.setattr(ascii_spcforc, "MAX_BYTES", limit)

    def grows(path):
        original_validate(path)
        observed["validations"] += 1
        if observed["validations"] == 2:
            with Path(path).open("a", encoding="utf8") as stream:
                stream.write("\n" * limit)

    def counted(*args, **kwargs):
        for line in original_lines(*args, **kwargs):
            observed["chars"] += len(line)
            yield line

    monkeypatch.setattr(ascii_spcforc, "validate_size", grows)
    monkeypatch.setattr(ascii_records, "bounded_lines", counted)
    _, result = extract(tmp_path)
    assert result["status"] == "failed" and not result["artifacts"]
    assert observed == dict(validations=2, chars=0)


@pytest.mark.parametrize("options", [{"entity_ids": [999]}, {"entity_ids": [90, 90]}, {"entity_ids": []},
                                     {"entity_ids": [True]}, {"entity_ids": [-1]}])
def test_spcforc_unknown_or_ambiguous_entity_selection_fails(tmp_path, options):
    _, result = extract(tmp_path, **options)
    assert result["status"] == "failed" and not result["artifacts"]
    assert result["backend"] == "ls-dyna-ascii"


@pytest.mark.parametrize("component", ["force_magnitude", "x_force_global", "mass", "1"])
def test_spcforc_unmapped_named_components_are_not_native_numeric_codes(tmp_path, component):
    _, result = extract(tmp_path, component=component)
    assert result["status"] == "failed" and not result["artifacts"]
    assert "SPCFORC component must be" in result["error"]["message"]


@pytest.mark.parametrize("filename,database", [("spcforc.txt", "spcforc"), ("spcforc", "rcforc"),
                                              ("other", "spcforc")])
def test_spcforc_explicit_filename_and_database_must_match_before_a_job(tmp_path, monkeypatch, filename, database):
    source = tmp_path / filename
    source.write_text(TEXT, encoding="utf8")
    service = Service(Settings(tmp_path))

    def forbidden(*args, **kwargs):
        pytest.fail("source mismatch must be rejected before creating a job")

    monkeypatch.setattr(service.jobs, "create", forbidden)
    result = service.extract_database(str(source), database, "x_force", "units")
    assert result["status"] == "failed" and not result["artifacts"]


def test_spcforc_source_must_stay_within_allowed_roots(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = tmp_path / "spcforc"
    source.write_text(TEXT, encoding="utf8")
    service = Service(Settings(allowed, allowed_roots=(allowed,)))

    def forbidden(*args, **kwargs):
        pytest.fail("out-of-root source must be rejected before creating a job")

    monkeypatch.setattr(service.jobs, "create", forbidden)
    result = service.extract_database(str(source), "spcforc", "x_force", "units")
    assert result["status"] == "failed" and not result["artifacts"]


@pytest.mark.parametrize("old,new", [("forces = 1 -2 3", "forces = 1e-999 -2 3"),
                                    ("moments= 4 -5 6", "moments= NaN -5 6"),
                                    ("force resultants = 0 0 0", "force resultants = 0 0"),
                                    ("output at time = 2", "output at time = 0"),
                                    ("node= 90 local x,y,z forces = -0.0 11 -12 setid= 7",
                                     "node= 90 local x,y,z forces = -0.0 11 -12 setid= 8")])
def test_spcforc_invalid_unselected_fields_fail_with_no_verified_product(tmp_path, old, new):
    _, result = extract(tmp_path, component="z_force", text=TEXT.replace(old, new))
    assert result["status"] == "failed" and not result["artifacts"]
    assert result["backend"] == "ls-dyna-ascii"
