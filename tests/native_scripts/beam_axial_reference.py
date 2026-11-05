"""Run ONLY inside an owned LS-PrePost process after root grants a headless lease.

This experimental reference does not enable product native_check or guess fringe codes.
"""
import csv
import json
import math
import traceback

import DataCenter as dc

try:
    with open("expected-plan.json") as stream:
        plan = json.load(stream)
    kind = dc.Type.BEAM
    count = int(dc.get_data("num_beam_elements"))
    states = int(dc.get_data("num_states"))
    # Native vectors may refer to shared buffers. Copy every value needed before
    # another SDK call, including the full geometry-ID and time registries.
    registry = [int(value) for value in dc.get_data("element_ids", type=kind)]
    times = [float(value) for value in dc.get_data("state_times")]
    if count != plan["beam_count"] or states != plan["state_count"]:
        raise ValueError("Native model counts differ from frozen sample")
    if len(registry) != count or len(set(registry)) != count or any(value <= 0 for value in registry):
        raise ValueError("Native beam user-ID registry is incomplete or ambiguous")
    if len(times) != states or not all(math.isfinite(value) for value in times):
        raise ValueError("Native state-time registry is incomplete")
    indexes = {uid: registry.index(uid) for uid in plan["entity_ids"]}
    rows = []
    for state in plan["states"]:
        if not 1 <= state <= states:
            raise ValueError("Expected states must be 1-based")
        # Keep the binding's documented/default ipt. No unverified numeric
        # sampling selector or UI component number is supplied.
        native = dc.get_data("axial_force", type=kind, ist=state)
        if len(native) != count:
            raise ValueError("Native axial_force length differs from beam registry")
        values = [(uid, float(native[indexes[uid]])) for uid in plan["entity_ids"]]
        if not all(math.isfinite(value) for _, value in values):
            raise ValueError("Native axial_force contains non-finite requested values")
        rows.extend((state, times[state - 1], uid, value) for uid, value in values)
    if len(rows) != len(plan["states"]) * len(plan["entity_ids"]):
        raise ValueError("Native state/user-ID matrix is incomplete")
    with open("native-beam.csv", "w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["state", "time", "entity_id", "axial_force"])
        writer.writerows(rows)
    with open("native-beam-marker.json", "w") as stream:
        json.dump(dict(complete=True, beam_count=count, state_count=states,
                       field="axial_force", entity_ids=plan["entity_ids"],
                       requested_states=plan["states"], ipt="binding default; not independently identified",
                       rows=len(rows)), stream)
except Exception as exc:
    with open("native-beam-marker.json", "w") as stream:
        json.dump(dict(complete=False, error_type=type(exc).__name__,
                       error=str(exc), traceback=traceback.format_exc()), stream)
    raise
