"""Q06 solver-text forces: synthetic layouts, no copied solver output or native process."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.service import Service


def contact(names=("slave", "master"), moments=True):
    rows = ["Synthetic model\n ls-dyna synthetic\n"]
    for t in (0, 2):
        for side, label in enumerate(names):
            value = (side + 1) * (t + 1)
            extra = f" mx {value + 10} my 0 mz 0" if moments else ""
            rows.append(f" {label} 7 time {t} x {value} y -2D+0 z 3 mass 4{extra}\n")
    return "".join(rows)


SECTION = """Synthetic section forces
 line#1  section#     time        x-force     y-force     z-force    magnitude
 line#2  resultant  moments       x-moment    y-moment    z-moment   magnitude
 line#3  centroids                x           y           z            area
 9 0.0 1 -2 3 4
ac ID = 123 5 6 7 8
 9 10 11 12

 9 2.0 2 -3 4 5
ac ID = 123 6 7 8 9
 10 11 12 13
"""


def extract(tmp_path, database, text, component="x_force", **kwargs):
    source = tmp_path / database
    source.write_text(text, encoding="utf-8")
    before = source.read_bytes()
    result = Service(Settings(tmp_path)).extract_database(str(source), database, component, "model_units", **kwargs)
    assert source.read_bytes() == before
    return JobResult.model_validate_json(json.dumps(result, allow_nan=False))


def rows(result):
    artifact = result.artifacts[0]
    assert hashlib.sha256(Path(artifact.path).read_bytes()).hexdigest() == artifact.sha256
    with open(artifact.path, newline="", encoding="utf-8") as stream:
        return list(csv.reader(stream))


@pytest.mark.parametrize("labels", [("slave", "master"), ("SURFA", "SURFB")])
def test_contact_preserves_both_stored_sides(tmp_path, labels):
    result = extract(tmp_path, "rcforc", contact(labels), entity_ids=[7])
    assert result.status == "succeeded", result.error
    assert result.backend == "ls-dyna-ascii"
    assert result.data["source_format"] == "rcforc"
    assert result.data["ids"] == [7, 7]
    assert result.data["column_key"] == ["entity_id", "side"]
    assert rows(result) == [["time", "entity_id", "side", "x_force"],
                            ["0.0", "7", "0", "1.0"], ["0.0", "7", "1", "2.0"],
                            ["2.0", "7", "0", "3.0"], ["2.0", "7", "1", "6.0"]]


def test_contact_fortran_and_optional_moment_components(tmp_path):
    force = extract(tmp_path, "rcforc", contact(), "y_force")
    assert force.status == "succeeded", force.error
    assert [float(r[-1]) for r in rows(force)[1:]] == [-2.0] * 4
    moment = extract(tmp_path, "rcforc", contact(), "x_moment")
    assert moment.status == "succeeded", moment.error
    assert [float(r[-1]) for r in rows(moment)[1:]] == [11, 12, 13, 16]


def test_one_stored_contact_side_keeps_side_column(tmp_path):
    result = extract(tmp_path, "rcforc", contact(("master",)), "x_force")
    assert result.status == "succeeded", result.error
    assert result.data["column_key"] == ["entity_id", "side"]
    assert [r[2] for r in rows(result)[1:]] == ["1", "1"]


@pytest.mark.parametrize("component,expected", [("x_force", [1, 2]), ("y_moment", [6, 7]),
                                               ("area", [12, 13])])
def test_section_three_line_records(tmp_path, component, expected):
    result = extract(tmp_path, "secforc", SECTION, component)
    assert result.status == "succeeded", result.error
    assert result.data["ids"] == [9] and result.data["state_count"] == 2
    assert result.data["entity_metadata"]["local_frame_reference"] == [{"id": 123, "prefixes": ["ac ID = 123"]}]
    assert [float(r[-1]) for r in rows(result)[1:]] == expected


def test_undefined_single_surface_contacts_warn_instead_of_zero_filling(tmp_path):
    text = "interface number, 99,is single surface-resultants are undefined\n" + contact()
    result = extract(tmp_path, "rcforc", text)
    assert result.status == "succeeded", result.error
    assert result.warnings and "99" in result.warnings[0]
    assert result.data["ids"] == [7, 7]


@pytest.mark.parametrize("database,text,component", [
    ("rcforc", contact().replace("x 1", "x NaN", 1), "x_force"),
    ("rcforc", contact() + "slave 7 time 2 x 3 y 0 z 0 mass 4\n", "x_force"),
    ("rcforc", contact().replace("master 7 time 2", "master 7 time 3"), "x_force"),
    ("rcforc", contact().replace("slave 7 time 0", "slave 0 time 0"), "x_force"),
    ("rcforc", contact().replace("x 1", "x 1 x 3", 1), "x_force"),
    ("rcforc", contact(moments=False), "x_moment"),
    ("rcforc", "interface number, 99,is single surface-resultants are undefined\n", "x_force"),
    ("secforc", SECTION.rsplit(" 10 11 12 13", 1)[0], "x_force"),
    ("secforc", SECTION.replace("ac ID = 123 6 7 8 9", "ac ID = 456 6 7 8 9"), "y_moment"),
    ("secforc", SECTION.replace("x-force", "unknown-force"), "x_force"),
    ("secforc", " title only\n", "x_force"),
])
def test_malformed_or_ambiguous_text_fails_without_verified_artifact(tmp_path, database, text, component):
    result = extract(tmp_path, database, text, component)
    assert result.status == "failed" and result.error["message"]
    assert not result.artifacts


@pytest.mark.parametrize("kwargs", [{"branch": "shell"}, {"shard": "binout0000"}])
def test_text_never_selects_binary_siblings(tmp_path, kwargs):
    (tmp_path / "binout0000").write_bytes(b"not a binout")
    result = extract(tmp_path, "rcforc", contact(), **kwargs)
    assert result.status == "failed" and not result.artifacts


def test_ascii_database_name_must_match_explicit_path(tmp_path):
    path = tmp_path / "secforc"
    path.write_text(SECTION, encoding="utf-8")
    result = Service(Settings(tmp_path)).extract_database(str(path), "rcforc", "x_force", "N")
    assert result["status"] == "failed" and not result["artifacts"]


def test_multiple_sections_keep_their_frame_references_and_stored_ids(tmp_path):
    other = SECTION[SECTION.index(" 9 0.0"):].replace(" 9 ", " 3 ").replace("ID = 123", "ID = 456")
    result = extract(tmp_path, "secforc", SECTION + other, "z_moment", entity_ids=[3, 9])
    assert result.status == "succeeded", result.error
    assert result.data["ids"] == [3, 9]
    # Metadata is explicitly aligned to stored columns; selection exposes that index mapping.
    assert result.data["stored_columns"] == [1, 0]
    assert [r["id"] for r in result.data["entity_metadata"]["local_frame_reference"]] == [123, 456]
    assert len(rows(result)) == 5


@pytest.mark.parametrize("limit", ["MAX_BYTES", "MAX_RECORD_CHARS", "MAX_RECORDS"])
def test_resource_bounds_fail_without_partial_verified_csv(tmp_path, monkeypatch, limit):
    from ls_prepost_mcp.domain.results import ascii_forces

    monkeypatch.setattr(ascii_forces, limit, 1)
    result = extract(tmp_path, "rcforc", contact())
    assert result.status == "failed" and result.backend == "ls-dyna-ascii"
    assert not result.artifacts


def test_ascii_symlink_cannot_read_outside_allowed_roots(tmp_path):
    workspace, outside = tmp_path / "ws", tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    target = outside / "rcforc"
    target.write_text(contact(), encoding="utf-8")
    try:
        (workspace / "rcforc").symlink_to(target)
    except OSError:
        pytest.skip("Symbolic links are unavailable on this host")
    result = Service(Settings(workspace)).extract_database(str(workspace / "rcforc"), "rcforc", "x_force", "N")
    assert result["status"] == "failed" and "allowed roots" in result["error"]["message"]
