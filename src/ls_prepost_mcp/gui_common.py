"""Common pre/post native geometry queries with independent numeric checks."""

import json
import math
import re
from pathlib import Path

import numpy as np
from pydantic import StrictInt

from .core.native_log import native_errors, read_delta
from .gui_controls import wait_for_gui_state
from .gui_mesh import ReadOnlyScopeMismatch, verify_mesh_digest
from .gui_selection import part_visibility
from .jobs import atomic_json, check_artifact
from .native import commands as nc
from .post_backend import ids

COUNTS = {"distance": 2, "height": 2, "angle3": 3, "angle4": 4, "circle3": 3}


def check_measurement(data, mode, axis, native_text):
    positions = np.asarray([row[1:] for row in data["node_positions"]], dtype=float)
    raw = data["native_values"]
    scale = max(float(np.max(np.abs(positions))), 1e-300)
    def near(a, b, text_precision=False):
        return np.allclose(a, b, rtol=6e-6 if text_precision else 2e-6,
                           atol=scale*(6e-6 if text_precision else 16*2**-23))
    if mode == "coordinates":
        if any(len(v) != 3 for v in raw) or not near(raw, positions):
            raise ValueError("Native Identify coordinates disagree with source coordinates")
        return dict(nodes=[dict(id=row[0], coordinates=row[1:]) for row in data["node_positions"]], value_unit="declared_length")
    values = raw[0]
    if mode in ("distance", "height"):
        delta = positions[1]-positions[0]
        distance = float(np.linalg.norm(delta))
        if len(values) != 4 or not near(values, [distance, *delta]):
            raise ValueError("Native distance/components disagree with the source node positions")
        result = dict(distance=values[0], delta=dict(zip("xyz", values[1:], strict=True)), value_unit="declared_length")
        if mode == "height":
            result.update(axis=axis, signed_height=values[1+"xyz".index(axis)], height=abs(values[1+"xyz".index(axis)]))
        return result
    if mode in ("angle3", "angle4"):
        a = positions[0]-positions[1] if mode == "angle3" else positions[1]-positions[0]
        b = positions[2]-positions[1] if mode == "angle3" else positions[3]-positions[2]
        expected = math.degrees(math.acos(float(np.clip(np.dot(a, b)/np.linalg.norm(a)/np.linalg.norm(b), -1, 1))))
        if len(values) != 4 or not math.isclose(values[0], expected, rel_tol=2e-6, abs_tol=2e-4):
            raise ValueError("Native angle disagrees with the requested node directions")
        return dict(angle_degrees=values[0], value_unit="deg", native_projected_values_uninterpreted=values[1:])
    if len(values) != 1:
        raise ValueError("Native radius result layout is unsupported")
    a, b = positions[1]-positions[0], positions[2]-positions[0]
    cross = np.cross(a, b)
    denominator = 2*float(np.dot(cross, cross))
    if denominator <= 0:
        raise ValueError("Collinear circle scope")
    center = positions[0] + (np.dot(a, a)*np.cross(b, cross)+np.dot(b, b)*np.cross(cross, a))/denominator
    radius = float(np.linalg.norm(center-positions[0]))
    if not near(values[0], radius):
        raise ValueError("Native radius disagrees with the three node coordinates")
    pattern = r"Radius formed by\s+(\d+)\s+(\d+)\s+(\d+)\s*=\s*([^,\s]+),\s*center:\s*([^,\s]+)\s*,\s*([^,\s]+)\s*,\s*([^\s]+)"
    matches = re.findall(pattern, native_text)
    wanted = tuple(row[0] for row in data["node_positions"])
    matches = [match for match in matches if tuple(map(int, match[:3])) == wanted]
    if len(matches) != 1:
        raise ValueError("Native circle center message is missing or ambiguous")
    reported = [float(v) for v in matches[0][4:7]]
    if not np.isfinite(reported).all() or not near(reported, center, True):
        raise ValueError("Native circle center disagrees with the three node coordinates")
    return dict(radius=values[0], center=reported, center_backend="lsprepost-message-log",
                value_unit="declared_length", center_text_precision="native console formatting")


