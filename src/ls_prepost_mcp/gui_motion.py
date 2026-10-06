"""Selection-driven prescribed nodal motion with native card/curve readback."""

import math

from pydantic import StrictFloat, StrictInt

from .boundary_cards import inspect_boundary_cards, verify_boundary_delta
from .config import command_path
from .core.validation import integer
from .deck_backend import api
from .entity_cards import check_motion_conflicts, inspect_cards, set_members
from .gui_boundaries import require_unit
from .gui_entities import entity_title, selection_source, stable_scene
from .gui_mesh import verify_mesh_digest
from .gui_selection import mesh_signature
from .jobs import atomic_json
from .post_backend import ids

AXES = {"x": 1, "y": 2, "z": 3, "rx": 5, "ry": 6, "rz": 7}
MOTIONS = {"velocity": 0, "acceleration": 1, "displacement": 2}


def validate_time_curve(curve):
    if curve["dattyp"] != 0 or (curve["sfa"] or 1.0) <= 0:
        raise ValueError(
            "Motion reuse requires a general time-compatible curve and positive effective abscissa scale"
        )
    points = curve["points"]
    if len(points) < 2 or any(points[i][0] <= points[i - 1][0] for i in range(1, len(points))):
        raise ValueError("Existing curve does not have increasing time samples")


