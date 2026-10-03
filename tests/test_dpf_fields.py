from types import SimpleNamespace

import numpy as np
import pytest

from ls_prepost_mcp.dpf_fields import field_spec, flatten_fields, write_labelled_csv


class Field:
    def __init__(self, ids, values, location="TimeFreq_steps", components=1, unit=""):
        self.scoping = SimpleNamespace(ids=ids)
        self.data = np.asarray(values)
        self.location, self.component_count, self.unit = location, components, unit
        self._values = dict(zip(ids, values, strict=True))

    def get_entity_data_by_id(self, uid):
        return np.asarray(self._values[uid])


class Container(list):
    def __init__(self, fields, labels, time_ids=(2, 9), times=(.1, .9)):
        super().__init__(fields)
        self.labels = labels
        self.time_freq_support = SimpleNamespace(time_frequencies=Field(time_ids, times, unit="s"))

    def get_label_space(self, i):
        return self.labels[i]


def test_binout_uses_time_ids_not_position_or_global_axis(tmp_path):
    fc = Container([Field([9, 2], [90., 20.], unit="J")], [dict(part=50)])
    rows, report = flatten_fields(fc, "binout", "part_kinetic_energy")
    assert [(r[4], r[5], r[8]) for r in rows] == [(9, .9, 90.), (2, .1, 20.)]
    assert all(r[6] is None for r in rows)
    assert report["fields"][0]["labels"] == dict(part=50)
    spec = field_spec(rows, report, "declared_model_units")
    assert spec["backend"] == "dpf" and spec["selection"]["domain"] == "part"
    assert spec["selection"]["entity_id_sample"] == [50]
    assert spec["sampling"]["kind"] == "dpf_native_location"
    artifact = write_labelled_csv(tmp_path / "result.csv", rows)
    assert artifact["row_count"] == 2 and artifact["validated"]


def test_interface_master_slave_do_not_collapse():
    fc = Container([Field([2], [[1., 2., 3.]], components=3, unit="N"),
                    Field([2], [[-1., -2., -3.]], components=3, unit="N")],
                   [dict(interface=19, idtype=0), dict(interface=19, idtype=1)])
    rows, report = flatten_fields(fc, "binout", "interface_contact_force", label_filter=dict(idtype=1))
    assert [r[8] for r in rows] == [-1., -2., -3.]
    assert report["fields"][0]["labels"]["idtype"] == 1
    single, _ = flatten_fields(fc, "binout", "interface_contact_force", label_filter=dict(idtype=1), component=2)
    assert len(single) == 1 and single[0][7:9] == [2, -3.]
    fc.labels[0].pop("idtype")
    with pytest.raises(ValueError, match="master/slave"):
        flatten_fields(fc, "binout", "interface_contact_force")


def test_missing_branch_sets_are_not_filled_or_interpolated():
    fc = Container([Field([2], [1.])], [dict(part=7)])
    with pytest.raises(ValueError, match="missing in this branch"):
        flatten_fields(fc, "binout", "part_internal_energy", states=[2, 9])


def test_absolute_peak_preserves_sign_and_entity_identity():
    fc = Container([Field([90, 10], [-12., 3.], "Elemental", unit="MPa"),
                    Field([10, 90], [7., -4.], "Elemental", unit="MPa")],
                   [dict(time=2, body=4), dict(time=9, body=4)])
    _, report = flatten_fields(fc, "d3plot", "beam_axial_stress", states=[2, 9])
    peak = report["extrema"]["groups"][0]
    assert peak["maximum"]["value"] == 7
    assert peak["absolute_peak"] == dict(set_id=2, time=.1, entity_id=90, value=-12.)
    assert report["contract"]["frame"].startswith("beam local")


def test_erosion_requires_exact_flags_and_keeps_user_ids():
    fc = Container([Field([901, 307], [0., 1.], "Elemental")], [dict(time=9)])
    rows, report = flatten_fields(fc, "d3plot", "erosion_flag", states=[9])
    assert [r[6] for r in rows] == [901, 307]
    assert report["fields"][0]["active_count"] == report["fields"][0]["eroded_count"] == 1
    fc[0]._values[307] = .5
    with pytest.raises(ValueError, match="exactly"):
        flatten_fields(fc, "d3plot", "erosion_flag", states=[9])


@pytest.mark.parametrize("invalid", ["location", "nan", "multiplicity", "missing_entity", "duplicate"])
def test_unsupported_or_incomplete_spatial_output_fails(invalid):
    fc = Container([Field([11], [3.], "Elemental")], [dict(time=2)])
    if invalid == "location":
        fc[0].location = "ElementalNodal"
    elif invalid == "nan":
        fc[0]._values[11] = float("nan")
    elif invalid == "multiplicity":
        fc[0]._values[11] = [1., 2.]
    elif invalid == "duplicate":
        fc.append(fc[0])
        fc.labels.append(dict(time=2))
    with pytest.raises(ValueError):
        flatten_fields(fc, "d3plot", "beam_axial_force", states=[2],
                       entity_ids=[99] if invalid == "missing_entity" else None)
