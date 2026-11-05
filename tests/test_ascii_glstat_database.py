"""Q06 synthetic GLSTAT layouts; source values are not calculated or inferred."""
import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


def block(time, kinetic, internal, total, hourglass=.25):
    return f"""
 dt of cycle 1 is controlled by synthetic input
 time........................... {time}
 time step...................... 2D-4
 kinetic energy................. {kinetic}
 internal energy................ {internal}
 hourglass energy .............. {hourglass}
 total energy................... {total}
 total energy / initial energy.. 1.0
 energy ratio w/o eroded energy. 1.0
 global x velocity.............. 0.0
 time per zone cycle.(nanosec).. 20
"""


TEXT = "Synthetic result\n ls-dyna synthetic\n" + block(0, 1.25, 5.5, 6.75) + block(2, 9, 7, 16)


def extract(tmp_path, text=TEXT, component="kinetic_energy", **options):
    source = tmp_path / "glstat"
    source.write_text(text, encoding="utf8")
    before = source.read_bytes()
    result = Service(Settings(tmp_path)).extract_database(str(source), "glstat", component,
                                                         "J", time_units="ms", **options)
    assert source.read_bytes() == before
    return result


@pytest.mark.parametrize("component,values,label", [
    ("kinetic_energy", [1.25, 9], "kinetic energy"),
    ("internal_energy", [5.5, 7], "internal energy"),
    ("total_energy", [6.75, 16], "total energy"),
    ("hourglass_energy", [.25, .25], "hourglass energy"),
    ("time_step", [.0002, .0002], "time step"),
])
def test_ascii_glstat_exposes_global_scalar_and_original_label(tmp_path, component, values, label):
    result = extract(tmp_path, component=component)
    assert result["status"] == "succeeded", result["error"]
    assert result["backend"] == "ls-dyna-ascii"
    data = result["data"]
    assert data["source_format"] == "glstat"
    assert data["source_kind"] == "ascii"
    assert data["ids"] is None and data["stored_columns"] is None
    assert data["entity_count"] == 0 and data["state_count"] == data["row_count"] == 2
    assert data["entity_metadata"]["scope"] == "global"
    assert data["source_column_names"] == {"time": ["time"], "value": [label]}
    assert data["units"] == "J" and data["time_units"] == "ms"
    assert not data["shards"] and data["repeated_times_dropped"] == 0
    artifact = result["artifacts"][0]
    with Path(artifact["path"]).open(newline="", encoding="utf8") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == ["time", component]
    assert [list(map(float, row)) for row in rows[1:]] == [[0., values[0]], [2., values[1]]]


def test_ascii_glstat_keeps_label_variants_without_changing_values(tmp_path):
    result = extract(tmp_path, TEXT.replace("kinetic energy", "KINETIC   ENERGY", 1))
    assert result["status"] == "succeeded", result["error"]
    assert result["data"]["source_column_names"]["value"] == ["KINETIC   ENERGY", "kinetic energy"]


def test_ascii_glstat_accepts_a_single_dot_leader(tmp_path):
    result = extract(tmp_path, TEXT.replace("kinetic energy.................", "kinetic energy."))
    assert result["status"] == "succeeded", result["error"]


def test_punctuated_titles_are_not_numeric_fields_even_when_repeated(tmp_path):
    text = TEXT.replace("Synthetic result", "Example A. B")
    text = text.replace("\n dt of cycle", "\n Example A. B\n dt of cycle")
    result = extract(tmp_path, text)
    assert result["status"] == "succeeded", result["error"]


