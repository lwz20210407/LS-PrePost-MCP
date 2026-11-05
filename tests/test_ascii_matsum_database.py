"""Q06 names map to literal MATSUM fields, preserving stored part identity."""
import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


def record(pid, internal, kinetic, hourglass, eroded_ie=0, eroded_ke=0):
    return (f"mat.#= {pid} inten= {internal} kinen= {kinetic} "
            f"eroded_ie= {eroded_ie} eroded_ke= {eroded_ke}\n"
            f"x-mom= 0 y-mom= 0 z-mom= 0\nhgeng= {hourglass}\n")


TEXT = ("Synthetic MATSUM\n{BEGIN LEGEND}\nEntity # Title\n90 Part ninety\n10 Part ten\n{END LEGEND}\n"
        "time = 0\n" + record(90, 9, 0, .5) + record(10, 1, 2, .1) +
        "time = 2\n" + record(10, 3, 4, .2, .01, .02) + record(90, 11, 6, .7, .03, .04))


def extract(tmp_path, text=TEXT, component="kinetic_energy", **options):
    source = tmp_path / "matsum"
    source.write_text(text, encoding="utf8")
    return Service(Settings(tmp_path)).extract_database(str(source), "matsum", component,
                                                       "source_energy", time_units="source_time", **options)


