"""Pure SLEOUT records: complete frames, literal IDs and finite stored fields."""
import pytest

from ls_prepost_mcp.domain.results.ascii_sleout import parse
from tests.test_ascii_sleout_database import COMPONENTS, FIRST, SECOND, frame, row, sample


@pytest.mark.parametrize("layout", ["slave", "surfa"])
@pytest.mark.parametrize("component,index", COMPONENTS)
def test_aliases_select_written_positions_without_side_or_total_arithmetic(layout, component, index):
    result = parse(sample(layout).splitlines(True), component)
    assert result["time"] == [0., 2.] and result["ids"] == [90, 10]
    assert result["values"] == [[FIRST[0][1][index], FIRST[1][1][index]],
                                [SECOND[1][1][index], SECOND[0][1][index]]]
    metadata = result["entity_metadata"]
    assert metadata["summary_records_validated"] == 8 and not metadata["summary_exported"]
    assert metadata["validity"] == "raw_unmasked" and metadata["deletion_validity"] == "unknown"
    assert not metadata["alive_mask_available"] and "side" not in metadata
    assert "raw interface" in metadata["id_source"]


@pytest.mark.parametrize("text,reason", [
    ("title only", "No supported"),
    (sample().replace("time= 0.0000000E+00", "time="), "time header"),
    (sample() + "contact interface energy file, time=", "time header"),
    (sample().replace("# slave master cycle= 1 frictional", "# slave cycle= 1 frictional"), "header"),
    (sample().replace("master cycle=", "surfb cycle=", 1), "header"),
    (sample().replace("cycle= 1", "cycle= bad", 1), "header"),
    (sample().replace("# slave master cycle= 1 frictional", ""), "header"),
    (sample().replace("# slave master cycle= 1 frictional", "# slave master cycle= 1 frictional extra"), "header"),
    (sample().replace(row(90, FIRST[0][1]), row(90, FIRST[0][1])*2, 1), "Duplicate"),
    (sample().replace(row(90, FIRST[0][1]), row(0, FIRST[0][1]), 1), "positive"),
    (sample().replace(row(10, SECOND[0][1]), row(20, SECOND[0][1]), 1), "membership"),
    (sample().replace(row(90, FIRST[0][1]), "90 1 2\n", 1), "row"),
    (sample().replace(row(90, FIRST[0][1]), "90 1 2 3 4\n", 1), "row"),
    (sample().replace("time= 2.0000000E+00", "time= 0.0000000E+00"), "increasing"),
    (sample().replace("time= 2.0000000E+00", "time= -1.0000000E+00"), "increasing"),
    (sample().replace("{END LEGEND}", "", 1), "legend"),
    (sample().replace("{BEGIN LEGEND}", "{BEGIN LEGEND}\n{BEGIN LEGEND}", 1), "legend"),
    (sample() + "{BEGIN LEGEND}\n", "legend"),
    (sample() + "{END LEGEND} extra\n", "legend"),
    (sample() + "unrecognized trailing record", "summary"),
])
def test_malformed_inputs_do_not_return_partial_curves(text, reason):
    with pytest.raises(ValueError, match=reason):
        parse(text.splitlines(True), "side_a_energy")


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("layout", ["slave", "surfa"])
def test_each_summary_record_is_required_and_ordered(index, layout):
    lines = frame(0, 1, FIRST, layout).splitlines(True)
    beginning = next(i for i, line in enumerate(lines) if line.strip().startswith("summary"))
    missing = lines[:beginning+index] + lines[beginning+index+1:]
    with pytest.raises(ValueError, match="summary"):
        parse(missing, "side_a_energy")
    truncated = lines[:beginning+index]
    with pytest.raises(ValueError, match="summary"):
        parse(truncated, "side_a_energy")