@pytest.mark.parametrize("text,reason", [
    (TEXT.replace("kinetic energy................. 9\n", ""), "missing"),
    (TEXT.replace("total energy................... 16\n", ""), "missing"),
    (TEXT.replace("time step...................... 2D-4\n", "", 1), "missing"),
    (TEXT.replace("time........................... 2", "time........................... 0"), "increasing"),
    (TEXT.replace("time........................... 2", "time........................... -2"), "increasing"),
    (TEXT.replace("1.25", "NaN", 1), "Nonfinite"),
    (TEXT.replace("global x velocity.............. 0.0", "global x velocity.............. Infinity", 1), "Nonfinite"),
    (TEXT.replace("internal energy................ 5.5", "internal energy................ 5.5 extra", 1), "number"),
    (TEXT.replace("total energy................... 6.75", "total energy................... 6.75\n total energy................... 6.75", 1), "Duplicate"),
    (TEXT.rsplit("time per zone cycle.", 1)[0], "Truncated"),
    (TEXT.replace("kinetic energy................. 1.25", "kinetic energy 1.25", 1), "Malformed"),
    ("only a title", "No supported"),
], ids=["missing-kinetic", "missing-total", "missing-step", "duplicate-time", "backward-time",
        "nan", "inf-unused-field", "extra-number-token", "duplicate-field", "truncated-ending",
        "missing-leader", "no-records"])
def test_ascii_glstat_malformed_records_fail_without_verified_output(tmp_path, text, reason):
    result = extract(tmp_path, text)
    assert result["status"] == "failed" and not result["artifacts"]
    assert reason.lower() in result["error"]["message"].lower()


def test_ascii_glstat_rejects_incomplete_next_cycle_and_numeric_underflow(tmp_path):
    result = extract(tmp_path, TEXT + "\n dt of cycle 3 is controlled by synthetic input\n")
    assert result["status"] == "failed" and "Truncated" in result["error"]["message"]
    result = extract(tmp_path, TEXT.replace("1.25", "1e-999", 1))
    assert result["status"] == "failed" and "underflow" in result["error"]["message"]


def test_truncated_time_field_after_a_complete_block_is_not_ignored(tmp_path):
    result = extract(tmp_path, TEXT + "\n time...........................\n")
    assert result["status"] == "failed" and "Truncated" in result["error"]["message"]


def test_time_step_and_energy_ratio_cannot_substitute_for_their_distinct_fields(tmp_path):
    result = extract(tmp_path, TEXT.replace("time........................... 0\n", "", 1))
    assert result["status"] == "failed"
    result = extract(tmp_path, TEXT.replace("total energy................... 6.75\n", "", 1),
                     component="total_energy")
    assert result["status"] == "failed" and "total_energy" in result["error"]["message"]


def test_optional_glstat_component_must_exist_in_every_block(tmp_path):
    result = extract(tmp_path, TEXT.replace("hourglass energy .............. 0.25\n", "", 1),
                     component="hourglass_energy")
    assert result["status"] == "failed" and "missing" in result["error"]["message"].lower()


@pytest.mark.parametrize("options,reason", [
    ({"branch": "global"}, "branch"),
    ({"shard": "binout0000"}, "shard"),
    ({"entity_ids": [1]}, "no entity IDs"),
    ({"native_check": True}, "native_check"),
])
def test_ascii_glstat_does_not_invent_binary_or_entity_semantics(tmp_path, options, reason):
    (tmp_path / "binout0000").write_bytes(b"must not be read")
    result = extract(tmp_path, **options)
    assert result["status"] == "failed" and not result["artifacts"]
    assert reason in result["error"]["message"]


def test_ascii_glstat_database_must_match_explicit_file(tmp_path):
    source = tmp_path / "glstat"
    source.write_text(TEXT)
    result = Service(Settings(tmp_path)).extract_database(str(source), "matsum", "kinetic_energy", "J")
    assert result["status"] == "failed" and "match" in result["error"]["message"]


def test_ascii_glstat_component_names_are_explicit(tmp_path):
    result = extract(tmp_path, component="energy")
    assert result["status"] == "failed" and "component" in result["error"]["message"]


def test_valid_ascii_glstat_does_not_open_a_binary_sibling(tmp_path, monkeypatch):
    def wrong_backend(*args, **kwargs):
        pytest.fail("ASCII GLSTAT must not substitute a binary sibling")

    monkeypatch.setattr("ls_prepost_mcp.domain.results.lasso_backend.binout_curves", wrong_backend)
    (tmp_path / "binout").write_bytes(b"not a binary database")
    result = extract(tmp_path)
    assert result["status"] == "succeeded", result["error"]
    assert result["data"]["source_kind"] == "ascii"


