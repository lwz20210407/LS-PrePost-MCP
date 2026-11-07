"""SPCFORC literal vectors: independent signed force/moment examples and hard boundaries."""
import math
import sys

import pytest

from ls_prepost_mcp.domain.results import ascii_spcforc as reader
from ls_prepost_mcp.domain.results.lasso_backend import ResultsError

TEXT = """Synthetic SPC vector example
ls-dyna test version
single point constraint forces
{BEGIN LEGEND}
90 printed title
10 printed title
{END LEGEND}
output at time = 0.0D+00
node= 00090 local x,y,z forces = 1 -2 3 setid= 0007
node= 10 local x,y,z moments= -40 50 -60 setid= 0
node= 00090 local x,y,z moments= 4 -5 6 setid= 7
node= 10 local x,y,z forces = -10 20 -30 setid= 00
force resultants = 999 -888 777
output at time = 2
node= 10 local x,y,z forces = 0 -21 31 setid= 0
node= 10 local x,y,z moments= 41 -51 61 setid= 0
node= 90 local x,y,z moments= -7 8 -9 setid= 7
node= 90 local x,y,z forces = -0.0 11 -12 setid= 7
force resultants = 0 0 0
"""
EXPECTED = {
    "x_force": [[1, -10], [-0.0, 0]], "y_force": [[-2, 20], [11, -21]],
    "z_force": [[3, -30], [-12, 31]], "x_moment": [[4, -40], [-7, 41]],
    "y_moment": [[-5, 50], [8, -51]], "z_moment": [[6, -60], [-9, 61]],
}
FORCE_ONLY = "\n".join(line for line in TEXT.splitlines() if "moments=" not in line) + "\n"


@pytest.mark.parametrize("component", list(EXPECTED))
def test_six_literal_components_have_independent_signed_oracles(component):
    data = reader.parse(TEXT.splitlines(), component)
    assert data["time"] == [0, 2] and data["ids"] == [90, 10]
    assert data["values"] == EXPECTED[component]
    assert data["source_kind"] == "ascii" and data["source_format"] == "spcforc"
    assert data["backend"] == "ls-dyna-ascii" and data["shards"] == []
    assert data["repeated_times_dropped"] == 0
    if component == "x_force":
        assert math.copysign(1, data["values"][1][0]) == -1


def test_raw_identity_kind_and_local_frame_are_not_coordinate_or_ui_claims():
    data = reader.parse(TEXT.splitlines(), "y_moment")
    meta = data["entity_metadata"]
    assert meta["raw_node_id_tokens"] == [["00090", "90"], ["10"]]
    assert meta["setid"] == [7, 0] and meta["raw_setid_tokens"] == [["0007", "7"], ["0", "00"]]
    assert meta["record_kind"] == "moments" and meta["component_index"] == 1
    assert meta["component_axis"] == "y" and meta["column_order"] == "first force table"
    assert meta["frame"] == "local as printed; basis unidentified; no transform"
    assert "coordinate_system_ids" not in meta and "global" not in meta["frame"]
    assert meta["deletion_validity"] == "unknown" and not meta["alive_mask_available"]
    assert meta["summary_records_validated"] == 2 and not meta["summary_exported"]
    assert meta["node_vector_rows_validated"] == 8 and meta["moment_records_available"] is True
    assert "no conservation" in meta["summary_validation"]
    assert data["source_column_names"] == dict(time=["output at time"], id=["node="], setid=["setid="],
                                                value=["local x,y,z moments"])


@pytest.mark.parametrize("component", ["x_force", "y_force", "z_force"])
def test_force_only_frames_are_complete_and_do_not_require_moments(component):
    data = reader.parse(FORCE_ONLY.splitlines(), component)
    assert data["values"] == EXPECTED[component]
    assert data["entity_metadata"]["moment_records_available"] is False


@pytest.mark.parametrize("component", ["x_moment", "y_moment", "z_moment"])
def test_force_only_moment_requests_fail_rather_than_invent_zero(component):
    with pytest.raises(ResultsError, match="not stored; missing values are unknown"):
        reader.parse(FORCE_ONLY.splitlines(), component)


@pytest.mark.parametrize("token", ["0", "-0", "0.0000E-999", "-0.0d+999", "5e-324", "-5E-324",
                                   "1.7976931348623157e308", ".125D+2"])
