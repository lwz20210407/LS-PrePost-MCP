"""DPF field semantics, independent of a running server or optional client import."""

import csv
import json
import math

import numpy as np

from .field_contracts import FieldSpec, ResultSelection, SamplingSpec

BEAM_RESULTS = {
    "beam_axial_force", "beam_s_shear_force", "beam_t_shear_force",
    "beam_s_bending_moment", "beam_t_bending_moment", "beam_torsional_moment",
    "beam_axial_stress", "beam_rs_shear_stress", "beam_tr_shear_stress",
    "beam_axial_plastic_strain", "beam_axial_total_strain",
}
GLOBAL_RESULTS = {
    "global_kinetic_energy", "global_internal_energy", "global_total_energy",
    "global_external_work", "global_eroded_kinetic_energy", "global_eroded_internal_energy",
    "global_energy_ratio", "global_energy_ratio_wo_eroded", "global_added_mass",
}
PART_RESULTS = {
    "part_internal_energy", "part_kinetic_energy", "part_eroded_internal_energy",
    "part_eroded_kinetic_energy", "part_added_mass",
}
RESULTS = {
    "d3plot": BEAM_RESULTS | {"displacement", "velocity", "acceleration", "erosion_flag"}
    | {"global_kinetic_energy", "global_internal_energy", "global_total_energy"},
    "binout": GLOBAL_RESULTS | PART_RESULTS | {"interface_contact_force"},
}
COLUMNS = ["result", "field_index", "labels", "location", "set_id", "time",
           "entity_id", "component", "value", "dpf_unit", "time_unit"]


def result_contract(file_type, result):
    if file_type not in RESULTS or result not in RESULTS[file_type]:
        raise ValueError("Unsupported DPF result/file type; use the documented typed result list")
    location = ("TimeFreq_steps" if result in GLOBAL_RESULTS | PART_RESULTS | {"interface_contact_force"}
                else "Elemental" if result in BEAM_RESULTS | {"erosion_flag"} else "Nodal")
    return dict(location=location, components=3 if result in {
        "displacement", "velocity", "acceleration", "interface_contact_force"} else 1,
        minimum_server="8.0" if result in BEAM_RESULTS | {"erosion_flag"} else "7.1",
        frame="beam local directions, scalar; no local/global transform" if result in BEAM_RESULTS
        else "DPF source frame; no requested transformation",
        validity="physical erosion flag: active=1, eroded=0" if result == "erosion_flag"
        else "as returned; no inferred physical alive/deletion mask")


def positive_ids(values, label):
    out = []
    for value in values:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < 1:
            raise ValueError(label + " must contain positive integer IDs")
        out.append(int(value))
    if len(out) != len(set(out)):
        raise ValueError(label + " contains duplicate IDs")
    return out


def time_axis(support):
    field = support.time_frequencies
    ids = positive_ids(field.scoping.ids, "Time scoping")
    values = np.asarray(field.data, dtype=float).reshape(-1)
    if len(ids) != len(values) or not ids or not np.isfinite(values).all():
        raise ValueError("Invalid DPF time support")
    return dict(zip(ids, values.tolist(), strict=True)), str(field.unit or "")


