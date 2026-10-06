"""Selection/set-driven concentrated force and moment creation."""

import math

from pydantic import StrictFloat, StrictInt

from .boundary_cards import inspect_boundary_cards, verify_boundary_delta
from .core.validation import integer
from .deck_backend import api
from .entity_cards import check_motion_conflicts, inspect_cards, set_members
from .gui_boundaries import require_unit
from .gui_entities import entity_title, selection_source, stable_scene
from .gui_mesh import verify_mesh_digest
from .gui_motion import validate_time_curve
from .gui_selection import mesh_signature
from .jobs import atomic_json
from .native import commands as nc
from .nodal_load_cards import LOAD_AXES, distribution_scale, load_overlap
from .post_backend import ids


class GuiNodalLoadTools:
    def create_gui_nodal_load(
        self,
        session_id: str,
        axis: str,
        curve_id: StrictInt,
        time_unit: str,
        value_unit: str,
        distribution: str,
        node_set_id: StrictInt | None = None,
        node_ids: list[StrictInt] | None = None,
        selection_job: str | None = None,
        points: list[list[StrictFloat]] | None = None,
        curve_title: str | None = None,
        scale: StrictFloat = 1.0,
        allow_superposition: bool = False,
    ) -> dict:
        """Create native LOAD_NODE_POINT/SET with a new or existing curve. Choose global x/y/z force or rx/ry/rz moment and explicit units. distribution='per_node' applies curve*scale to EACH node (SET stays linked); 'total_equal' divides by current membership and writes POINT records, freezing nodes so later set edits cannot change total. Exactly one node_set_id/node_ids/selection_job. Overlapping global same-DOF nodal loads require allow_superposition; local/follower ambiguity rejects. Existing prescribed motion/SPC is reported, not silently removed. No solver, rigid/follower/local frames or rotational eligibility certification. Native import/save, mesh/display/card verification and recording replay included."""

        integer(curve_id, "curve_id")
        if axis not in LOAD_AXES or distribution not in ("per_node", "total_equal"):
            raise ValueError("Choose x/y/z/rx/ry/rz and per_node or total_equal distribution")
        if type(allow_superposition) is not bool:
            raise ValueError("allow_superposition must be boolean")
        if type(scale) not in (int, float) or not math.isfinite(scale) or scale == 0:
            raise ValueError("Provide a finite nonzero load scale")
        time_unit = require_unit(time_unit, (0, 0, 1))
        value_unit = require_unit(value_unit, (2, 1, -2) if axis.startswith("r") else (1, 1, -2))
        if sum(v is not None for v in (node_set_id, node_ids, selection_job)) != 1:
            raise ValueError("Provide exactly one node_set_id, node_ids or selection_job")
        if node_set_id is not None:
            integer(node_set_id, "node_set_id")
        if node_ids is not None:
            ids(node_ids, "node_ids", 20000)
        if points is not None:
            curve_title = entity_title(curve_title)
            if not isinstance(points, list) or not 2 <= len(points) <= 10000:
                raise ValueError("Provide2..10000 time-load points")
            for i, row in enumerate(points):
                if (
                    not isinstance(row, list)
                    or len(row) != 2
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in row)
                    or i
                    and row[0] <= points[i - 1][0]
                ):
                    raise ValueError("Load curve requires finite pairs and strictly increasing time")
        elif curve_title is not None:
            raise ValueError("curve_title only applies to a new curve")
        manager = self._session_manager()
        selected_state = None
        if selection_job is not None:
            members, selected_state, selection_job = selection_source(
                manager, session_id, selection_job, "node"
            )
        else:
            members = sorted(node_ids) if node_ids is not None else []
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
        baseline, state_before, curve_info, contract = {}, {}, {}, {}
        expected = []

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
            baseline.update(inspect_boundary_cards(path, include_nodal_loads=True))
            if node_set_id is not None:
                members.extend(set_members(entities, "node", node_set_id))
            ids(members, "target nodes", 20000)
            if any(n.startswith(("*LOAD_NODE", "*DEFINE_CURVE")) for n, _ in baseline["unresolved"]):
                raise ValueError("Resolve unsupported nodal-load/curve variants before creating loads")
            overlaps = load_overlap(baseline["nodal_loads"], entities, members, LOAD_AXES[axis])
            if overlaps and not allow_superposition:
                raise ValueError("Same-DOF nodal load overlap; explicitly allow_superposition to add loads")
            constraint_note = None
            try:
                check_motion_conflicts(entities, members, LOAD_AXES[axis])
            except ValueError as exc:
                # A force on a constrained node can intentionally create a
                # reaction. Report this instead of changing the user's physics.
                constraint_note = str(exc)
            contract.update(overlap_record_count=len(overlaps), constraint_review=constraint_note)
            if points is not None:
                if curve_id in baseline["namespace_ids"]:
                    raise ValueError("Curve ID collides with curve/table/function namespace")
                curve_info.update(expected_curve)
            else:
                if curve_id not in baseline["curves"]:
                    raise ValueError("Requested existing curve is missing or unsupported")
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
                raise ValueError("Load references unknown current-model nodes")

        def commands(state, directory):
            import pandas as pd

            per_node_scale = distribution_scale(scale, len(members), distribution)
            linked_set = node_set_id is not None and distribution == "per_node"
            targets = [node_set_id] if linked_set else members
            expected.extend(
                dict(
                    target_type="node_set" if linked_set else "node",
                    target_id=n,
                    dof=LOAD_AXES[axis],
                    curve_id=curve_id,
                    scale=per_node_scale,
                    coordinate_system=0,
                    m1=0,
                    m2=0,
                    m3=0,
                )
                for n in targets
            )
            if linked_set:
                fragment.append(
                    kw.LoadNodeSet(nsid=node_set_id, dof=LOAD_AXES[axis], lcid=curve_id, sf=per_node_scale)
                )
            else:
                card = kw.LoadNodePoint()
                card.nodes = pd.DataFrame(
                    [
                        dict(
                            nid=n,
                            dof=LOAD_AXES[axis],
                            lcid=curve_id,
                            sf=per_node_scale,
                            cid=0,
                            m1=0,
                            m2=0,
                            m3=0,
                        )
                        for n in members
                    ]
                )
                fragment.append(card)
            contract.update(
                per_node_scale=per_node_scale,
                summed_scale=per_node_scale * len(members),
                set_membership_linked=linked_set,
            )
            path = directory / "nodal-load.k"
            fragment.export_file(str(path))
            return [nc.import_keyword(path)]

        def postcheck(_, path, verification):
            actual = inspect_boundary_cards(path, include_nodal_loads=True)
            audit = verify_boundary_delta(baseline, actual, curve=expected_curve, nodal_loads=expected)
            records = audit.pop("actual_nodal_loads")
            readback = path.parent / "nodal-load-readback.json"
            atomic_json(readback, dict(loads=records, curve=actual["curves"][curve_id], node_ids=members))
            verification.update(
                contract,
                axis=axis,
                quantity="moment" if axis.startswith("r") else "force",
                distribution=distribution,
                time_unit=time_unit,
                value_unit=value_unit,
                curve_id=curve_id,
                curve_created=points is not None,
                affected_node_count=len(members),
                created_load_count=len(records),
                readback=str(readback),
                unit_labels_verified_against_model=False,
                rotational_dof_eligibility_verified=False,
                semantics="Curve values in declared deck units; no conversion. SET applies per-node; total_equal freezes current nodes into POINT cards.",
            )
            return audit

        return self._gui_mesh_edit(
            session_id,
            "create_gui_nodal_load",
            dict(
                axis=axis,
                curve_id=curve_id,
                time_unit=time_unit,
                value_unit=value_unit,
                distribution=distribution,
                node_set_id=node_set_id,
                node_ids=node_ids,
                selection_job=selection_job,
                points=points,
                curve_title=curve_title,
                scale=scale,
                allow_superposition=allow_superposition,
            ),
            commands,
            stable_scene,
            precheck,
            postcheck,
            preflight,
            snapshot_parameters=dict(visibility_readback=True),
        )
