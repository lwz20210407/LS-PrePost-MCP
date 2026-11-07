"""Q06 SLEOUT keeps the three written interface-energy columns and caller units."""
import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service

COMPONENTS = [("side_a_energy", 0), ("side_b_energy", 1), ("frictional_energy", 2)]
FIRST = [(90, [1., -2., 3.]), (10, [-4., 5., -6.])]
SECOND = [(10, [-7., 8., -9.]), (90, [10., -11., 12.])]


def row(identity, values):
    return f"{identity:10d}" + "".join(f"{v:13.4E}" for v in values[:2]) + " "*26 + f"{values[2]:13.4E}\n"


def frame(time, cycle, rows, layout="slave"):
    left, right, summary_right = ("slave", "master", "mastr") if layout == "slave" else ("surfa", "surfb", "surfb")
    return (f" contact interface energy file, time= {time:.7E}\n"
            f"    # {left} {right} cycle= {cycle} frictional\n\n"
            + "".join(row(identity, values) for identity, values in rows)
            + f"\n summary   total {left} side= 1.0000000E+00\n"
            f"           total {summary_right} side= -2.0000000E+00\n"
            "           total energy    = -1.0000000E+00\n"
            "           friction energy = 3.0000000E+00\n")


def sample(layout="slave"):
    return ("Synthetic contact energy\nSolver version\n{BEGIN LEGEND}\n"
            " Entity # Title\n10 First title\n90 Other title\n{END LEGEND}\n\n"
            + frame(0, 1, FIRST, layout) + frame(2, 42, SECOND, layout))


def extract(tmp_path, text=None, component="side_a_energy", **options):
    source = tmp_path / "sleout"
    source.write_text(sample() if text is None else text, encoding="utf8")
    return Service(Settings(tmp_path)).extract_database(str(source), "sleout", component, "declared_energy",
                                                       time_units="declared_time", **options)


@pytest.mark.parametrize("layout", ["slave", "surfa"])
@pytest.mark.parametrize("component,index", COMPONENTS)
def test_named_sleout_components_preserve_ids_values_and_source_labels(tmp_path, layout, component, index):
    result = extract(tmp_path, sample(layout), component)
    assert result["status"] == "succeeded", result["error"]
    data = result["data"]
    assert result["backend"] == "ls-dyna-ascii"
    assert data["source_kind"] == "ascii" and data["source_format"] == "sleout"
    assert data["ids"] == [90, 10] and data["stored_columns"] == [0, 1]
    assert data["state_count"] == 2 and data["row_count"] == 4
    labels = ["slave", "master", "frictional"] if layout == "slave" else ["surfa", "surfb", "frictional"]
    assert data["source_column_names"] == {"time": ["time"], "id": ["#"], "value": [labels[index]]}
    assert data["units"] == "declared_energy" and data["time_units"] == "declared_time"
    assert data["entity_metadata"]["validity"] == "raw_unmasked"
    assert data["entity_metadata"]["deletion_validity"] == "unknown"
    assert data["entity_metadata"]["summary_exported"] is False
    with Path(result["artifacts"][0]["path"]).open(newline="", encoding="utf8") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ["time", "entity_id", component]
        written = [(float(r["time"]), int(r["entity_id"]), float(r[component])) for r in reader]
    assert written == [(0., 90, FIRST[0][1][index]), (0., 10, FIRST[1][1][index]),
                       (2., 90, SECOND[1][1][index]), (2., 10, SECOND[0][1][index])]


def test_selection_and_input_hash_are_recorded_without_inferred_units(tmp_path):
    result = extract(tmp_path, entity_ids=[10, 90])
    assert result["status"] == "succeeded", result["error"]
    data = result["data"]
    assert data["ids"] == [10, 90] and data["stored_columns"] == [1, 0]
    source = tmp_path / "sleout"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert data["source_sha256"] == digest
    job = json.loads(next(tmp_path.rglob("job.json")).read_text())
    assert job["inputs"] == [{"path": str(source), "sha256": digest}]


def test_source_mutation_returns_no_verified_artifact(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import ascii_sleout

    original = ascii_sleout.parse

    def changed(lines, component):
        data = original(lines, component)
        with (tmp_path / "sleout").open("a", encoding="utf8") as stream:
            stream.write("changed")
        return data

    monkeypatch.setattr(ascii_sleout, "parse", changed)
    result = extract(tmp_path)
    assert result["status"] == "failed" and not result["artifacts"]
    assert "changed" in result["error"]["message"]


@pytest.mark.parametrize("options", [{"branch": "interface"}, {"shard": "binout0000"},
                                     {"native_check": True}, {"native_check": "false"}, {"entity_ids": [999]}])
def test_unsupported_selection_and_native_modes_fail_explicitly(tmp_path, options):
    result = extract(tmp_path, **options)
    assert result["status"] == "failed" and not result["artifacts"]
    assert result["backend"] == "ls-dyna-ascii"
    if options.get("native_check") is True:
        assert "native_check currently supports" in result["error"]["message"]
        assert not list(tmp_path.rglob("job.json"))


def test_ascii_needs_no_lasso_and_does_not_read_siblings(tmp_path, monkeypatch):
    for name in [k for k in sys.modules if k == "lasso" or k.startswith("lasso.")]:
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setitem(sys.modules, "lasso", None)

    def forbidden(*args, **kwargs):
        pytest.fail("ASCII SLEOUT must not open a binary sibling or model")

    monkeypatch.setattr("ls_prepost_mcp.domain.results.lasso_backend.binout_curves", forbidden)
    (tmp_path / "binout").write_bytes(b"not a binary database")
    (tmp_path / "model.k").write_text("not a keyword deck")
    assert extract(tmp_path)["status"] == "succeeded"


@pytest.mark.parametrize("limit", ["MAX_BYTES", "MAX_RECORD_CHARS", "MAX_ROWS"])
def test_resource_budgets_fail_without_verified_artifact(tmp_path, monkeypatch, limit):
    from ls_prepost_mcp.domain.results import ascii_sleout

    monkeypatch.setattr(ascii_sleout, limit, 1)
    result = extract(tmp_path)
    assert result["status"] == "failed" and not result["artifacts"]


def test_growth_is_rejected_before_reading_extra_data(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import ascii_records, ascii_sleout

    original_validate, original_lines = ascii_sleout.validate_size, ascii_records.bounded_lines
    observed = dict(validations=0, chars=0)
    limit = len(sample().encode()) + 50
    monkeypatch.setattr(ascii_sleout, "MAX_BYTES", limit)

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

    monkeypatch.setattr(ascii_sleout, "validate_size", grows)
    monkeypatch.setattr(ascii_records, "bounded_lines", counted)
    result = extract(tmp_path)
    assert result["status"] == "failed" and not result["artifacts"]
    assert observed == dict(validations=2, chars=0)