class GuiMotionTools:
    def create_gui_prescribed_motion(
        self,
        session_id: str,
        motion_id: StrictInt,
        title: str,
        axis: str,
        motion: str,
        curve_id: StrictInt,
        time_unit: str,
        length_unit: str,
        node_set_id: StrictInt | None = None,
        node_ids: list[StrictInt] | None = None,
        selection_job: str | None = None,
        points: list[list[StrictFloat]] | None = None,
        curve_title: str | None = None,
        scale: StrictFloat = 1.0,
        birth: StrictFloat = 0.0,
        death: StrictFloat = 1e28,
        append_to_group: bool = False,
    ) -> dict:
        """Create global NODE_ID/SET_ID prescribed displacement, velocity or acceleration on x/y/z/rx/ry/rz. Exactly one node-set SID, node-ID list or verified node selection. New curve points are [relative time,motion value] in declared deck units (radians for rotation); omit points/title to reuse an existing native curve. BIRTH shifts the curve's time origin; DEATH=0 means native1e28 default. motion_id is a grouping ID shared by this call's nodes, not required unique by LS-DYNA; explicit append_to_group allows an existing same-title group. Reject SPC/same-DOF overlap, unresolved variants and stale selection. No implicit unit conversion, rigid/local/vector/IGA variants, rotational-DOF eligibility or solver certification. Commas in motion headings are rejected because this native importer alters them."""

        integer(motion_id, "motion_id")
        integer(curve_id, "curve_id")
        title = entity_title(title)
        if "," in title:
            raise ValueError(
                "Native prescribed-motion headings with commas are not preserved; use a comma-free title"
            )
        if axis not in AXES or motion not in MOTIONS:
            raise ValueError("Choose global x/y/z/rx/ry/rz and displacement/velocity/acceleration")
        if type(append_to_group) is not bool:
            raise ValueError("append_to_group must be boolean")
        time_unit = require_unit(time_unit, (0, 0, 1))
        length_unit = require_unit(length_unit, (1, 0, 0))
        if sum(v is not None for v in (node_set_id, node_ids, selection_job)) != 1:
            raise ValueError("Provide exactly one node_set_id, node_ids or node selection_job")
        for value in (scale, birth, death):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Motion scale/birth/death must be finite numbers")
        effective_death = death or 1e28
        if birth < 0 or effective_death <= birth:
            raise ValueError(
                "Motion requires nonnegative birth and death later than birth (0=unbounded default)"
            )
        manager = self._session_manager()
        selected_state = None
        if node_set_id is not None:
            integer(node_set_id, "node_set_id")
            members = []
        elif selection_job is not None:
            members, selected_state, selection_job = selection_source(
                manager, session_id, selection_job, "node"
            )
        else:
            ids(node_ids, "node_ids", 20000)
            members = sorted(node_ids)
        if node_set_id is None:
            ids(members, "target nodes", 20000)
        if points is not None:
            curve_title = entity_title(curve_title)
            if not isinstance(points, list) or not 2 <= len(points) <= 10000:
                raise ValueError("Provide2..10000 time-motion points")
            for i, row in enumerate(points):
                if (
                    not isinstance(row, list)
                    or len(row) != 2
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in row)
                    or i
                    and row[0] <= points[i - 1][0]
                ):
                    raise ValueError(
                        "Motion curve requires finite pairs and strictly increasing relative times"
                    )
        elif curve_title is not None:
            raise ValueError("curve_title only applies when creating a new curve")
        Deck, kw = api()
        fragment = Deck()
        expected_curve = None
        if points is not None:
            import pandas as pd

            curve = kw.DefineCurve(lcid=curve_id, sidr=0)
            curve.title = curve_title
            curve.curves = pd.DataFrame(points, columns=["a1", "o1"])
            fragment.append(curve)
            expected_curve = dict(
                curve_id=curve_id,
                title=curve_title,
                sidr=0,
                sfa=1.0,
                sfo=1.0,
                offa=0.0,
                offo=0.0,
                dattyp=0,
                lcint=0,
                points=points,
            )
        expected = []
        for target in [node_set_id] if node_set_id is not None else members:
            card = (
                kw.BoundaryPrescribedMotionSet(nsid=target)
                if node_set_id is not None
                else kw.BoundaryPrescribedMotionNode(nid=target)
            )
            card.id = motion_id
            card.heading = title
            card.dof = AXES[axis]
            card.vad = MOTIONS[motion]
            card.lcid = curve_id
            card.sf = scale
            card.vid = 0
            card.birth = birth
            card.death = effective_death
            fragment.append(card)
            expected.append(
                dict(
                    target_type="node_set" if node_set_id is not None else "node",
                    target_id=target,
                    motion_id=motion_id,
                    title=title,
                    dof=AXES[axis],
                    vad=MOTIONS[motion],
                    curve_id=curve_id,
                    scale=scale,
                    vector_id=0,
                    birth=birth,
                    death=effective_death,
                )
            )
        baseline, state_before, curve_info = {}, {}, {}

        def precheck(state):
            state_before.update(state)
            if selection_job is not None:
                selection_source(manager, session_id, selection_job, "node")
                if (
                    mesh_signature(state) != mesh_signature(selected_state)
                    or state["current_state"] != selected_state["current_state"]
                ):
                    raise ValueError("Selection geometry/state is stale; select again")

        def preflight(path):
            entities = inspect_cards(path)
            baseline.update(inspect_boundary_cards(path, include_motions=True))
            if node_set_id is not None:
                members.extend(set_members(entities, "node", node_set_id))
            ids(members, "target nodes", 20000)
            check_motion_conflicts(entities, members, AXES[axis])
            group = [m for m in entities["motions"] if m["motion_id"] == motion_id]
            if group and (not append_to_group or any(m["title"] != title for m in group)):
                raise ValueError(
                    "Motion group already exists; explicit same-title append_to_group is required"
                )
            if append_to_group and not group:
                raise ValueError("Cannot append to a missing prescribed-motion group")
            if any(name.startswith("*DEFINE_CURVE") for name, _ in baseline["unresolved"]):
                raise ValueError("Resolve unsupported curve variants before prescribing motion")
            if points is not None:
                if curve_id in baseline["namespace_ids"]:
                    raise ValueError("Curve ID collides with curve/table/function namespace")
                curve_info.update(expected_curve)
            else:
                if curve_id not in baseline["curves"]:
                    raise ValueError("Requested existing native curve is missing or unsupported")
                curve_info.update(baseline["curves"][curve_id])
                validate_time_curve(curve_info)
            registered = manager.dispatch(
                session_id,
                "gui_mesh_digest",
                dict(entity_type="node", entity_ids=members, allow_missing_entity_ids=True),
            )
            if registered["status"] != "succeeded":
                raise ValueError("Native target-node registry could not be read")
            verify_mesh_digest(state_before, registered["data"])
            if set(registered["data"]["registry_matches"]) != set(members):
                raise ValueError("Motion references unknown current-model nodes")

        def commands(state, directory):
            path = directory / "prescribed-motion.k"
            fragment.export_file(str(path))
            return ["import keyword " + command_path(path)]

        def postcheck(_, path, verification):
            actual = inspect_boundary_cards(path, include_motions=True)
            audit = verify_boundary_delta(baseline, actual, curve=expected_curve, motions=expected)
            records = audit.pop("actual_motions")
            readback = path.parent / "prescribed-motion-readback.json"
            atomic_json(readback, dict(motions=records, curve=actual["curves"][curve_id], node_ids=members))
            base_unit = "rad" if axis.startswith("r") else length_unit
            unit = (
                base_unit
                if motion == "displacement"
                else base_unit + "/" + time_unit + ("^2" if motion == "acceleration" else "")
            )
            verification.update(
                motion_id=motion_id,
                title=title,
                axis=axis,
                motion=motion,
                created_motion_count=len(records),
                affected_node_count=len(members),
                curve_id=curve_id,
                curve_created=points is not None,
                curve_point_count=len(curve_info["points"]),
                readback=str(readback),
                time_unit=time_unit,
                length_unit=length_unit,
                value_unit=unit,
                scale=scale,
                birth=birth,
                death=effective_death,
                time_semantics="BIRTH shifts the prescribed curve time origin; existing curve scale/offset remain unchanged",
                unit_labels_verified_against_model=False,
                rotational_dof_eligibility_verified=False,
            )
            return audit

        return self._gui_mesh_edit(
            session_id,
            "create_gui_prescribed_motion",
            dict(
                motion_id=motion_id,
                title=title,
                axis=axis,
                motion=motion,
                curve_id=curve_id,
                time_unit=time_unit,
                length_unit=length_unit,
                node_set_id=node_set_id,
                node_ids=node_ids,
                selection_job=selection_job,
                points=points,
                curve_title=curve_title,
                scale=scale,
                birth=birth,
                death=death,
                append_to_group=append_to_group,
            ),
            commands,
            stable_scene,
            precheck,
            postcheck,
            preflight,
            snapshot_parameters=dict(visibility_readback=True),
        )