class GuiCommonTools:
    def measure_gui_geometry(self, session_id: str, measurement: str, node_ids: list[StrictInt], units: str,
                             axis: str = "z", state: StrictInt | None = None, capture: bool = False) -> dict:
        """Native common pre/post coordinate/distance/axis-height/3-node or 4-node angle/3-node circle query. Keyword uses reference geometry; d3plot requires explicit state and uses native state coordinates. Global axes0 and scale1 requested; numeric output is independently checked. Native measurement/Identify overlays remain; optional PNG. Targets the active managed model. Projected angle values are not interpreted; full F4/F5 panels remain broader."""
        from .service import unit_label

        unit_label(units)
        if measurement not in {*COUNTS, "coordinates"} or axis not in "xyz" or len(axis) != 1:
            raise ValueError("Unsupported native measurement or global height axis")
        ids(node_ids, "node_ids", 100)
        if measurement in COUNTS and len(node_ids) != COUNTS[measurement]:
            raise ValueError("Measurement requires exactly%d node IDs" % COUNTS[measurement])
        if state is not None and (type(state) is not int or state < 1):
            raise ValueError("State must be a positive1-based integer")
        if type(capture) is not bool:
            raise ValueError("capture must be boolean")
        manager = self._session_manager()
        arguments = dict(measurement=measurement, node_ids=node_ids, units=units, axis=axis, state=state, capture=capture)
        with manager.lock(session_id):
            meta = self._visible_mesh_session(session_id, manager, allow_results=True)
            if meta["model_kind"] == "d3plot" and state is None:
                raise ValueError("Result geometry measurements require an explicit state")
            if meta["model_kind"] == "keyword" and state is not None:
                raise ValueError("Keyword geometry has reference coordinates; omit state")
            if state is not None:
                settled, _ = wait_for_gui_state(manager, session_id, state, self.settings.timeout,
                                                native_commands=[nc.animation('stop'), nc.state(state)])
                if settled["status"] != "succeeded":
                    return settled
            baseline = manager.dispatch(session_id, "gui_mesh_digest", {})
            if baseline["status"] != "succeeded":
                return baseline
            log = manager.directory(session_id)/"lspost.msg"
            offset = log.stat().st_size if log.exists() else 0
            try:
                result = manager.dispatch(session_id, "gui_measure", dict(measurement=measurement, node_ids=node_ids, state=state),
                                          native_commands=["measure select 1"])
            except Exception as exc:
                result = dict(status="uncertain", session_id=session_id, job_directory=baseline["job_directory"],
                              artifacts=[], error=dict(type=type(exc).__name__, message=str(exc)))
            directory = Path(result["job_directory"])
            geometry_unchanged = False
            if result["status"] == "failed":
                response_file = directory/"complete.json"
                response = json.loads(response_file.read_text(encoding="utf8")) if response_file.is_file() else {}
                if response.get("query_started") is False and not manager.read(session_id).get("active_request"):
                    checked = manager.dispatch(session_id, "gui_mesh_digest", {})
                    if checked["status"] == "succeeded":
                        try:
                            verify_mesh_digest(baseline["data"], checked["data"])
                            if (part_visibility(baseline["data"]) != part_visibility(checked["data"]) or
                                    baseline["data"]["current_state"] != checked["data"]["current_state"]):
                                raise ValueError("Read-only precondition failure changed scope")
                            stable = manager.read(session_id)
                            stable.update(state="ready", dirty=meta.get("dirty", False))
                            manager.save(session_id, stable)
                            result["verification"] = dict(precondition_rejected=True, geometry_preserved=True, model_ready=True)
                        except ValueError:
                            pass
            if result["status"] == "succeeded":
                try:
                    after = manager.dispatch(session_id, "gui_mesh_digest", {})
                    if after["status"] != "succeeded":
                        raise ValueError("Native measurement preservation readback failed")
                    verify_mesh_digest(baseline["data"], after["data"])
                    geometry_unchanged = True
                    if (part_visibility(baseline["data"]) != part_visibility(after["data"]) or
                            baseline["data"]["current_state"] != after["data"]["current_state"]):
                        raise ReadOnlyScopeMismatch("Measurement changed native state/part visibility")
                    text = read_delta(log, offset, existed=True)
                    (directory/"native.log").write_text(text, encoding="utf8")
                    if native_errors(text):
                        raise ValueError("Native measurement reported command errors")
                    computed = check_measurement(result["data"], measurement, axis, text)
                    computed.update(backend="lsprepost", measurement=measurement, units=units,
                                    node_ids=node_ids, model_kind=meta["model_kind"],
                                    coordinate_configuration=result["data"]["coordinate_configuration"],
                                    state=state, global_axes_requested=0, scale_factor_requested=1,
                                    native_model_context=result["data"]["native_model_context"], dimensional_validation=False,
                                    scene_after="Native measurement/Identify overlays and axes0/scale1 retained; requested result state retained",
                                    verification="Native numeric query plus independent coordinate geometry; complete reference mesh preserved")
                    if capture:
                        image = manager.dispatch(session_id, "inspect_model", {}, native_commands=[
                            nc.print_png(directory/"measurement.png")])
                        if image["status"] != "succeeded":
                            raise ValueError("Native measurement image failed")
                        result["artifacts"].append(check_artifact(directory/"measurement.png", "png"))
                    atomic_json(directory/"measurement.json", computed)
                    result["artifacts"].append(check_artifact(directory/"measurement.json", "json"))
                    result["data"] = computed
                except Exception as exc:
                    result.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)), artifacts=[])
                    if not geometry_unchanged:
                        changed = manager.read(session_id)
                        changed.update(state="uncertain", dirty=True)
                        manager.save(session_id, changed)
            result["parameters"] = arguments
            atomic_json(directory/"operation.json", result)
            manager.journal(session_id, dict(action="measure_gui_geometry", parameters=arguments, result=result))
            return result
