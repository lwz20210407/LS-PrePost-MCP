"""Pure records: no pending I/O budget API, native process or nodal mathematics."""
import pytest

from ls_prepost_mcp.domain.results.ascii_nodout import parse
from tests.test_ascii_nodout_database import COMPONENTS, FIRST, SECOND, TEXT, TRANSLATION, row, table


@pytest.mark.parametrize("component,index,label", COMPONENTS)
def test_nine_components_keep_literal_node_identity_and_fields(component, index, label):
    result = parse(TEXT.splitlines(keepends=True), component)
    assert result["ids"] == [90, 10] and result["time"] == [0., 2.]
    assert result["values"] == [[FIRST[0][1][index], FIRST[1][1][index]],
                                 [SECOND[1][1][index], SECOND[0][1][index]]]
    assert result["source_column_names"]["value"] == [label]
    assert result["entity_metadata"]["rotation_tables_validated"] == 2
    assert result["entity_metadata"]["validity"] == "raw_unmasked"
    assert result["entity_metadata"]["deletion_validity"] == "unknown"
    assert not result["entity_metadata"]["alive_mask_available"]
    assert any("alive/deletion" in item for item in result["warnings"])


def test_translation_only_layout_and_no_coordinate_subtraction():
    result = parse(table(0, 0, "translation", FIRST).splitlines(True), "x_displacement")
    assert result["values"] == [[1., -11.]]
    assert result["entity_metadata"]["rotation_tables_validated"] == 0


@pytest.mark.parametrize("text,reason", [
    ("title only", "No NODOUT"),
    (TEXT.replace("x-disp", "x-unknown", 1), "header"),
    (TEXT.replace(TRANSLATION, TRANSLATION+" x-extra", 1), "header"),
    (TEXT.replace(TRANSLATION, "", 1), "header"),
    (TEXT.replace("( at time 2.0000000E+00 )", "( at time )", 1), "header"),
    (TEXT + "n o d a l p r i n t o u t f o r t i m e s t e p", "header"),
    (TEXT.replace("{END LEGEND}", "", 1), "legend"),
    (TEXT.replace("{BEGIN LEGEND}", "{BEGIN LEGEND}\n{BEGIN LEGEND}", 1), "legend"),
    (TEXT.replace(row(90, FIRST[0][1]), row(90, FIRST[0][1])[:-3]+"\n", 1), "row"),
    (TEXT.replace(row(90, FIRST[0][1]), row(90, FIRST[0][1])+row(90, FIRST[0][1]), 1), "Duplicate"),
    (TEXT.replace(row(90, FIRST[0][1]), row(0, FIRST[0][1]), 1), "positive"),
    (TEXT.replace(" 1.00000E+00", "         NaN", 1), "numeric"),
    (TEXT.replace(" 1.00000E+00", " 1.00000-345", 1), "underflows"),
    (TEXT.replace("at time 2.0000000E+00", "at time 0.0000000E+00"), "increasing"),
    (TEXT + table(3, 99, "translation", FIRST), "pairs"),
    (TEXT.replace(row(90, [2]*9), "", 1), "rotation"),
])
def test_malformed_known_layouts_never_return_a_partial_curve(text, reason):
    with pytest.raises(ValueError, match=reason):
        parse(text.splitlines(keepends=True), "x_displacement")


def test_finite_implicit_three_digit_exponent_is_not_an_arithmetic_expression():
    text = table(0, 1, "translation", FIRST).replace(" 1.00000E+00", " 1.00000+100", 1)
    assert parse(text.splitlines(True), "x_displacement")["values"][0][0] == 1e100


def test_plain_prose_titles_are_not_reserved_prefix_fields():
    result = parse(("Timeless\nNodal documentation\n" + TEXT).splitlines(True), "x_velocity")
    assert result["values"][0][0] == -4.


def test_total_row_budget_includes_ignored_rotation_tables(monkeypatch):
    from ls_prepost_mcp.domain.results import ascii_nodout

    monkeypatch.setattr(ascii_nodout, "MAX_ROWS", 3)
    with pytest.raises(ValueError, match="total table rows"):
        parse(TEXT.splitlines(True), "x_velocity")


@pytest.mark.parametrize("component", ["displacement_x", "x_coordinate", "x_rotation", "velocity", "1"])
def test_only_declared_nine_components_are_supported(component):
    with pytest.raises(ValueError, match="component"):
        parse(TEXT.splitlines(True), component)


@pytest.mark.parametrize("column", range(12))
@pytest.mark.parametrize("token", ["NaN", "Infinity", "1.00000-345", "", "bad"])
def test_every_stored_translation_column_needs_a_finite_present_value(column, token):
    original = row(90, FIRST[0][1])
    broken = original[:10+column*12] + f"{token:>12}" + original[22+column*12:]
    text = TEXT.replace(original, broken, 1)
    with pytest.raises(ValueError):
        parse(text.splitlines(True), "x_displacement")


@pytest.mark.parametrize("column", range(12))
def test_column_identity_cannot_be_reordered_even_for_an_unrequested_field(column):
    labels = TRANSLATION.split()[2:]
    labels[column] = "unknown-field"
    text = TEXT.replace(TRANSLATION, "nodal point " + " ".join(labels), 1)
    with pytest.raises(ValueError, match="column header"):
        parse(text.splitlines(True), "x_displacement")


@pytest.mark.parametrize("tail", ["{BEGIN LEGEND} extra", "{END LEGEND} extra",
                                  "n o d a l p r i n t o u t f o r t i m e s t e p 4 ( at time )"])
def test_known_control_markers_do_not_silently_hide_a_truncated_tail(tail):
    with pytest.raises(ValueError):
        parse((TEXT+tail).splitlines(True), "x_displacement")


def test_missing_last_rotation_header_is_not_a_translation_only_layout():
    text = TEXT[:TEXT.rfind("n o d a l")]
    with pytest.raises(ValueError, match="pairs"):
        parse(text.splitlines(True), "x_displacement")


def test_all_rotation_data_are_syntactically_checked_but_not_substituted_for_displacement():
    first_rotation = row(90, [0]*9)
    bad = first_rotation[:10] + "         NaN" + first_rotation[22:]
    with pytest.raises(ValueError):
        parse(TEXT.replace(first_rotation, bad, 1).splitlines(True), "x_displacement")


def test_translation_membership_cannot_shrink_without_unknown_samples():
    text = TEXT.replace(row(90, SECOND[1][1]), "", 1)
    with pytest.raises(ValueError, match="membership"):
        parse(text.splitlines(True), "x_displacement")
