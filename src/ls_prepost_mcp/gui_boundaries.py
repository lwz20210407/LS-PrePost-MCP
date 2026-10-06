"""Native pressure and nonreflecting conditions on verified Segment sets."""

import math

from pydantic import StrictFloat, StrictInt

from .boundary_cards import inspect_boundary_cards, verify_boundary_delta
from .boundary_geometry import segment_normals, validate_boundary
from .config import command_path
from .core.validation import integer
from .deck_backend import api
from .entity_cards import inspect_cards
from .gui_entities import entity_title, stable_scene
from .jobs import atomic_json
from .units import Unit


def require_unit(label, dimensions):
    unit = Unit.parse(label)
    if unit.dimensions != dimensions:
        raise ValueError("Incorrect physical dimension for unit: " + label)
    return unit.label


def segments_from(index, sid):
    if any(n.startswith("*SET_SEGMENT") for n, _ in index["unresolved"]):
        raise ValueError("Unsupported Segment variant prevents reference validation")
    try:
        records = index["sets"][("segment", sid)]["segments"]
    except KeyError as exc:
        raise ValueError("Requested Segment set does not exist") from exc
    if not records:
        raise ValueError("Cannot apply a boundary to an empty Segment set")
    return records


class GuiBoundaryTools:
    def create_gui_segment_pressure(self, session_id: str, segment_set_id: StrictInt, curve_id: StrictInt,
                                     curve_title: str, points: list[list[StrictFloat]], time_unit: str,
                                     pressure_unit: str, length_unit: str, scale: StrictFloat = 1.0,
                                     arrival_time: StrictFloat = 0.0, load_id: StrictInt | None = None,
                                     load_title: str | None = None, curve_usage: str = "transient") -> dict:
        """Create DEFINE_CURVE plus LOAD_SEGMENT_SET or its named ID variant in the current visible keyword model. Points are [time,pressure] already in explicitly declared deck units, not converted or inferred. Strict increasing time, finite values, SID/curve-table-function namespace/load-ID collisions and duplicate set pressure are checked. Positive pressure acts opposite the reference segment normal; normals and curve readback are recorded.2D edges require supported XY continuum boundary formulations12..15. Native import/readback preserves existing mesh/display/cards. No solver run, follower-load response or complete load-conflict certification."""

        integer(segment_set_id, "segment_set_id")
        integer(curve_id, "curve_id")
        curve_title = entity_title(curve_title)
        time_unit = require_unit(time_unit, (0, 0, 1))
        pressure_unit = require_unit(pressure_unit, (-1, 1, -2))
        length_unit = require_unit(length_unit, (1, 0, 0))
        if not isinstance(points, list) or not 2 <= len(points) <= 10000:
            raise ValueError("Provide2..10000 time-pressure points")
        for i, row in enumerate(points):
            if (not isinstance(row, list) or len(row) != 2 or
                    any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in row)
                    or i and row[0] <= points[i-1][0]):
                raise ValueError("Pressure points require finite pairs and strictly increasing time")
        if any(isinstance(v, bool) or not math.isfinite(v) for v in (scale, arrival_time)):
            raise ValueError("Scale and arrival time must be finite numbers")
        if curve_usage not in ("transient", "relaxation", "both"):
            raise ValueError("Unknown curve usage")
        if load_id is not None:
            integer(load_id, "load_id")
            load_title = entity_title(load_title)
        elif load_title is not None:
            raise ValueError("load_title requires a load_id")
        Deck, kw = api()
        import pandas as pd

        sidr = {"transient": 0, "relaxation": 1, "both": 2}[curve_usage]
        curve = kw.DefineCurve(lcid=curve_id, sidr=sidr)
        curve.title = curve_title
        curve.curves = pd.DataFrame(points, columns=["a1", "o1"])
        load = (kw.LoadSegmentSet if load_id is None else kw.LoadSegmentSetId)(ssid=segment_set_id, lcid=curve_id, sf=scale, at=arrival_time)
        if load_id is not None:
            load.id, load.heading = load_id, load_title
        fragment = Deck()
        fragment.append(curve)
        fragment.append(load)
        expected_curve = dict(curve_id=curve_id, title=curve_title, sidr=sidr, sfa=1.0, sfo=1.0,
                              offa=0.0, offo=0.0, dattyp=0, lcint=0, points=points)
        expected_load = dict(set_id=segment_set_id, curve_id=curve_id, scale=scale, arrival_time=arrival_time,
                             load_id=load_id, title=load_title or "")
        baseline, context = {}, {}

        def preflight(path):
            baseline.update(inspect_boundary_cards(path))
            if any(n.startswith(("*DEFINE_CURVE", "*LOAD_SEGMENT_SET")) for n, _ in baseline["unresolved"]):
                raise ValueError("Unresolved curve/pressure variant must be reviewed before adding a load")
            if curve_id in baseline["namespace_ids"]:
                raise ValueError("Curve ID already exists in curve/table/function namespace")
            if any(r["set_id"] == segment_set_id or (load_id is not None and r["load_id"] == load_id) for r in baseline["loads"]):
                raise ValueError("Pressure already exists on this set, or load ID collides")
            records = segments_from(inspect_cards(path), segment_set_id)
            dimension, audit = segment_normals(path, records)
            if dimension == 2:
                context["boundary"] = validate_boundary(path, records, 2, (12, 13, 14, 15), require_ccw=False)
            context.update(dimension=dimension, audit=audit)

        def commands(state, directory):
            path = directory / "pressure.k"
            fragment.export_file(str(path))
            atomic_json(directory / "pressure-directions.json", dict(length_unit=length_unit,
                        pressure_unit=pressure_unit, time_unit=time_unit, reference_segments=context["audit"],
                        convention="Positive pressure acts opposite reference normal; no solver follower response computed"))
            context["direction_report"] = str(directory / "pressure-directions.json")
            return ["import keyword " + command_path(path)]

        def postcheck(_, path, verification):
            actual = inspect_boundary_cards(path)
            audit = verify_boundary_delta(baseline, actual, curve=expected_curve, load=expected_load)
            atomic_json(path.parent / "pressure-readback.json", dict(curve=actual["curves"][curve_id], load=audit["actual_load"]))
            summary = {k: v for k, v in expected_curve.items() if k != "points"}
            summary["point_count"] = len(points)
            verification.update(created_curve=summary, curve_readback=str(path.parent / "pressure-readback.json"),
                                created_load=audit["actual_load"], dimension=context["dimension"],
                                segment_count=len(context["audit"]), direction_report=context["direction_report"],
                                units=dict(time=time_unit, pressure=pressure_unit, length=length_unit),
                                unit_labels_verified_against_model=False)
            return audit

        return self._gui_mesh_edit(session_id, "create_gui_segment_pressure",
            dict(segment_set_id=segment_set_id, curve_id=curve_id, curve_title=curve_title, points=points,
                 time_unit=time_unit, pressure_unit=pressure_unit, length_unit=length_unit, scale=scale,
                 arrival_time=arrival_time, load_id=load_id, load_title=load_title, curve_usage=curve_usage),
            commands, stable_scene, postcheck=postcheck, preflight=preflight,
            snapshot_parameters=dict(visibility_readback=True))

    def create_gui_nonreflecting_boundary(self, session_id: str, segment_set_id: StrictInt, dimension: StrictInt,
                                          solver_release: StrictInt, length_unit: str,
                                          dilatational: bool = True, shear: bool = True,
                                          node_set_start_id: StrictInt | None = None) -> dict:
        """Create native nonreflecting conditions on unique exterior linear-solid faces or counterclockwise XY continuum edges(SECTION_SHELL13/14/15). Explicit solver target11..16 is separate from LSPP version.2D R14+ uses negative Segment SID;2D R11..13 requires node_set_start_id and emits one ordered two-node set per edge, preserving native endpoint order, with both wave families enabled.3D permits either face winding. Reject overlapping conditions, reversed2D/interior faces, ID collisions and unsupported variants. AD/AS zero means enabled. Native card/geometry checks are not solver absorption, material, dynamic-relaxation or stability certification."""

        integer(segment_set_id, "segment_set_id")
        integer(solver_release, "solver_release", 11, 16)
        length_unit = require_unit(length_unit, (1, 0, 0))
        if type(dimension) is not int or dimension not in (2, 3):
            raise ValueError("Boundary dimension must be2 or3")
        if type(dilatational) is not bool or type(shear) is not bool:
            raise ValueError("Wave family switches must be boolean")
        legacy = dimension == 2 and solver_release < 14
        if legacy:
            if node_set_start_id is None:
                raise ValueError("Direct Segment-based2D requires R14+; provide node_set_start_id for the R11..13 ordered-edge route")
            integer(node_set_start_id, "node_set_start_id")
            if not (dilatational and shear):
                raise ValueError("Legacy2D route supports only the documented default enabled wave families")
        elif node_set_start_id is not None:
            raise ValueError("node_set_start_id applies only to the legacy2D route")
        Deck, kw = api()
        target = -segment_set_id if dimension == 2 else segment_set_id
        ad, as_ = int(not dilatational), int(not shear)
        fragment = Deck()
        if not legacy:
            card = (kw.BoundaryNonReflecting2D(nsid=target, ad=ad, as_=as_) if dimension == 2 else
                    kw.BoundaryNonReflecting(ssid=target, ad=float(ad), as_=float(as_)))
            fragment.append(card)
        baseline, context = {}, {}
        expected = [] if legacy else [dict(dimension=dimension, target_id=target, ad=float(ad), as_=float(as_))]
        new_sets = []

        def preflight(path):
            baseline.update(inspect_boundary_cards(path, include_ordered_node_sets=dimension == 2))
            if any(n.startswith("*BOUNDARY_NON_REFLECTING") for n, _ in baseline["unresolved"]):
                raise ValueError("Unscoped/unsupported nonreflecting definition requires review")
            entities = inspect_cards(path)
            records = segments_from(entities, segment_set_id)
            actual_dimension, audit = segment_normals(path, records)
            if actual_dimension != dimension:
                raise ValueError("Requested dimension does not match Segment connectivity")
            context.update(audit=audit, boundary=validate_boundary(path, records, dimension))
            wanted = {tuple(sorted(r["node_ids"])) for r in records}
            for existing in baseline["nonreflecting"]:
                if existing["dimension"] != dimension:
                    continue
                if existing["target_id"] == 0 or (dimension == 3 and existing["target_id"] < 0):
                    raise ValueError("Unsupported existing nonreflecting target ID")
                if dimension == 2 and existing["target_id"] > 0:
                    old = baseline["ordered_node_sets"].get(existing["target_id"])
                    if old is None or len(old["order"]) < 2:
                        raise ValueError("Cannot resolve existing ordered-node boundary")
                    old_faces = [pair for pair in zip(old["order"], old["order"][1:])]
                else:
                    old_faces = [r["node_ids"] for r in segments_from(entities, abs(existing["target_id"]))]
                if wanted & {tuple(sorted(row)) for row in old_faces}:
                    raise ValueError("Nonreflecting condition already covers one or more requested faces/edges")
            if legacy:
                integer(node_set_start_id + len(records) - 1, "last allocated node-set ID")
                if any(n.startswith("*SET_NODE") for n, _ in baseline["unresolved"]):
                    raise ValueError("Unresolved node-set namespace prevents allocation")
                for i, record in enumerate(records):
                    uid = node_set_start_id + i
                    if uid in baseline["ordered_node_sets"]:
                        raise ValueError("Allocated ordered node-set ID already exists")
                    name = "NR2D edge " + str(uid)
                    nodes = list(record["node_ids"])
                    node_set = kw.SetNodeList(sid=uid)
                    node_set.title, node_set.nodes = name, nodes
                    fragment.append(node_set)
                    fragment.append(kw.BoundaryNonReflecting2D(nsid=uid))
                    new_sets.append(dict(entity_type="node", set_id=uid, title=name, member_ids=sorted(nodes),
                                         order=nodes, attributes=[0.0]*4, solver="MECH", its="1"))
                    expected.append(dict(dimension=2, target_id=uid, ad=0.0, as_=0.0))

        def commands(state, directory):
            path = directory / "nonreflecting.k"
            fragment.export_file(str(path))
            atomic_json(directory / "boundary-geometry.json", dict(**context, length_unit=length_unit,
                        solver_release=solver_release, created_boundaries=expected, created_ordered_node_sets=new_sets))
            context["report"] = str(directory / "boundary-geometry.json")
            return ["import keyword " + command_path(path)]

        def postcheck(_, path, verification):
            audit = verify_boundary_delta(baseline, inspect_boundary_cards(path, include_ordered_node_sets=dimension == 2),
                                          nonreflecting=expected, new_node_sets=new_sets)
            verification.update(created_boundary=expected[0] if len(expected) == 1 else None,
                                created_boundary_count=len(expected), created_boundaries_sample=expected[:20],
                                created_node_set_count=len(new_sets), boundary_geometry=context["boundary"],
                                geometry_report=context["report"], target_solver_release=solver_release,
                                keyword_ingestion_only=True, impedance_physics_verified=False)
            return audit

        return self._gui_mesh_edit(session_id, "create_gui_nonreflecting_boundary",
            dict(segment_set_id=segment_set_id, dimension=dimension, solver_release=solver_release,
                 length_unit=length_unit, dilatational=dilatational, shear=shear, node_set_start_id=node_set_start_id),
            commands, stable_scene, postcheck=postcheck, preflight=preflight,
            snapshot_parameters=dict(visibility_readback=True))