def flatten_fields(container, file_type, result, states=None, entity_ids=None, label_filter=None, component=None, max_rows=500000):
    """Keep labels and branch-local time IDs; never zip fields to a model-wide axis.

    No averaging, positional ID mapping, implicit layer collapse or zero filling.
    """
    contract = result_contract(file_type, result)
    if component is not None and (type(component) is not int or not 0 <= component < contract["components"]):
        raise ValueError("Invalid DPF component index")
    if not 0 < len(container) <= 512:
        raise ValueError("Empty DPF output or too many labelled fields")
    times, time_unit = time_axis(container.time_freq_support)
    requested_states = None if states is None else set(positive_ids(states, "Requested states"))
    requested_entities = None if entity_ids is None else set(positive_ids(entity_ids, "Requested entities"))
    if requested_states is not None and (not requested_states or not requested_states <= times.keys()):
        raise ValueError("Requested states are absent from this result's time support")
    if requested_entities is not None and contract["location"] == "TimeFreq_steps":
        raise ValueError("TimeFreq_steps uses part/interface label spaces, not mesh entity IDs")
    rows, fields, seen = [], [], set()
    for index, field in enumerate(container):
        labels = container.get_label_space(index)
        if not isinstance(labels, dict) or any(not isinstance(k, str) or isinstance(v, bool)
                or not isinstance(v, (int, np.integer)) for k, v in labels.items()):
            raise ValueError("DPF label space must map names to integer IDs")
        labels = {key: int(value) for key, value in labels.items()}
        if label_filter and any(labels.get(k) != v for k, v in label_filter.items()):
            continue
        serialized = json.dumps(labels, sort_keys=True, separators=(",", ":"))
        location = str(field.location)
        if location != contract["location"] or int(field.component_count) != contract["components"]:
            raise ValueError("Unexpected DPF location/component count; no averaging or layer collapse is allowed")
        if result in PART_RESULTS and "part" not in labels:
            raise ValueError("Part history lacks its part label")
        if result == "interface_contact_force" and ("interface" not in labels or labels.get("idtype") not in (0, 1)):
            raise ValueError("Contact-force history requires interface and master/slave idtype labels")
        scoped = positive_ids(field.scoping.ids, "Field scoping")
        if location != "TimeFreq_steps":
            state = labels.get("time")
            if state not in times:
                raise ValueError("Spatial field lacks an explicit time label in its time support")
            if requested_states is not None and state not in requested_states:
                continue
            if requested_entities is not None and not requested_entities <= set(scoped):
                raise ValueError("Requested entities are missing in a labelled field; restrict labels explicitly")
        else:
            if not set(scoped) <= times.keys():
                raise ValueError("History field's time IDs are absent from its own time support")
            if requested_states is not None and not requested_states <= set(scoped):
                raise ValueError("Requested states are missing in this branch/label space")
        units = str(field.unit or "")
        emitted, eroded, active = 0, 0, 0
        for uid in scoped:
            if location == "TimeFreq_steps":
                state, entity = uid, None
                if requested_states is not None and state not in requested_states:
                    continue
            else:
                entity = uid
                if requested_entities is not None and uid not in requested_entities:
                    continue
            values = np.asarray(field.get_entity_data_by_id(uid), dtype=float).reshape(-1)
            if len(values) != contract["components"] or not np.isfinite(values).all():
                raise ValueError("Missing/nonfinite values or unresolved integration-point multiplicity")
            if result == "erosion_flag":
                if values[0] not in (0.0, 1.0):
                    raise ValueError("Erosion flags must be exactly active=1 or eroded=0")
                active += int(values[0] == 1)
                eroded += int(values[0] == 0)
            for column, value in enumerate(values):
                if component is not None and column != component:
                    continue
                identity = (serialized, state, entity, column)
                if identity in seen:
                    raise ValueError("Duplicate DPF label/state/entity/component identity")
                seen.add(identity)
                rows.append([result, index, serialized, location, state, times[state], entity,
                             column, float(value), units, time_unit])
                if len(rows) > max_rows:
                    raise ValueError("DPF export row budget exceeded; narrow the scope")
            emitted += 1
        fields.append(dict(index=index, labels=labels, location=location, dpf_unit=units,
                           emitted_entities=emitted, active_count=active if result == "erosion_flag" else None,
                           eroded_count=eroded if result == "erosion_flag" else None))
    if not rows:
        raise ValueError("DPF produced no requested values")
    if requested_states is not None and {row[4] for row in rows} != requested_states:
        raise ValueError("DPF omitted requested states")
    return rows, dict(backend="dpf", result=result, contract=contract, fields=fields,
                      rows=len(rows), time_unit=time_unit, unit_conversion=False,
                      averaging="none requested; native result location required",
                      state_mapping="field scoping IDs for histories; time labels for spatial fields",
                      extrema=extrema(rows))


def extrema(rows):
    groups = {}
    for row in rows:
        labels = {k: v for k, v in json.loads(row[2]).items() if k != "time"}
        key = (row[0], json.dumps(labels, sort_keys=True), row[7], row[9], row[10])
        witness = dict(set_id=row[4], time=row[5], entity_id=row[6], value=row[8])
        if key not in groups:
            groups[key] = dict(result=row[0], labels=labels, component=row[7], dpf_unit=row[9], time_unit=row[10],
                               minimum=witness, maximum=witness, absolute_peak=witness)
        value = groups[key]
        if row[8] < value["minimum"]["value"]:
            value["minimum"] = witness
        if row[8] > value["maximum"]["value"]:
            value["maximum"] = witness
        if abs(row[8]) > abs(value["absolute_peak"]["value"]):
            value["absolute_peak"] = witness
    return dict(scope="Exported rows only; labels except time, component and units remain separate; first tie retained",
                groups=list(groups.values()))


def write_labelled_csv(path, rows):
    """Read back text + numeric columns; generic project CSV validator is numeric-only."""
    from .jobs import fingerprint

    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        if next(reader) != COLUMNS:
            raise ValueError("DPF CSV header differs")
        count = 0
        for expected, actual in zip(rows, reader, strict=True):
            if actual != ["" if v is None else str(v) for v in expected]:
                raise ValueError("DPF CSV representation differs from verified rows")
            if not isinstance(json.loads(actual[2]), dict):
                raise ValueError("DPF CSV lost its label space")
            for i in (1, 4, 5, 7, 8):
                if not math.isfinite(float(actual[i])):
                    raise ValueError("DPF CSV contains nonfinite numeric data")
            count += 1
    if not count:
        raise ValueError("DPF CSV is empty")
    return dict(**fingerprint(path), kind="csv", schema="dpf_labelled_long_v1", validated=True, row_count=count)


def field_spec(rows, report, declared_units):
    result, contract = report["result"], report["contract"]
    domain = ("beam" if result in BEAM_RESULTS else "element" if result == "erosion_flag" else
              "part" if result in PART_RESULTS else "interface" if result == "interface_contact_force" else
              "global" if result in GLOBAL_RESULTS else "node")
    if domain in ("part", "interface"):
        entities = list(dict.fromkeys(json.loads(row[2])[domain] for row in rows))
    else:
        entities = list(dict.fromkeys(row[6] for row in rows if row[6] is not None))
    spec = FieldSpec("dpf", (result,), declared_units,
        ResultSelection(domain, entities, list(dict.fromkeys(row[4] for row in rows))),
        SamplingSpec("dpf_native_location", contract["location"]), contract["frame"],
        report["averaging"], contract["validity"]).describe()
    spec["selection"].update(full_request_location="result.csv + semantics.json expanded labels/time/ID scope",
        state_index_semantics="DPF time-set IDs; correspondence to LS-PrePost states is not inferred",
        global_csv_entity_placeholder=None)
    spec["dpf_reported_units"] = sorted({row[9] for row in rows})
    spec["label_spaces_location"] = "semantics.json:fields and result.csv:labels"
    return spec