def test_supported_float64_literals_preserve_written_values(token):
    text = TEXT.replace("forces = 1 -2 3", f"forces = {token} -2 3")
    value = reader.parse(text.splitlines(), "x_force")["values"][0][0]
    assert value == float(token.replace("D", "E").replace("d", "e"))


@pytest.mark.parametrize("token", ["nan", "NaN", "inf", "Infinity", "1e309", "-1D309", "1e-999",
                                   "-1D-999", "2e-324", "1e", "1.0-03", "1,0", "***", "1_0",
                                   "+", "0 .1", "1E -3", "１", "1e−3"])
@pytest.mark.parametrize("place", ["force", "moment", "time", "summary"])
def test_all_fields_are_validated_even_when_requesting_another_component(token, place):
    needle = {"force": "forces = 1 -2 3", "moment": "moments= 4 -5 6",
              "time": "time = 0.0D+00", "summary": "resultants = 999 -888 777"}[place]
    replacement = {"force": f"forces = {token} -2 3", "moment": f"moments= {token} -5 6",
                   "time": f"time = {token}", "summary": f"resultants = {token} -888 777"}[place]
    with pytest.raises(ResultsError):
        reader.parse(TEXT.replace(needle, replacement).splitlines(), "z_force")


@pytest.mark.parametrize("old,new", [
    ("output at time = 2", "output at time = 0"),
    ("output at time = 2", "output at time = -1"),
    ("output at time = 2", "output at time 2"),
    ("output at time = 2", "output at time = 2 trailing"),
    ("node= 90 local x,y,z forces", "node= 91 local x,y,z forces"),
    ("node= 00090 local x,y,z moments= 4 -5 6 setid= 7\n", ""),
    ("node= 90 local x,y,z moments= -7 8 -9 setid= 7\n", ""),
    ("node= 10 local x,y,z forces = -10 20 -30 setid= 00\n", ""),
    ("force resultants = 999 -888 777\n", ""),
    ("force resultants = 0 0 0\n", ""),
    ("force resultants = 0 0 0", "force resultants = 0 0"),
    ("force resultants = 0 0 0", "force resultants = 0 0 0 0"),
    ("force resultants = 0 0 0", "force resultants = 0 0 0\nforce resultants = 0 0 0"),
    ("forces = 1 -2 3 setid= 0007", "forces = 1 -2 setid= 0007"),
    ("forces = 1 -2 3 setid= 0007", "forces = 1 -2 3 4 setid= 0007"),
    ("forces = 1 -2 3 setid= 0007", "forces = 1 -2 3 setid= 0007 extra"),
    ("node= 00090", "node= 0"), ("node= 00090", "node= -90"),
    ("node= 00090", "node= 9 0"), ("setid= 0007", "setid= -7"),
    ("setid= 0007", "setid= 8"), ("setid= 0007", "setid= 7 0"),
    ("node= 90 local x,y,z forces = -0.0 11 -12 setid= 7", "node= 90 local x,y,z forces = -0.0 11 -12 setid= 8"),
    ("local x,y,z", "global x,y,z"), ("forces = 1 -2 3", "force = 1 -2 3"),
    ("node= 00090 local x,y,z forces = 1 -2 3 setid= 0007",
     "node= 00090 local x,y,z forces = 1 -2 3 setid= 0007\nnode= 90 local x,y,z forces = 4 5 6 setid= 7"),
    ("force resultants = 0 0 0", "force resultants = 0 0 0\nnode= 90 local x,y,z forces = 4 5 6 setid= 7"),
    ("force resultants = 999 -888 777", "force resultants = 999 -888 777\nunknown footer"),
    ("{END LEGEND}", ""), ("{BEGIN LEGEND}", "{BEGIN LEGEND}\n{BEGIN LEGEND}"),
    ("{BEGIN LEGEND}", "x{BEGIN LEGEND}"),
])
def test_malformed_incomplete_ambiguous_and_changing_frames_fail(old, new):
    text = TEXT.replace(old, new)
    with pytest.raises(ResultsError):
        reader.parse(text.splitlines(), "x_force")


@pytest.mark.parametrize("frame", [0, 1])
def test_moment_mode_cannot_change_in_either_direction(frame):
    lines = TEXT.splitlines()
    marker = lines.index("output at time = 2")
    text = [line for index, line in enumerate(lines)
            if "moments=" not in line or (index >= marker if frame == 0 else index < marker)]
    with pytest.raises(ResultsError, match="record mode changes"):
        reader.parse(text, "x_force")


