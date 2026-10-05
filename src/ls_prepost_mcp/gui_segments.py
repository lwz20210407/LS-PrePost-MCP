"""Native Segment-set creation from explicit and selection-bound mesh scopes."""

import math

import numpy as np
from pydantic import StrictFloat, StrictInt

from .config import command_path
from .core.validation import integer, numbers, unit_label
from .deck_backend import api
from .entity_cards import inspect_cards, verify_cards
from .gui_entities import entity_title, selection_source, stable_scene
from .gui_selection import mesh_signature
from .jobs import atomic_json
from .post_backend import ids
from .segment_geometry import build_segments


class GuiSegmentTools:
    def create_gui_segment_set(self, session_id: str, set_id: StrictInt, title: str, source: str,
                               length_unit: str, element_ids: list[StrictInt] | None = None,
                               selection_job: str | None = None, normal_direction: list[StrictFloat] | None = None,
                               cosine_min: StrictFloat = 0.99, reverse: bool = False,
                               max_warpage_degrees: StrictFloat = 15.0) -> dict:
        """Create a native SET_SEGMENT from solid_exterior (conforming Hex8/Tet4), shell_faces (Tri3/Quad4), or shell_boundary_2d (XY Tri3/Quad4 boundary edges). One explicit element-ID list or same-session selection_job of matching solid/shell domain. Exterior ownership is checked against the entire matching mesh domain, not just selected cells; no disconnected/nonconforming geometric intersections. Orient solids/2D edges outward, shells by connectivity; filter those normals by optional direction/cosine, then reverse if requested. Verify native saved ordered connectivity, attributes, full mesh/state/display and other cards. Max20000 selected elements and generated segments, ASCII names, standalone native short-format export; only creation, not solver boundary applicability certification."""

        integer(set_id, "set_id")
        title = entity_title(title)
        unit_label(length_unit)
        if source not in ("solid_exterior", "shell_faces", "shell_boundary_2d"):
            raise ValueError("Unsupported segment source")
        if type(reverse) is not bool or not math.isfinite(cosine_min) or not -1 <= cosine_min <= 1:
            raise ValueError("Invalid reverse flag or cosine threshold")
        if not math.isfinite(max_warpage_degrees) or not 0 <= max_warpage_degrees < 90:
            raise ValueError("Warpage threshold must be finite and in0..90 degrees (90 excluded)")
        if normal_direction is not None:
            normal_direction = numbers(normal_direction, 3, "normal_direction")
            scale = max(abs(v) for v in normal_direction)
            if scale == 0:
                raise ValueError("Nonzero normal direction required")
            unit = np.asarray(normal_direction) / scale
            direction = (unit / np.linalg.norm(unit)).tolist()
        else:
            direction = None
        if (element_ids is None) == (selection_job is None):
            raise ValueError("Provide exactly one element_ids or selection_job")
        kind = "solid" if source == "solid_exterior" else "shell"
        manager = self._session_manager()
        old_state = None
        if selection_job is not None:
            members, old_state, selection_job = selection_source(manager, session_id, selection_job, kind)
        else:
            ids(element_ids, "element_ids", 20000)
            members = sorted(element_ids)
        baseline, context = {}, {}
        Deck, kw = api()

        def precheck(state):
            if selection_job is not None:
                selection_source(manager, session_id, selection_job, kind)
                if mesh_signature(old_state) != mesh_signature(state):
                    raise ValueError("Selection geometry is stale; select again")
            if set(state["registry_matches"]) != set(members):
                raise ValueError("Unknown selected elements")

        def preflight(path):
            baseline.update(inspect_cards(path))
            if ("segment", set_id) in baseline["sets"]:
                raise ValueError("Segment set ID already exists")
            if any(n.startswith("*SET_SEGMENT") for n, _ in baseline["unresolved"]):
                raise ValueError("Resolve unsupported Segment-set variants before creating this set")
            records, audit = build_segments(path, source, members, direction, cosine_min, reverse, max_warpage_degrees)
            context.update(records=records, audit=audit)

        def commands(state, directory):
            import pandas as pd

            card = kw.SetSegment(sid=set_id, its=0)
            card.title = title
            rows = []
            for record in context["records"]:
                nodes = record["node_ids"]
                expanded = nodes + ([0, 0] if len(nodes) == 2 else [nodes[-1]] if len(nodes) == 3 else [])
                rows.append(dict(zip(("n1", "n2", "n3", "n4", "a1", "a2", "a3", "a4"), expanded + record["attributes"])))
            card.segments = pd.DataFrame(rows)
            fragment = Deck()
            fragment.append(card)
            path = directory / "segment-set.k"
            fragment.export_file(str(path))
            atomic_json(directory / "segment-geometry.json", dict(source=source, length_unit=length_unit,
                        reverse=reverse, normal_direction=normal_direction, cosine_min=cosine_min,
                        coordinate_source="fresh native keyword export", segments=context["audit"]))
            context["geometry_report"] = str(directory / "segment-geometry.json")
            return ["import keyword " + command_path(path)]

        def postcheck(_, path, validation):
            target = dict(entity_type="segment", set_id=set_id, title=title, segments=context["records"],
                          attributes=[0.0]*4, solver="MECH", its=0)
            result = verify_cards(baseline, inspect_cards(path), new_set=target)
            validation.update(set_id=set_id, segment_count=len(context["records"]), source=source,
                              geometry_report=context["geometry_report"], length_unit=length_unit,
                              total_measure=sum(r["measure"] for r in context["audit"]),
                              measure_dimension=1 if source == "shell_boundary_2d" else 2)
            return result

        return self._gui_mesh_edit(session_id, "create_gui_segment_set",
            dict(set_id=set_id, title=title, source=source, length_unit=length_unit, element_ids=element_ids,
                 selection_job=selection_job, normal_direction=normal_direction, cosine_min=cosine_min,
                 reverse=reverse, max_warpage_degrees=max_warpage_degrees),
            commands, stable_scene, precheck, postcheck, preflight,
            snapshot_parameters=dict(entity_type=kind, entity_ids=members, visibility_readback=True,
                                     allow_missing_entity_ids=True))