def test_ascii_glstat_does_not_require_the_optional_lasso_package(tmp_path, monkeypatch):
    for name in [name for name in sys.modules if name == "lasso" or name.startswith("lasso.")]:
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setitem(sys.modules, "lasso", None)
    result = extract(tmp_path)
    assert result["status"] == "succeeded", result["error"]
    assert result["backend"] == "ls-dyna-ascii"


def test_glstat_binds_success_to_runtime_source_hash(tmp_path):
    result = extract(tmp_path)
    digest = hashlib.sha256((tmp_path / "glstat").read_bytes()).hexdigest()
    assert result["status"] == "succeeded", result["error"]
    assert result["data"]["source_sha256"] == digest
    manifest = json.loads(next(tmp_path.rglob("job.json")).read_text(encoding="utf8"))
    assert manifest["inputs"] == [{"path": str(tmp_path / "glstat"), "sha256": digest}]


def test_glstat_source_mutation_after_parse_fails_without_verified_artifact(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import ascii_glstat

    source = tmp_path / "glstat"
    source.write_text(TEXT, encoding="utf8")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    original = ascii_glstat.read

    def changed_after_parse(path, component):
        result = original(path, component)
        Path(path).write_text(TEXT + "\nchanged after parse\n", encoding="utf8")
        return result

    monkeypatch.setattr(ascii_glstat, "read", changed_after_parse)
    result = Service(Settings(tmp_path)).extract_database(str(source), "glstat", "total_energy", "J")
    assert result["status"] == "failed" and not result["artifacts"]
    assert "changed" in result["error"]["message"].lower()
    manifest = json.loads(next(tmp_path.rglob("job.json")).read_text(encoding="utf8"))
    assert manifest["status"] == "failed" and manifest["inputs"][0]["sha256"] == before


def test_glstat_cycle_head_cannot_replace_a_head_waiting_for_time(tmp_path):
    text = TEXT.replace("time........................... 2", "dt of cycle 2 is controlled by synthetic input\n time........................... 2")
    result = extract(tmp_path, text)
    assert result["status"] == "failed" and "cycle" in result["error"]["message"].lower()


@pytest.mark.parametrize("options", [{"branch": "global"}, {"shard": "binout0000"}, {"native_check": "false"}])
def test_glstat_preparation_failures_keep_the_requested_ascii_backend(tmp_path, options):
    result = extract(tmp_path, **options)
    assert result["status"] == "failed"
    assert result["backend"] == result["data"]["backend"] == "ls-dyna-ascii"


def test_glstat_hashing_remains_bounded_if_source_grows_after_size_validation(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import ascii_glstat

    original = ascii_glstat.validate_size
    monkeypatch.setattr(ascii_glstat, "MAX_BYTES", 10_000)

    def growth_after_size_check(path):
        original(path)
        with Path(path).open("a", encoding="utf8") as stream:
            stream.write("x" * 10_000)

    def should_not_parse(*args):
        pytest.fail("Oversized input must fail during bounded hashing before parsing")

    monkeypatch.setattr(ascii_glstat, "validate_size", growth_after_size_check)
    monkeypatch.setattr(ascii_glstat, "read", should_not_parse)
    source = tmp_path / "glstat"
    source.write_text(TEXT, encoding="utf8")
    result = Service(Settings(tmp_path)).extract_database(str(source), "glstat", "total_energy", "J")
    assert result["status"] == "failed" and not result["artifacts"]
    assert "hashing" in result["error"]["message"]


@pytest.mark.parametrize("name", ["MAX_BYTES", "MAX_RECORD_CHARS", "MAX_STATES"])
def test_ascii_glstat_resource_bounds(tmp_path, monkeypatch, name):
    from ls_prepost_mcp.domain.results import ascii_glstat

    monkeypatch.setattr(ascii_glstat, name, 1)
    result = extract(tmp_path)
    assert result["status"] == "failed" and result["backend"] == "ls-dyna-ascii"
    assert not result["artifacts"]


def test_ascii_glstat_follows_input_confinement(tmp_path):
    workspace = tmp_path / "allowed"
    workspace.mkdir()
    source = tmp_path / "glstat"
    source.write_text(TEXT)
    result = Service(Settings(workspace)).extract_database(str(source), "glstat", "total_energy", "J")
    assert result["status"] == "failed" and "allowed roots" in result["error"]["message"]
