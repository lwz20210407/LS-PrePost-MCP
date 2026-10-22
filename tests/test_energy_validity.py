"""Q12 counterexamples: missing measurements are never zero or evidence of conservation."""
import json

import numpy as np
import pytest

from ls_prepost_mcp.domain.results.energy import calculate_energy_balance
from ls_prepost_mcp.domain.results.energy_readers import read_ascii_glstat, read_ascii_matsum


def histories(scale=1.):
    return {"time": [0., 1.], "total_energy": np.array([100., 50.]) * scale,
            "internal_energy": np.array([100., 50.]) * scale,
            "kinetic_energy": [0., 0.], "hourglass_energy": [0., 0.], "external_work": [0., 0.]}


@pytest.mark.parametrize("scale", [1., 1e-3, 1e-6, 1e6])
def test_balance_verdict_and_relative_residual_are_unit_invariant(scale):
    summary = calculate_energy_balance(histories(scale), units="declared", residual_ratio_limit=.01)["summary"]
    assert summary["verdict"] == "exceeded"
    assert summary["passed"] is False
    assert summary["balance_residual"]["max_relative_residual"] == pytest.approx(.5)


@pytest.mark.parametrize("missing", ["total_energy", "external_work"])
def test_missing_balance_input_is_not_synthesized_or_certified(missing):
    data = histories()
    data[missing] = None
    summary = calculate_energy_balance(data, residual_ratio_limit=.01)["summary"]
    assert summary["verdict"] == "incomplete"
    assert summary["passed"] is None
    assert summary["balance_residual"]["max_relative_residual"] is None
    assert any(missing in warning for warning in summary["warnings"])


def test_missing_hourglass_stays_null_in_budget_and_csv_rows():
    data = histories()
    data["hourglass_energy"] = None
    report = calculate_energy_balance(data, hourglass_ratio_limit=.05)
    assert report["summary"]["energy_budget"]["peak_hourglass_energy"] is None
    assert all(row[4] is None for row in report["series_rows"])
    assert report["summary"]["verdict"] == "incomplete"


def test_no_thresholds_report_numbers_without_pass_fail_conclusion():
    summary = calculate_energy_balance(histories())["summary"]
    assert summary["passed"] is None
    assert summary["verdict"] == "metrics_only_no_thresholds"


def test_time_reversal_is_incomplete_not_an_exceedance():
    data = histories()
    data["time"] = [1., 0.]
    data["total_energy"] = [100., 100.]
    summary = calculate_energy_balance(data, residual_ratio_limit=.01)["summary"]
    assert summary["verdict"] == "incomplete"
    assert summary["passed"] is None


def test_missing_hourglass_in_one_ascii_block_is_not_zero(tmp_path):
    source = tmp_path / "glstat"
    source.write_text("time.... 0\ninternal energy.... 100\nhourglass energy.... 1\n"
                      "time.... 1\ninternal energy.... 100\n", encoding="ascii")
    data = read_ascii_glstat(source)
    assert data["hourglass_energy"] == [1., None]
    summary = calculate_energy_balance(data, hourglass_ratio_limit=.05)["summary"]
    assert summary["verdict"] == "incomplete"


def test_numeric_table_is_not_a_glstat_database(tmp_path):
    source = tmp_path / "energies.txt"
    source.write_text("0 1 2 3 4 5 6 7\n1 1 2 3 4 5 6 7\n", encoding="ascii")
    with pytest.raises(ValueError, match="glstat"):
        read_ascii_glstat(source)


def test_matsum_continuations_and_missing_values_preserve_real_part_ids(tmp_path):
    source = tmp_path / "matsum"
    source.write_text("time = 0\nmat.#= 10 inten= 100 kinen= 2\nhgeng= 20\n"
                      "mat.#= 90 inten= 200\nhgeng= 10\n"
                      "time = 1\nmat.#= 10 inten= 110 kinen= 3\n"
                      "mat.#= 90 inten= 210\nhgeng= 11\n", encoding="ascii")
    parts = read_ascii_matsum(source)
    assert parts[10]["hourglass_energy"] == [20., None]
    assert parts[90]["kinetic_energy"] is None
    summary = calculate_energy_balance(histories(), parts=parts)["summary"]
    json.dumps(summary, allow_nan=False)
    assert set(summary["parts"]) == {"10", "90"}


def test_initial_tiny_internal_energy_samples_are_explicitly_undefined():
    data = histories()
    data.update(internal_energy=[1e-20, 100.], kinetic_energy=[1., 1.])
    summary = calculate_energy_balance(data, kinetic_ratio_limit=.05)["summary"]
    assert summary["screening_ratios"]["max_kinetic_energy_ratio"] == pytest.approx(.01)
    assert summary["ratio_defined"]["kinetic_energy"]["undefined_samples"] == 1


def test_zero_energy_has_no_arbitrary_absolute_denominator_floor():
    data = {key: [0., 0.] for key in histories()}
    data["time"] = [0., 1.]
    summary = calculate_energy_balance(data, residual_ratio_limit=.01)["summary"]
    assert summary["verdict"] == "incomplete"
    assert summary["balance_residual"]["max_relative_residual"] is None


@pytest.mark.parametrize("scale", [1e-20, 1., 1e20])
def test_screening_ratios_and_undefined_counts_are_unit_invariant(scale):
    data = histories()
    data.update(internal_energy=np.array([1e-20, 100.]) * scale,
                kinetic_energy=np.array([1., 1.]) * scale,
                hourglass_energy=np.array([2., 2.]) * scale)
    summary = calculate_energy_balance(data, kinetic_ratio_limit=.05, hourglass_ratio_limit=.05)["summary"]
    assert summary["screening_ratios"]["max_kinetic_energy_ratio"] == pytest.approx(.01)
    assert summary["screening_ratios"]["max_hourglass_ratio"] == pytest.approx(.02)
    assert summary["ratio_defined"]["hourglass_energy"] == {"defined_samples": 1, "undefined_samples": 1}
    assert summary["passed"] is True


def test_balance_reference_uses_work_increment_when_record_starts_after_zero():
    data = histories()
    data.update(total_energy=[100., 110.], external_work=[50., 60.])
    summary = calculate_energy_balance(data, residual_ratio_limit=1e-8)["summary"]
    assert summary["passed"] is True
    assert summary["balance_residual"]["max_relative_residual"] == 0


@pytest.mark.parametrize("data", [
    {"time": [0., 1.], "internal_energy": [1., float('nan')]},
    {"time": [0., 1.], "internal_energy": [1.]},
    {"time": [0., 1.], "total_energy": [1e308, 1e308], "external_work": [-1e308, 1e308]},
])
def test_nonfinite_or_misaligned_measurements_and_derived_overflow_are_rejected(data):
    with pytest.raises(ValueError):
        calculate_energy_balance(data, residual_ratio_limit=.01)


@pytest.mark.parametrize("reader,body", [
    (read_ascii_glstat, "time.... 0\ninternal energy.... 1\n"),
    (read_ascii_matsum, "time = 0\nmat.#= 1 inten= 1\n"),
])
def test_overlong_ascii_record_has_an_explicit_resource_bound(tmp_path, reader, body):
    source = tmp_path / "energy"
    source.write_text("X" * 20000 + "\n" + body)
    with pytest.raises(ValueError, match="record exceeds"):
        reader(source)