@pytest.mark.parametrize("column", range(3))
@pytest.mark.parametrize("token", ["NaN", "Infinity", "1e309", "1e-999", "-1D-999", "bad", "***"])
def test_every_energy_field_is_validated_even_when_not_requested(column, token):
    fields = ["90", "1", "-2", "3"]
    fields[column+1] = token
    text = sample().replace(row(90, FIRST[0][1]), " ".join(fields)+"\n", 1)
    with pytest.raises(ValueError, match="numeric|underflows"):
        parse(text.splitlines(True), "side_a_energy")


@pytest.mark.parametrize("token", ["NaN", "1e309", "1e-999", "1 E-3"])
def test_time_is_a_single_finite_representable_scalar(token):
    text = sample().replace("time= 0.0000000E+00", "time= "+token)
    with pytest.raises(ValueError):
        parse(text.splitlines(True), "side_a_energy")


@pytest.mark.parametrize("index", range(4))
def test_summary_numbers_are_checked_without_using_their_values(index):
    lines = frame(0, 1, FIRST).splitlines(True)
    beginning = next(i for i, line in enumerate(lines) if line.strip().startswith("summary"))
    label = lines[beginning+index].split("=")[0]
    lines[beginning+index] = label + "= 1e-999\n"
    with pytest.raises(ValueError, match="underflows"):
        parse(lines, "side_a_energy")


def test_summary_values_are_not_used_to_rewrite_or_validate_stored_energies():
    text = frame(0, 1, FIRST).replace("total energy    = -1.0000000E+00", "total energy = 999D+12")
    result = parse(text.splitlines(True), "side_a_energy")
    assert result["values"] == [[1., -4.]]
    assert "summary" not in result and "energy_balance" not in result


def test_zero_with_large_exponent_is_zero_and_fortran_d_exponents_are_literal():
    text = frame(0, 0, FIRST).replace("1.0000E+00", "1.0000D+00", 1)
    text = text.replace("3.0000E+00", "-0.0000D-999", 1)
    assert parse(text.splitlines(True), "frictional_energy")["values"] == [[-0., -6.]]


def test_original_label_spelling_and_layout_variants_are_retained():
    text = frame(0, 1, FIRST).replace("slave master", "SLAVE MASTER") + frame(2, 2, SECOND, "surfa")
    assert parse(text.splitlines(True), "side_a_energy")["source_column_names"]["value"] == ["SLAVE", "surfa"]


@pytest.mark.parametrize("prefix", [row(90, [1, 2, 3]), row(-1, [1, 2, 3]),
                                   " NaN 1 2 3\n", "summary total slave side= 0\n"])
def test_orphan_table_syntax_cannot_be_dropped_as_preamble(prefix):
    with pytest.raises(ValueError, match="outside an active time block"):
        parse((prefix+sample()).splitlines(True), "side_a_energy")


@pytest.mark.parametrize("prefix", ["71 1.0 2.0\n", "71 1.0 2.0 3.0 4.0\n", "71\n"])
def test_incomplete_or_extra_orphan_numeric_records_are_not_titles(prefix):
    with pytest.raises(ValueError, match="outside an active time block"):
        parse((prefix+frame(0, 1, FIRST)).splitlines(True), "side_a_energy")


@pytest.mark.parametrize("prefix", [".5\n", " .5\n"])
def test_decimal_orphan_numeric_records_are_not_titles(prefix):
    with pytest.raises(ValueError, match="outside an active time block"):
        parse((prefix+frame(0, 1, FIRST)).splitlines(True), "side_a_energy")


def test_dot_prefixed_prose_is_still_supported_preamble():
    result = parse((".model title\n"+frame(0, 1, FIRST)).splitlines(True), "side_a_energy")
    assert result["values"] == [[1., -4.]]


@pytest.mark.parametrize("component", ["slave", "master", "total_energy", "frictional", "1"])
def test_only_the_three_declared_aliases_are_exported(component):
    with pytest.raises(ValueError, match="component"):
        parse(sample().splitlines(True), component)
