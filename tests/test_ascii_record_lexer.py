"""Low-level text scanning exposes syntax without deciding numerical/block policy."""
import string

import pytest

from ls_prepost_mcp.domain.results.ascii_records import RecordTooLong, bounded_lines, tokenize_scalar


@pytest.mark.parametrize("line,label,value,suffix,width", [
    ("  kinetic energy........ 1D-3\n", "kinetic energy", "1D-3", "", 8),
    ("energy ratio w/o eroded energy. 1.0", "energy ratio w/o eroded energy", "1.0", "", 1),
    ("time per zone cycle.(nanosec).. 20", "time per zone cycle.(nanosec)", "20", "", 2),
    ("stonewall energy.... 3 wall# 1", "stonewall energy", "3", " wall# 1", 4),
    ("label.... NaN", "label", "NaN", "", 4),
    ("A. B", "A", "B", "", 1),
    ("label. dotted name.... .5", "label. dotted name", ".5", "", 4),
])
def test_raw_dotted_fields_and_suffixes_are_not_numeric_interpretations(line, label, value, suffix, width):
    field = tokenize_scalar(line)
    assert (field.raw_label, field.value_token, field.suffix) == (label, value, suffix)
    assert field.separator == "." and field.separator_width == width


@pytest.mark.parametrize("line,separator", [("time:0", ":"), ("time = 0", "="), ("time....0", ".")])
def test_caller_can_explicitly_preserve_legacy_separators(line, separator):
    allowed = frozenset(string.ascii_letters + string.digits + "_ /()#%-")
    assert tokenize_scalar(line) is None
    field = tokenize_scalar(line, separators=".:=", minimum_dots=2, require_dot_space=False,
                            label_characters=allowed)
    assert field.raw_label == "time" and field.value_token == "0" and field.separator == separator


def test_label_alphabet_is_a_caller_policy_and_does_not_leak_into_raw_labels():
    allowed = frozenset(string.ascii_letters + string.digits + "_ /()#%-")
    assert tokenize_scalar("label. dotted.... 1").raw_label == "label. dotted"
    assert tokenize_scalar("label. dotted.... 1", minimum_dots=2, label_characters=allowed) is None
    assert tokenize_scalar("A. B", minimum_dots=2, label_characters=allowed) is None


def test_missing_numeric_value_keeps_the_legacy_opaque_dot_token():
    allowed = frozenset(string.ascii_letters + string.digits + "_ /()#%-")
    assert tokenize_scalar("time.... ") is None
    field = tokenize_scalar("time.... ", minimum_dots=2, require_dot_space=False,
                            label_characters=allowed)
    assert field.value_token == "." and field.suffix == " "


def test_long_leaders_and_missing_values_have_bounded_linear_scanning():
    field = tokenize_scalar("label" + "." * 15_000 + " 1 wall# 2")
    assert field.separator_width == 15_000 and field.suffix == " wall# 2"
    assert tokenize_scalar("label" + "." * 15_000 + "   ") is None


def test_bounded_lines_retains_blank_lines_and_logical_newlines(tmp_path):
    source = tmp_path / "text"
    source.write_bytes(b"\xef\xbb\xbfa\r\n\r\n b \r\n")
    assert list(bounded_lines(source, max_record_chars=4, encoding="utf-8-sig", errors="strict")) == [
        "a\n", "\n", " b \n"]


def test_line_size_and_decoding_are_explicit_independent_policies(tmp_path):
    source = tmp_path / "text"
    source.write_bytes(b"\xff\n" + b"a\n" * 100)
    with pytest.raises(UnicodeDecodeError):
        list(bounded_lines(source, max_record_chars=2, encoding="utf-8-sig", errors="strict"))
    lines = list(bounded_lines(source, max_record_chars=2, encoding="utf-8-sig", errors="replace"))
    assert lines == ["\ufffd\n"] + ["a\n"] * 100  # No implicit total-file or UTF-8-strict policy.
    with pytest.raises(RecordTooLong):
        list(bounded_lines(source, max_record_chars=1, encoding="utf-8-sig", errors="replace"))
