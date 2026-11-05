"""Shared lexical work must not merge Q06 strict and Q12 nullable policies."""
import pytest

from ls_prepost_mcp.domain.results.ascii_glstat import read
from ls_prepost_mcp.domain.results.energy_readers import read_ascii_glstat


def block(t, kinetic, internal, total, wall=""):
    return (f"time.... {t}\ntime step.... .01\nkinetic energy.... {kinetic}\n"
            f"internal energy.... {internal}\ntotal energy.... {total}\n"
            f"hourglass energy.... .5\n{wall}time per zone cycle.(nanosec).. 0\n")


FULL = "Example A. B\nls-dyna synthetic\n" + block(0, 1, 10, 11) + block(1, 2, 11, 13)
SPARSE = "time.... 0\ninternal energy.... 10\nhourglass energy.... 1\ntime.... 1\ninternal energy.... 11\n"
WALL_ONE = "stonewall energy.... 3 wall# 1\nstonewall energy.... 5 wall# 2\n"
WALL_TWO = "stonewall energy.... 4 wall# 1\nstonewall energy.... 6 wall# 2\n"


@pytest.mark.parametrize("text", [FULL, FULL.replace("time per zone cycle.(nanosec).. 0\n", "time per zone cycle.(nanosec).. 0\nExample A. B\n")])
def test_full_records_keep_shared_values_and_punctuated_headings(tmp_path, text):
    path = tmp_path / "glstat"
    path.write_text(text)
    assert read(path, "kinetic_energy")["values"] == read_ascii_glstat(path)["kinetic_energy"] == [1., 2.]


def test_sparse_record_is_strict_failure_but_nullable_energy_data(tmp_path):
    path = tmp_path / "glstat"
    path.write_text(SPARSE)
    with pytest.raises(ValueError):
        read(path, "internal_energy")
    actual = read_ascii_glstat(path)
    assert actual["hourglass_energy"] == [1., None]
    assert actual["total_energy"] is None


@pytest.mark.parametrize("wall_second,expected", [(WALL_TWO, [8., 10.]), ("stonewall energy.... 4 wall# 1\n", [8., None])])
def test_nullable_wall_sets_and_missing_wall_samples_survive(tmp_path, wall_second, expected):
    path = tmp_path / "glstat"
    path.write_text(block(0, 1, 10, 11, WALL_ONE) + block(1, 2, 11, 13, wall_second))
    assert read_ascii_glstat(path)["stonewall_energy"] == expected
    with pytest.raises(ValueError):
        read(path, "kinetic_energy")


def test_explicit_wall_total_is_not_added_to_per_wall_details(tmp_path):
    path = tmp_path / "glstat"
    path.write_text(block(0, 1, 10, 11, "stonewall energy.... 20\n" + WALL_ONE))
    assert read_ascii_glstat(path)["stonewall_energy"] == [20.]


def test_repeated_wall_identity_still_fails(tmp_path):
    path = tmp_path / "glstat"
    path.write_text(block(0, 1, 10, 11, WALL_ONE + "stonewall energy.... 3 wall# 1\n"))
    with pytest.raises(ValueError, match="Duplicate glstat wall"):
        read_ascii_glstat(path)


def test_wall_identity_in_label_and_suffix_are_both_supported_by_q12(tmp_path):
    path = tmp_path / "glstat"
    path.write_text(block(0, 1, 10, 11, "wall# 1 energy.... 3\nwall# 2 energy.... 5\n"))
    assert read_ascii_glstat(path)["stonewall_energy"] == [8.]


@pytest.mark.parametrize("text", ["time:0\ninternal energy=10\n", "time....0\ninternal energy....10\n"])
def test_q12_keeps_legacy_separator_and_no_space_grammar(tmp_path, text):
    path = tmp_path / "glstat"
    path.write_text(text)
    assert read_ascii_glstat(path)["internal_energy"] == [10.]
    with pytest.raises(ValueError):
        read(path, "internal_energy")


def test_single_dot_policy_remains_explicit_per_reader(tmp_path):
    path = tmp_path / "glstat"
    path.write_text(FULL.replace("kinetic energy....", "kinetic energy."))
    assert read(path, "kinetic_energy")["values"] == [1., 2.]
    assert read_ascii_glstat(path)["kinetic_energy"] is None


def test_unknown_nonfinite_field_is_not_promoted_to_a_q12_measurement(tmp_path):
    path = tmp_path / "glstat"
    path.write_text(FULL.replace("internal energy.... 10", "unknown telemetry.... NaN\ninternal energy.... 10"))
    with pytest.raises(ValueError, match="Nonfinite"):
        read(path, "kinetic_energy")
    assert read_ascii_glstat(path)["internal_energy"] == [10., 11.]


def test_strict_decoding_is_not_forced_onto_nullable_reader(tmp_path):
    path = tmp_path / "glstat"
    path.write_bytes(b"title\xff\n" + FULL.encode())
    with pytest.raises(UnicodeDecodeError):
        read(path, "kinetic_energy")
    assert read_ascii_glstat(path)["kinetic_energy"] == [1., 2.]


def test_q06_file_limit_does_not_become_a_q12_policy(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.results import ascii_glstat

    path = tmp_path / "glstat"
    path.write_text(FULL)
    monkeypatch.setattr(ascii_glstat, "MAX_BYTES", 1)
    with pytest.raises(ValueError, match="256 MiB"):
        read(path, "kinetic_energy")
    assert read_ascii_glstat(path)["kinetic_energy"] == [1., 2.]


def test_missing_numeric_value_does_not_silently_become_a_q12_null_field(tmp_path):
    path = tmp_path / "glstat"
    path.write_text(SPARSE + "time....\n")
    with pytest.raises(ValueError, match="Invalid numeric"):
        read_ascii_glstat(path)