@pytest.mark.parametrize("prefix", ["node= 1 local x,y,z forces = 1 2 3 setid= 0\n",
                                    "force resultants = 1 2 3\n", "1 2 3\n", "-1 model title\n",
                                    "0\n", ".5\n", "NaN\n", "bad 1 2 3\n", "***\n", "１２ model title\n",
                                    "local x,y,z forces= 1 2 3 setid= 0\n", "setid= 1\n"])
def test_orphan_and_numeric_leading_preamble_is_not_silently_dropped(prefix):
    with pytest.raises(ResultsError, match="outside an active time block"):
        reader.parse((prefix + TEXT).splitlines(), "x_force")


@pytest.mark.parametrize("text", ["", "header only", "{BEGIN LEGEND}\nnode= 1", "{END LEGEND}",
                                  TEXT + "{BEGIN LEGEND}\nignored\n{END LEGEND}",
                                  "output at time = 0\nforce resultants = 0 0 0\n"])
def test_empty_unclosed_and_misplaced_records_fail(text):
    with pytest.raises(ResultsError):
        reader.parse(text.splitlines(), "x_force")


@pytest.mark.parametrize("component", ["force", "x", "x_force_global", "force_magnitude", "mass", "", None])
def test_unmapped_components_fail(component):
    with pytest.raises(ResultsError, match="component must be"):
        reader.parse(TEXT.splitlines(), component)


@pytest.mark.parametrize("limit", ["MAX_BYTES", "MAX_RECORD_CHARS", "MAX_ROWS"])
def test_resource_limits(tmp_path, monkeypatch, limit):
    source = tmp_path / "spcforc"
    source.write_text(TEXT, encoding="utf8")
    monkeypatch.setattr(reader, limit, 1)
    with pytest.raises(ResultsError, match="exceeds"):
        reader.read(source, "x_force")


def test_source_growth_is_checked_on_the_open_descriptor_before_parsing(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import ascii_records

    source = tmp_path / "spcforc"
    source.write_text(TEXT, encoding="utf8")
    limit = source.stat().st_size + 50
    monkeypatch.setattr(reader, "MAX_BYTES", limit)
    original = ascii_records.bounded_lines

    def grows(*args, **kwargs):
        with source.open("a", encoding="utf8") as stream:
            stream.write("\n" * limit)
        yield from original(*args, **kwargs)

    monkeypatch.setattr(ascii_records, "bounded_lines", grows)
    with pytest.raises(ResultsError, match="while reading"):
        reader.read(source, "x_force")


def test_bom_crlf_and_no_optional_lasso_read(tmp_path, monkeypatch):
    for name in [k for k in sys.modules if k == "lasso" or k.startswith("lasso.")]:
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setitem(sys.modules, "lasso", None)
    source = tmp_path / "spcforc"
    source.write_bytes(b"\xef\xbb\xbf" + TEXT.replace("\n", "\r\n").encode())
    assert reader.read(source, "z_moment")["values"] == EXPECTED["z_moment"]


def test_invalid_utf8_is_not_replaced(tmp_path):
    source = tmp_path / "spcforc"
    source.write_bytes(TEXT.encode() + b"\xff")
    with pytest.raises(UnicodeDecodeError):
        reader.read(source, "x_force")


@pytest.mark.parametrize("component", list(EXPECTED))
def test_independent_decimal_token_oracle_has_nonzero_moment_expectations(tmp_path, component):
    from tools.verify_ascii_spcforc_corpus import literal_reference

    source = tmp_path / "spcforc"
    source.write_text(TEXT, encoding="utf8")
    reference = literal_reference(source)
    assert reference["times"] == [0, 2] and reference["ids"] == [90, 10]
    assert reference["setid"] == [7, 0] and reference["moments"] is True
    kind, axis = component.split("_")[1] + "s", "xyz".index(component[0])
    assert [[frame[kind][node][axis] for node in [90, 10]] for frame in reference["frames"]] == EXPECTED[component]


@pytest.mark.parametrize("token", ["1e-999", "NaN", "1e309"])
def test_independent_decimal_oracle_rejects_unrepresentable_source_scalars(tmp_path, token):
    from tools.verify_ascii_spcforc_corpus import literal_reference

    source = tmp_path / "spcforc"
    source.write_text(TEXT.replace("forces = 1 -2 3", f"forces = {token} -2 3"), encoding="utf8")
    with pytest.raises(AssertionError):
        literal_reference(source)