def rows(result):
    artifact = result["artifacts"][0]
    path = Path(artifact["path"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
    with path.open(newline="", encoding="utf8") as stream:
        return list(csv.reader(stream))


@pytest.mark.parametrize("component,label,expected", [
    ("kinetic_energy", "kinen", [0, 2, 6, 4]),
    ("internal_energy", "inten", [9, 1, 11, 3]),
    ("hourglass_energy", "hgeng", [.5, .1, .7, .2]),
    ("eroded_internal_energy", "eroded_ie", [0, 0, .03, .01]),
    ("eroded_kinetic_energy", "eroded_ke", [0, 0, .04, .02]),
])
def test_named_matsum_energy_preserves_raw_ids_and_source_columns(tmp_path, component, label, expected):
    result = extract(tmp_path, component=component)
    assert result["status"] == "succeeded", result["error"]
    data = result["data"]
    assert result["backend"] == data["backend"] == "ls-dyna-ascii"
    assert data["source_format"] == "matsum" and data["source_kind"] == "ascii"
    assert data["ids"] == [90, 10] and data["stored_columns"] == [0, 1]
    assert data["source_column_names"] == {"time": ["time"], "id": ["mat.#"], "value": [label]}
    assert data["state_count"] == 2 and data["entity_count"] == 2 and data["row_count"] == 4
    assert data["units"] == "source_energy" and data["time_units"] == "source_time"
    assert not data["shards"] and data["repeated_times_dropped"] == 0
    exported = rows(result)
    assert exported[0] == ["time", "entity_id", component]
    assert [float(row[-1]) for row in exported[1:]] == expected
    assert [int(row[1]) for row in exported[1:]] == [90, 10, 90, 10]
    assert [float(row[0]) for row in exported[1:]] == [0, 0, 2, 2]


def test_matsum_caller_selection_retains_original_stored_columns(tmp_path):
    result = extract(tmp_path, entity_ids=[10, 90])
    assert result["status"] == "succeeded", result["error"]
    assert result["data"]["ids"] == [10, 90] and result["data"]["stored_columns"] == [1, 0]
    assert [int(row[1]) for row in rows(result)[1:]] == [10, 90, 10, 90]


def test_matsum_explicit_zero_is_not_unknown(tmp_path):
    result = extract(tmp_path, component="eroded_internal_energy")
    assert result["status"] == "succeeded", result["error"]
    assert [float(row[-1]) for row in rows(result)[1:]][:2] == [0., 0.]


@pytest.mark.parametrize("text,reason", [
    (TEXT.replace("kinen= 0 ", "", 1), "missing"),
    (TEXT.replace("eroded_ie= 0 ", "", 1), "missing"),
    (TEXT.replace("hgeng= 0.7\n", ""), "missing"),
    (TEXT.replace("time = 2", "time = 0"), "increasing"),
    (TEXT.replace("time = 2", "time = -1"), "increasing"),
    (TEXT + "time = 3\n", "empty"),
    (TEXT.replace("time = 2", "time = 1\ntime = 2"), "empty"),
    (TEXT.replace(record(90, 11, 6, .7, .03, .04), ""), "part"),
    (TEXT + record(90, 11, 6, .7), "Duplicate"),
    (TEXT.replace("hgeng= 0.5", "hgeng= 0.5 hgeng= 1", 1), "Duplicate"),
    (TEXT.replace("inten= 9", "inten= NaN", 1), "Nonfinite"),
    (TEXT.replace("kinen= 0", "kinen= Infinity", 1), "Nonfinite"),
    (TEXT.replace("kinen= 0", "kinen= missing", 1), "Invalid"),
    (TEXT.replace("mat.#= 90", "mat.#= 0", 1), "positive"),
    (TEXT.replace("mat.#= 90", "mat.#= 90suffix", 1), "identifier"),
    (TEXT.replace("time = 2", "time ="), "time"),
    (TEXT.replace("time = 2", "time = NaN"), "Nonfinite"),
    (TEXT.replace("time = 2", "time = 1_000"), "numeric token"),
    (TEXT.replace("time = 2", "time = 1e-999"), "underflows"),
    (TEXT.replace("kinen= 0", "kinen= 1e-999", 1), "underflows"),
    (TEXT.replace("{END LEGEND}", ""), "legend"),
    (TEXT.replace("{BEGIN LEGEND}", "{BEGIN LEGEND}\n{BEGIN LEGEND}", 1), "legend"),
    (TEXT.replace("{BEGIN LEGEND}", "{END LEGEND}", 1), "legend"),
])
def test_matsum_invalid_records_fail_without_verified_output(tmp_path, text, reason):
    result = extract(tmp_path, text, component="eroded_internal_energy")
    assert result["status"] == "failed" and not result["artifacts"]
    assert result["backend"] == "ls-dyna-ascii"
    assert reason.lower() in result["error"]["message"].lower()


@pytest.mark.parametrize("component", ["total_energy", "mass", "momentum_x", "eroded_hourglass_energy", "energy"])
def test_matsum_unimplemented_component_fails_explicitly(tmp_path, component):
    result = extract(tmp_path, component=component)
    assert result["status"] == "failed" and "component" in result["error"]["message"]


@pytest.mark.parametrize("options", [{"branch": "part"}, {"shard": "binout0000"},
                                     {"native_check": True}, {"entity_ids": [999]}])
def test_matsum_does_not_substitute_binary_or_unverified_native_semantics(tmp_path, options):
    (tmp_path / "binout0000").write_bytes(b"must not be used")
    result = extract(tmp_path, **options)
    assert result["status"] == "failed" and not result["artifacts"]
    assert result["backend"] == "ls-dyna-ascii"


def test_matsum_does_not_require_optional_lasso(tmp_path, monkeypatch):
    for name in [name for name in sys.modules if name == "lasso" or name.startswith("lasso.")]:
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setitem(sys.modules, "lasso", None)
    result = extract(tmp_path)
    assert result["status"] == "succeeded", result["error"]


def test_matsum_source_hash_is_bound_before_and_after_read(tmp_path):
    result = extract(tmp_path)
    assert result["status"] == "succeeded", result["error"]
    source = tmp_path / "matsum"
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    assert result["data"]["source_sha256"] == sha
    manifest = json.loads(next(tmp_path.rglob("job.json")).read_text())
    assert manifest["inputs"] == [{"path": str(source), "sha256": sha}]


def test_matsum_source_changed_during_parse_is_failed(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import ascii_matsum

    original = ascii_matsum.read

    def changed(path, component):
        value = original(path, component)
        with Path(path).open("a") as stream:
            stream.write("changed\n")
        return value

    monkeypatch.setattr(ascii_matsum, "read", changed)
    result = extract(tmp_path)
    assert result["status"] == "failed" and not result["artifacts"]
    assert "changed" in result["error"]["message"].lower()


def test_matsum_keeps_q12_sparse_unknowns(tmp_path):
    from ls_prepost_mcp.domain.results.energy_readers import read_ascii_matsum

    source = tmp_path / "matsum"
    source.write_text("time = 0\nmat.#= 10 inten= 3\ntime = 1\nmat.#= 10 inten= 4 kinen= 0\n")
    parts = read_ascii_matsum(source)
    assert parts[10]["kinetic_energy"] == [None, 0.]
    assert parts[10]["hourglass_energy"] is None


def test_matsum_source_label_case_and_d_exponents_are_preserved(tmp_path):
    result = extract(tmp_path, TEXT.replace("kinen= 2", "KINEN= 2D0", 1))
    assert result["status"] == "succeeded", result["error"]
    assert result["data"]["source_column_names"]["value"] == ["kinen", "KINEN"]
    assert float(rows(result)[2][-1]) == 2.


def test_matsum_strict_decoding_does_not_change_q12_default(tmp_path):
    from ls_prepost_mcp.domain.results.energy_readers import read_ascii_matsum

    source = tmp_path / "matsum"
    source.write_bytes(b"title\xff\n" + TEXT.encode())
    assert read_ascii_matsum(source)[90]["kinetic_energy"] == [0., 6.]
    result = Service(Settings(tmp_path)).extract_database(str(source), "matsum", "kinetic_energy", "J")
    assert result["status"] == "failed" and not result["artifacts"]


def test_matsum_growth_is_bounded_before_parser(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import ascii_matsum

    original = ascii_matsum.validate_size
    monkeypatch.setattr(ascii_matsum, "MAX_BYTES", 10_000)

    def grows(path):
        original(path)
        with Path(path).open("a") as stream:
            stream.write("x" * 10_000)

    def should_not_parse(*args):
        pytest.fail("Oversize input must fail before parsing")

    monkeypatch.setattr(ascii_matsum, "validate_size", grows)
    monkeypatch.setattr(ascii_matsum, "read", should_not_parse)
    result = extract(tmp_path)
    assert result["status"] == "failed" and "hashing" in result["error"]["message"]
    assert not result["artifacts"]


def test_trailing_empty_assignment_cannot_hide_behind_an_earlier_value(tmp_path):
    result = extract(tmp_path, TEXT + "inten=\n")
    assert result["status"] == "failed" and not result["artifacts"]
    assert "missing number" in result["error"]["message"].lower()


def test_q12_existing_line_limit_keeps_its_runtime_value(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import energy_readers

    source = tmp_path / "matsum"
    source.write_text(TEXT)
    monkeypatch.setattr(energy_readers, "MAX_RECORD_CHARS", 1)
    with pytest.raises(ValueError, match="record exceeds"):
        energy_readers.read_ascii_matsum(source)


@pytest.mark.parametrize("name", ["MAX_BYTES", "MAX_RECORD_CHARS", "MAX_ROWS"])
def test_matsum_resource_bounds(tmp_path, monkeypatch, name):
    from ls_prepost_mcp.domain.results import ascii_matsum

    monkeypatch.setattr(ascii_matsum, name, 1)
    result = extract(tmp_path)
    assert result["status"] == "failed" and not result["artifacts"]


def test_matsum_follows_allowed_roots(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = tmp_path / "matsum"
    source.write_text(TEXT)
    result = Service(Settings(allowed)).extract_database(str(source), "matsum", "kinetic_energy", "J")
    assert result["status"] == "failed" and "allowed roots" in result["error"]["message"]
