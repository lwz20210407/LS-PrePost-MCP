"""Q06 NODOUT named components keep the printed node and field identities."""
import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service

TRANSLATION = "nodal point x-disp y-disp z-disp x-vel y-vel z-vel x-accl y-accl z-accl x-coor y-coor z-coor"
ROTATION = "nodal point x-rot y-rot z-rot x-rot vel y-rot vel z-rot vel x-rot acc y-rot acc z-rot acc"
COMPONENTS = [(f"{axis}_{quantity}", offset+i, f"{axis}-{raw}")
              for quantity, offset, raw in [("displacement", 0, "disp"), ("velocity", 3, "vel"),
                                             ("acceleration", 6, "accl")]
              for i, axis in enumerate("xyz")]


def row(node, values):
    return f"{node:10d}" + "".join(f"{value:12.5E}" for value in values) + "\n"


def table(time, step, kind, rows):
    return (f"n o d a l   p r i n t   o u t   f o r   t i m e  s t e p {step:7d} ( at time {time:.7E} )\n"
            + (TRANSLATION if kind == "translation" else ROTATION) + "\n"
            + "".join(row(node, values) for node, values in rows))


FIRST = [(90, [1, -2, 3, -4, 5, -6, 7, -8, 9, 101, 102, 103]),
         (10, [-11, 12, -13, 14, -15, 16, -17, 18, -19, 201, 202, 203])]
SECOND = [(10, [-21, 22, -23, 24, -25, 26, -27, 28, -29, 301, 302, 303]),
          (90, [31, -32, 33, -34, 35, -36, 37, -38, 39, 401, 402, 403])]
TEXT = ("Synthetic nodal result\nSolver version\n{BEGIN LEGEND}\n90\n10\n{END LEGEND}\n"
        + table(0, 1, "translation", FIRST) + table(0, 1, "rotation", [(90, [0]*9), (10, [0]*9)])
        + table(2, 42, "translation", SECOND) + table(2, 42, "rotation", [(10, [1]*9), (90, [2]*9)]))


@pytest.mark.parametrize("component,index,label", COMPONENTS)
def test_named_nodout_components_are_literal_translation_fields(tmp_path, component, index, label):
    source = tmp_path / "nodout"
    source.write_text(TEXT, encoding="utf8")
    result = Service(Settings(tmp_path)).extract_database(str(source), "nodout", component, "source_units",
                                                         time_units="source_time")
    assert result["status"] == "succeeded", result["error"]
    data = result["data"]
    assert result["backend"] == "ls-dyna-ascii"
    assert data["source_kind"] == "ascii" and data["source_format"] == "nodout"
    assert data["ids"] == [90, 10] and data["stored_columns"] == [0, 1]
    assert data["state_count"] == 2 and data["row_count"] == 4
    assert data["source_column_names"]["value"] == [label]
    with Path(result["artifacts"][0]["path"]).open(newline="", encoding="utf8") as stream:
        exported = list(csv.DictReader(stream))
    assert [float(r[component]) for r in exported] == [FIRST[0][1][index], FIRST[1][1][index],
                                                     SECOND[1][1][index], SECOND[0][1][index]]


def extract(tmp_path, text=TEXT, **options):
    source = tmp_path / "nodout"
    source.write_text(text, encoding="utf8")
    return Service(Settings(tmp_path)).extract_database(str(source), "nodout", "z_displacement", "model_length",
                                                       time_units="model_time", **options)


def test_nodout_selection_and_units_do_not_change_identity_or_values(tmp_path):
    result = extract(tmp_path, entity_ids=[10, 90])
    assert result["status"] == "succeeded", result["error"]
    data = result["data"]
    assert data["ids"] == [10, 90] and data["stored_columns"] == [1, 0]
    assert data["units"] == "model_length" and data["time_units"] == "model_time"
    assert data["entity_metadata"]["deletion_validity"] == "unknown"
    assert any("raw/unmasked" in w for w in result["warnings"])


def test_nodout_hash_is_bound_to_runtime_input(tmp_path):
    result = extract(tmp_path)
    assert result["status"] == "succeeded", result["error"]
    source = tmp_path / "nodout"
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    assert result["data"]["source_sha256"] == expected
    job = json.loads(next(tmp_path.rglob("job.json")).read_text())
    assert job["inputs"] == [{"path": str(source), "sha256": expected}]


def test_nodout_source_mutation_during_parse_returns_no_verified_artifact(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import ascii_nodout

    original = ascii_nodout.parse

    def changed(lines, component):
        data = original(lines, component)
        with (tmp_path / "nodout").open("a", encoding="utf8") as stream:
            stream.write("changed")
        return data

    monkeypatch.setattr(ascii_nodout, "parse", changed)
    result = extract(tmp_path)
    assert result["status"] == "failed" and not result["artifacts"]
    assert "changed" in result["error"]["message"]


@pytest.mark.parametrize("options", [{"branch": "node"}, {"shard": "binout0000"},
                                     {"native_check": True}, {"native_check": "false"}, {"entity_ids": [999]}])
def test_nodout_rejects_inapplicable_selection_and_native_modes(tmp_path, options):
    result = extract(tmp_path, **options)
    assert result["status"] == "failed" and not result["artifacts"]
    assert result["backend"] == "ls-dyna-ascii"


def test_nodout_needs_no_optional_lasso_and_never_substitutes_a_binary_sibling(tmp_path, monkeypatch):
    for name in [k for k in sys.modules if k == "lasso" or k.startswith("lasso.")]:
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setitem(sys.modules, "lasso", None)

    def forbidden(*args, **kwargs):
        pytest.fail("ASCII NODOUT must not read a binary sibling")

    monkeypatch.setattr("ls_prepost_mcp.domain.results.lasso_backend.binout_curves", forbidden)
    (tmp_path / "binout").write_bytes(b"not a native database")
    assert extract(tmp_path)["status"] == "succeeded"


@pytest.mark.parametrize("limit", ["MAX_BYTES", "MAX_RECORD_CHARS", "MAX_ROWS"])
def test_nodout_resource_budgets(tmp_path, monkeypatch, limit):
    from ls_prepost_mcp.domain.results import ascii_nodout

    monkeypatch.setattr(ascii_nodout, limit, 1)
    result = extract(tmp_path)
    assert result["status"] == "failed" and not result["artifacts"]


def test_nodout_growth_is_rejected_before_following_extra_data(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import ascii_nodout, ascii_records

    original_validate = ascii_nodout.validate_size
    original_lines = ascii_records.bounded_lines
    observed = dict(validations=0, read_chars=0)
    limit = len(TEXT.encode()) + 50
    monkeypatch.setattr(ascii_nodout, "MAX_BYTES", limit)

    def grows(path):
        original_validate(path)
        observed["validations"] += 1
        if observed["validations"] == 2:
            with Path(path).open("a", encoding="utf8") as stream:
                stream.write("\n" * limit)

    def counted(*args, **kwargs):
        for line in original_lines(*args, **kwargs):
            observed["read_chars"] += len(line)
            yield line

    monkeypatch.setattr(ascii_nodout, "validate_size", grows)
    monkeypatch.setattr(ascii_records, "bounded_lines", counted)
    result = extract(tmp_path)
    assert result["status"] == "failed" and not result["artifacts"]
    assert observed["read_chars"] == 0
    assert observed["validations"] == 2


@pytest.mark.parametrize("bad_row", [row(-1, FIRST[0][1]), f"{1:10d}"+"         NaN"+f"{2.:12.5E}"*11+"\n"])
def test_semantically_bad_orphan_rows_cannot_be_dropped_before_a_good_frame(tmp_path, bad_row):
    result = extract(tmp_path, bad_row+TEXT)
    assert result["status"] == "failed" and not result["artifacts"]
    assert "outside an active time block" in result["error"]["message"]
