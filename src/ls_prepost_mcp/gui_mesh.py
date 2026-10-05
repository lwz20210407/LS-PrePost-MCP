"""Visible native mesh edits with before/after topology and coordinate verification."""

import itertools
import math
from pathlib import Path

import numpy as np
from pydantic import StrictFloat, StrictInt

from .config import command_path
from .jobs import atomic_json, check_artifact
from .native import commands as nc


class ReadOnlyScopeMismatch(ValueError):
    """Geometry was verified unchanged, but selection/state postconditions failed."""


def verify_mesh_digest(before, after, allow_selected_coordinates=False, allow_normal_reversal=False):
    """Reject mismatched scopes; hash equality verifies full unchanged populations."""
    if (before.get("digest_contract") != "native_registry_order_sha256_v1"
            or after.get("digest_contract") != before["digest_contract"]
            or before.get("digest_node_ids") != after.get("digest_node_ids")
            or before.get("counts") != after.get("counts")
            or before.get("part_ids") != after.get("part_ids")):
        raise ValueError("Native mesh digest scope or model inventory changed")
    required = {"node_ids", "connectivity", "part_membership", "unselected_coordinates"}
    if allow_normal_reversal:
        if (before.get("normal_scope") is None or before.get("normal_scope") != after.get("normal_scope")
                or before.get("normal_count", 0) < 1 or before["normal_count"] != after.get("normal_count")):
            raise ValueError("Native normal verification scope changed")
        required.remove("connectivity")
        required.add("unselected_connectivity")
    if not allow_selected_coordinates:
        required.add("coordinates")
    for key in required:
        a = before.get("mesh_digest", {}).get(key)
        b = after.get("mesh_digest", {}).get(key)
        if not isinstance(a, str) or len(a) != 64 or a != b:
            raise ValueError("Native operation changed " + key + " or digest is unavailable")


def mesh_index(state):
    nodes = {int(n[0]): np.asarray(n[1:], dtype=float) for n in state["nodes"]}
    elements = {(e["type"], e["id"]): tuple(e["nodes"]) for e in state["elements"]}
    if len(nodes) != len(state["nodes"]) or len(elements) != len(state["elements"]):
        raise ValueError("Native mesh contains duplicate user IDs")
    if any(x.shape != (3,) or not np.isfinite(x).all() for x in nodes.values()):
        raise ValueError("Invalid native coordinates")
    if any(n and n not in nodes for conn in elements.values() for n in conn):
        raise ValueError("Native connectivity references a missing node")
    return nodes, elements


def check_same_nodes(before, after):
    if before.keys() != after.keys() or any(
        not np.allclose(x, after[k], rtol=1e-7, atol=1e-8) for k, x in before.items()
    ):
        raise ValueError("Native operation unexpectedly changed nodes/coordinates")


def check_same_parts(before, after):
    if set(before["part_ids"]) != set(after["part_ids"]):
        raise ValueError("Native operation changed the part registry")
    a = {k: sorted(v) for k, v in before.get("part_elements", {}).items()}
    b = {k: sorted(v) for k, v in after.get("part_elements", {}).items()}
    if a != b:
        raise ValueError("Native operation changed element part membership")


def check_no_collapse(nodes, elements, tolerance):
    for (kind, eid), connectivity in elements.items():
        unique = set(n for n in connectivity if n)
        for a, b in itertools.combinations(unique, 2):
            if np.linalg.norm(nodes[a] - nodes[b]) <= tolerance:
                raise ValueError("Merge may collapse {} {} within the requested tolerance".format(kind, eid))


def verify_merge(before, after, tolerance):
    old, old_elements = mesh_index(before)
    new, new_elements = mesh_index(after)
    if not new.keys() <= old.keys() or old_elements.keys() != new_elements.keys():
        raise ValueError("Native merge added IDs or removed elements")
    check_same_parts(before, after)
    check_same_nodes({k: old[k] for k in new}, new)
    cells = {}
    for uid, xyz in new.items():
        scaled = xyz / tolerance
        if not np.isfinite(scaled).all():
            raise ValueError("Coordinate/tolerance ratio exceeds numeric range")
        key = tuple(math.floor(float(v)) for v in scaled)
        for delta in itertools.product((-1, 0, 1), repeat=3):
            for other in cells.get(tuple(key[i] + delta[i] for i in range(3)), []):
                if np.linalg.norm(xyz - new[other]) <= tolerance:
                    raise ValueError("Duplicate nodes remain after the native merge")
        cells.setdefault(key, []).append(uid)
    mapping = {}
    for uid in old.keys() - new.keys():
        key = tuple(math.floor(float(v)) for v in old[uid] / tolerance)
        candidates = []
        for delta in itertools.product((-1, 0, 1), repeat=3):
            candidates.extend(cells.get(tuple(key[i] + delta[i] for i in range(3)), []))
        matches = [v for v in candidates if np.linalg.norm(old[uid] - new[v]) <= tolerance * (1 + 1e-7)]
        if not matches or min(matches) > uid:
            raise ValueError("Removed node has no lower-ID survivor within tolerance")
        mapping[uid] = min(matches)
    for key, connectivity in old_elements.items():
        expected = tuple(mapping.get(n, n) for n in connectivity)
        if new_elements[key] != expected:
            raise ValueError("Native merge connectivity does not match node remapping")
    return dict(
        removed_count=len(mapping),
        node_map={str(k): v for k, v in mapping.items()},
        preserved_elements=len(new_elements),
        scope="Native node coordinates, IDs, connectivity and part registry; other keyword references require separate checks",
    )


def cyclic_equal(a, b):
    return len(a) == len(b) and any(a == b[i:] + b[:i] for i in range(len(b)))


def shell_cycle(conn):
    values = list(conn)
    if len(values) == 4 and values[3] in (0, values[2]):
        values = values[:3]
    if len(values) not in (3, 4) or not all(values) or len(set(values)) != len(values):
        raise ValueError("Unsupported repeated-node shell topology")
    return values


def verify_reverse(before, after, selected=None):
    if "mesh_digest" in before or "mesh_digest" in after:
        verify_mesh_digest(before, after, allow_normal_reversal=True)
        scope = before["normal_scope"]["shell_ids"]
        if (scope is None) != (selected is None) or scope is not None and set(scope) != set(selected):
            raise ValueError("Normal digest does not cover the requested shells")
        if before["mesh_digest"]["normal_reversed"] != after["mesh_digest"]["normal_current"]:
            raise ValueError("Shell cyclic connectivity was not reversed exactly")
        if before.get("part_visibility") != after.get("part_visibility"):
            raise ValueError("Normal reversal did not restore part visibility")
        return dict(reversed_shells=before["normal_count"],
                    verification="All requested shell cyclic orientations reversed; every coordinate, unselected connectivity and part membership preserved via complete native scans")
    old, old_elements = mesh_index(before)
    new, new_elements = mesh_index(after)
    check_same_nodes(old, new)
    check_same_parts(before, after)
    if old_elements.keys() != new_elements.keys() or set(before["part_ids"]) != set(after["part_ids"]):
        raise ValueError("Normal reversal unexpectedly changed entity registries")
    reversed_count = 0
    shells = {eid for kind, eid in old_elements if kind == "shell"}
    selected = shells if selected is None else set(selected)
    if not selected or not selected <= shells:
        raise ValueError("No shells or unknown selected shell IDs")
    for key, conn in old_elements.items():
        actual = new_elements[key]
        if key[0] != "shell":
            if actual != conn:
                raise ValueError("Normal reversal altered a non-shell element")
            continue
        if key[1] not in selected:
            if actual != conn:
                raise ValueError("Normal reversal altered an unselected shell")
            continue
        a = shell_cycle(conn)
        b = shell_cycle(actual)
        if len(a) not in (3, 4) or not cyclic_equal(list(reversed(a)), b):
            raise ValueError("Shell connectivity was not reversed")
        reversed_count += 1
    if reversed_count == 0:
        raise ValueError("No shell elements to reverse")
    return dict(
        reversed_shells=reversed_count,
        verification="Reversed cyclic connectivity; all node coordinates and unselected connectivity preserved",
    )


def verify_transform(before, after, selected, transform):
    if "mesh_digest" in before or "mesh_digest" in after:
        verify_mesh_digest(before, after, allow_selected_coordinates=True)
        if set(before["digest_node_ids"]) != set(selected):
            raise ValueError("Transform verification excludes the wrong node set")
    if before.get("part_visibility") != after.get("part_visibility"):
        raise ValueError("Transform did not preserve part visibility")
    old, old_elements = mesh_index(before)
    new, new_elements = mesh_index(after)
    if (
        old.keys() != new.keys()
        or old_elements != new_elements
        or set(before["part_ids"]) != set(after["part_ids"])
    ):
        raise ValueError("Native coordinate transform unexpectedly changed topology")
    check_same_parts(before, after)
    if not selected or not set(selected) <= old.keys():
        raise ValueError("Unknown/empty native node selection")
    error = 0.0
    for uid, xyz in old.items():
        expected = np.asarray(transform(xyz), float) if uid in selected else xyz
        if not np.allclose(expected, new[uid], rtol=1e-6, atol=1e-6):
            raise ValueError("Native transform did not change exactly the requested coordinates")
        error = max(error, float(np.max(np.abs(expected - new[uid]))))
    return dict(
        transformed_nodes=len(selected),
        maximum_coordinate_error=error,
        verification="All selected/unselected coordinates and all connectivity checked; mesh quality/loads/material axes are a separate scope",
    )


class GuiMeshTools:
    def set_gui_node_coordinates(
        self, session_id: str, nodes: list[dict], units: str, tolerance: StrictFloat = 1e-6
    ) -> dict:
        """Set absolute global coordinates of 1..100 existing nodes through native translations. Each row has id and coordinates=[x,y,z]; null preserves that axis. Verifies every node/topology and part visibility, with edit checkpoints. Does not project to CAD or move load/material axes; follow with quality checks."""
        from .gui_node_edit import set_coordinates

        return set_coordinates(self, session_id, nodes, units, tolerance)

    def _visible_mesh_session(self, session_id, manager, allow_results=False):
        meta = manager.read(session_id)
        kinds = ("keyword", "d3plot") if allow_results else ("keyword",)
        if not meta["process_alive"] or meta["state"] != "ready" or meta["model_kind"] not in kinds:
            raise ValueError(
                "A ready owned "
                + ("keyword/result" if allow_results else "keyword")
                + " GUI session is required"
            )
        if meta.get("bridge_protocol", 1) < 3:
            raise ValueError("Start a new GUI session for the verified mesh bridge")
        return meta

    def inspect_gui_mesh(
        self, session_id: str, include_entities: bool = False,
        entity_type: str | None = None, offset: StrictInt = 0, limit: StrictInt = 1000,
    ) -> dict:
        """Read native reference mesh. Specify entity_type=node/shell/solid/beam for a bounded page (0-based offset, limit1..5000) without the legacy whole-model20000 cap. Pages return entities and next_offset; stable native registry order, not sorted user IDs. No deformed/alive-only filter or cross-call snapshot guarantee. With entity_type=None retain legacy full snapshot, at most20000 nodes/elements."""
        if entity_type not in (None, "node", "shell", "solid", "beam"):
            raise ValueError("Unsupported mesh page entity_type")
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 5000:
            raise ValueError("Mesh page offset must be nonnegative and limit an integer from 1 to 5000")
        if entity_type is None and (offset != 0 or limit != 1000):
            raise ValueError("Specify entity_type when requesting a mesh page")
        manager = self._session_manager()
        with manager.lock(session_id):
            meta = self._visible_mesh_session(session_id, manager, allow_results=True)
            paged = entity_type is not None
            result = manager.dispatch(
                session_id, "gui_mesh_page" if paged else "gui_mesh_state",
                dict(entity_type=entity_type, offset=offset, limit=limit) if paged else {},
            )
            if result["status"] == "succeeded":
                result["data"].update(model_kind=meta["model_kind"], coordinate_configuration="reference")
                codes = result["data"].get("selection_types")
                if codes and any(code < 0 or code > 4096 for code in codes):
                    result["data"]["selection_types"] = None
                    result["data"]["warnings"].append(
                        "Native selection-type array is invalid on this binding; not used for entity interpretation"
                    )
                path = Path(result["job_directory"]) / "mesh.json"
                atomic_json(path, result["data"])
                result["artifacts"] = [check_artifact(path, "json")]
                if not include_entities and not paged:
                    result["data"] = {
                        k: v
                        for k, v in result["data"].items()
                        if k not in ("nodes", "elements", "part_elements", "selection_ids", "selection_types")
                    }
                atomic_json(Path(result["job_directory"]) / "operation.json", result)
            return result

    def inspect_gui_mesh_quality(
        self,
        session_id: str,
        units: str,
        max_aspect: float = 10.0,
        max_warpage: float = 15.0,
        min_scaled_jacobian: float = 0.2,
        fail_on_issues: bool = False,
    ) -> dict:
        """Read the current GUI mesh and calculate explicit geometric quality metrics. This is native readback plus geometry math, not LS-PrePost's complete Model Checking panel."""
        from .mesh_quality import quality
        from .service import unit_label

        unit_label(units)
        if (
            not all(math.isfinite(v) for v in (max_aspect, max_warpage, min_scaled_jacobian))
            or max_aspect < 1
            or not 0 <= max_warpage <= 180
            or not -1 <= min_scaled_jacobian <= 1
        ):
            raise ValueError("Invalid mesh quality thresholds")
        result = self.inspect_gui_mesh(session_id, include_entities=True)
        if result["status"] != "succeeded":
            return result
        report = quality(
            result["data"]["nodes"], result["data"]["elements"], max_aspect, max_warpage, min_scaled_jacobian
        )
        report.update(
            backend="lsprepost-readback+geometry-math",
            units=units,
            native_model_check=False,
            coordinate_configuration="reference",
            model_kind=result["data"].get("model_kind"),
        )
        path = Path(result["job_directory"]) / "quality.json"
        atomic_json(path, report)
        result["artifacts"].append(check_artifact(path, "json"))
        result["data"] = {
            k: v for k, v in report.items() if k not in ("elements", "unsupported", "orphan_nodes")
        }
        if fail_on_issues and not report["valid_within_scope"]:
            result.update(
                status="failed", error=dict(message="Mesh quality requirements not met; see report")
            )
        atomic_json(Path(result["job_directory"]) / "operation.json", result)
        return result

    def _gui_mesh_edit(
        self,
        session_id,
        action,
        parameters,
        commands,
        verify,
        precheck=None,
        postcheck=None,
        preflight=None,
        on_verified=None,
        transaction_kind="edit",
        snapshot_parameters=None,
        finalize_native=None,
        prepare_snapshot=None,
    ):
        if transaction_kind not in ("edit", "selection", "inspection"):
            raise ValueError("Unsupported GUI transaction kind")
        mutates_model = transaction_kind == "edit"
        if not mutates_model and (preflight or postcheck):
            raise ValueError("Keyword-file pre/post checks require an edit checkpoint")
        artifacts = (("model.k", "keyword"),) if mutates_model else ()
        snapshot_action = "gui_mesh_state" if snapshot_parameters is None else "gui_mesh_digest"
        snapshot_parameters = {} if snapshot_parameters is None else snapshot_parameters
        manager = self._session_manager()
        with manager.lock(session_id):
            original_meta = self._visible_mesh_session(
                session_id, manager, allow_results=transaction_kind == "selection"
            )
            if prepare_snapshot is not None:
                # Resolve model-owned sources under the same request lock used by
                # selection. No interleaving MCP model/set mutation is permitted.
                preparation = prepare_snapshot(manager, session_id, snapshot_parameters)
                if preparation is not None:
                    return preparation
            baseline = manager.dispatch(
                session_id, snapshot_action, snapshot_parameters, artifacts=artifacts, export=mutates_model
            )
            if baseline["status"] != "succeeded":
                return baseline
            before = baseline["data"]
            before["model_kind"] = original_meta["model_kind"]
            if precheck:
                precheck(before)
            checkpoint = (
                baseline["artifacts"][0]["path"] if mutates_model else original_meta.get("last_checkpoint")
            )
            meta = manager.read(session_id)
            if mutates_model:
                meta.update(last_checkpoint=checkpoint, dirty=False)
                manager.save(session_id, meta)
            if preflight:
                preflight(Path(checkpoint))
            try:
                if callable(commands):
                    commands = commands(before, Path(baseline["job_directory"]))
                result = manager.dispatch(
                    session_id,
                    snapshot_action,
                    snapshot_parameters,
                    native_commands=commands,
                    artifacts=artifacts,
                    export=mutates_model,
                )
                if result["status"] == "succeeded" and finalize_native is not None:
                    result = finalize_native(before, result)
            except Exception as exc:
                meta = manager.read(session_id)
                meta.update(
                    state="uncertain", dirty=True if mutates_model else original_meta.get("dirty", False)
                )
                if mutates_model:
                    # A multi-stage edit may reopen a repaired deck, which clears
                    # session caches/checkpoints before host verification finishes.
                    meta["last_checkpoint"] = checkpoint
                manager.save(session_id, meta)
                result = dict(
                    session_id=session_id,
                    status="uncertain" if meta.get("active_request") else "failed",
                    job_directory=baseline["job_directory"],
                    artifacts=[],
                    baseline_checkpoint=checkpoint,
                    error=dict(type=type(exc).__name__, message=str(exc)),
                    transaction_kind=transaction_kind,
                    checkpoint_created=mutates_model,
                )
                atomic_json(Path(baseline["job_directory"]) / "edit-failure.json", result)
                manager.journal(session_id, dict(action=action, parameters=parameters, result=result))
                return result
            directory = Path(result["job_directory"])
            atomic_json(directory / "before.json", before)
            meta = manager.read(session_id)
            meta["dirty"] = True if mutates_model else original_meta.get("dirty", False)
            if result["status"] == "succeeded":
                result["data"]["model_kind"] = original_meta["model_kind"]
                try:
                    validation = verify(before, result["data"])
                    if snapshot_action == "gui_mesh_digest":
                        validation["mesh_verification"] = dict(
                            method="complete_native_scan_sha256_and_requested_coordinates",
                            model_counts=before["counts"],
                            materialized_node_count=len(before["nodes"]),
                            whole_mesh_json=False,
                            scope="Reference geometry/topology/part membership, not all keyword semantics or mesh quality",
                        )
                    if postcheck:
                        validation["reference_checks"] = postcheck(
                            Path(checkpoint), directory / "model.k", validation
                        )
                    atomic_json(directory / "verification.json", validation)
                    result["verification"] = validation
                    result["artifacts"].append(check_artifact(directory / "verification.json", "json"))
                    if mutates_model:
                        meta.update(last_checkpoint=str(directory / "model.k"), dirty=False)
                    if on_verified:
                        on_verified(before, result["data"], meta)
                except Exception as exc:
                    result.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
                    if not mutates_model and isinstance(exc, ReadOnlyScopeMismatch):
                        meta.update(state="ready", dirty=original_meta.get("dirty", False))
                    else:
                        meta["state"] = "uncertain"
                        # Unexpected external/model changes cannot be excluded.
                        meta["dirty"] = True
                        if mutates_model:
                            meta["last_checkpoint"] = checkpoint
            result.update(
                execution_mode=result.get("execution_mode", "visible_gui_native_cfile"),
                baseline_checkpoint=checkpoint,
                transaction_kind=transaction_kind,
                checkpoint_created=mutates_model,
            )
            result["model_generation"] = original_meta.get("model_generation")
            if result.get("data"):
                atomic_json(directory / "after.json", result["data"])
                result["artifacts"].append(check_artifact(directory / "after.json", "json"))
                result["data"] = {
                    k: v
                    for k, v in result["data"].items()
                    if k not in ("nodes", "elements", "part_elements", "selection_ids", "selection_types")
                }
            manager.save(session_id, meta)
            atomic_json(directory / "operation.json", result)
            manager.journal(session_id, dict(action=action, parameters=parameters, result=result))
            return result

    def merge_gui_duplicate_nodes(self, session_id: str, tolerance: float, units: str) -> dict:
        """Native Duplicate Nodes in the same visible GUI; keep lower ID/coordinates, disable element cleanup, verify remapping and preserve a checkpoint. Does not certify all keyword references."""
        from .service import unit_label

        unit_label(units)
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("Positive finite merge tolerance required")
        commands = [
            "pall",
            nc.selection('clear'),
            nc.selection_target('node'),
            "dupnode open 1",
            "dupnode keepnode 1",
            "dupnode keepcenter off",
            "dupnode delunrefnode on",
            "dupnode delelem off",
            "dupnode clean off",
            "dupnode showdup " + repr(tolerance),
            "dupnode merge " + repr(tolerance),
            "dupnode accept",
            "dupnode open 0",
        ]
        return self._gui_mesh_edit(
            session_id,
            "merge_gui_duplicate_nodes",
            dict(tolerance=tolerance, units=units),
            commands,
            lambda a, b: verify_merge(a, b, tolerance),
            lambda state: check_no_collapse(*mesh_index(state), tolerance),
        )

    def replace_gui_node(self, session_id: str, source_node_id: StrictInt, target_node_id: StrictInt,
                         units: str) -> dict:
        """Replace a source node by an existing target through native elemedit, preserving target coordinates. Verify every node/element/part in the bounded snapshot; reject collapse/inversion and overlapping SPCs. Repair supported Node/Segment sets and SPC references in a fresh native-export copy, then natively reopen and verify. Explicit mixed backend, not a promise that native Replace updates references. Standalone standard shell/solid models; legacy20k snapshot bound, unresolved reference-sensitive variants/TC-RC attributes reject. Other keyword references and solver physics are not fully certified."""
        from .node_replacement import replace_node

        return replace_node(self, session_id, source_node_id, target_node_id, units)

    def reverse_gui_shell_normals(
        self, session_id: str, units: str, shell_ids: list[int] | None = None
    ) -> dict:
        """Reverse all or explicit shell normals through native GUI commands; verify reversed connectivity and preserve every unselected element. Native material/coordinate semantics remain separate review scope."""
        from .post_backend import ids
        from .service import unit_label

        unit_label(units)
        if shell_ids is not None:
            ids(shell_ids, "shell_ids", 20000)
        selected = None if shell_ids is None else set(shell_ids)
        commands = [
            "pall",
            nc.selection('clear'),
            nc.selection_target('shell'),
        ]
        commands += (
            [nc.selection('whole')]
            if selected is None
            else [nc.selection_add('shell', uid, 'shell') for uid in sorted(selected)]
        )
        commands += ["normal reverse", nc.selection('clear')]

        def precheck(state):
            if "mesh_digest" in state:
                if state.get("normal_count") is None:
                    raise ValueError("Start a new owned GUI session for the updated normal-verification bridge")
                if state["normal_count"] < 1:
                    raise ValueError("No selected shells")
                return
            _, elements = mesh_index(state)
            shells = {eid for kind, eid in elements if kind == "shell"}
            if not shells or (selected is not None and not selected <= shells):
                raise ValueError("No shells or unknown selected shell IDs")

        return self._gui_mesh_edit(
            session_id,
            "reverse_gui_shell_normals",
            dict(units=units, shell_ids=shell_ids),
            lambda state, directory: commands + ["-m " + pid for pid, active in state["part_visibility"].items() if not active],
            lambda a, b: verify_reverse(a, b, selected),
            precheck,
            snapshot_parameters=dict(normal_scope=dict(shell_ids=shell_ids)),
        )

    def translate_gui_nodes(
        self, session_id: str, node_ids: list[int], offset: list[float], units: str
    ) -> dict:
        """Translate explicit nodes through the same visible GUI native command stream; read back selected/unselected coordinates and preserve a pre-edit checkpoint."""
        from .post_backend import ids
        from .service import numbers, unit_label

        ids(node_ids, "node_ids", 10000)
        offset = numbers(offset, 3, "offset")
        unit_label(units)
        selected = set(node_ids)
        commands = ["pall", nc.selection('clear'), nc.selection_target('node'), nc.selection_transfer(0)]
        commands += [nc.selection_add('node', uid, 'node') for uid in node_ids]
        commands += [
            "translate_model " + " ".join(map(str, offset)),
            "translate_model accept",
            nc.selection('clear'),
        ]

        def precheck(state):
            if not selected <= mesh_index(state)[0].keys():
                raise ValueError("Unknown node IDs")

        return self._gui_mesh_edit(
            session_id,
            "translate_gui_nodes",
            dict(node_ids=node_ids, offset=offset, units=units),
            lambda state, directory: commands + ["-m " + pid for pid, active in state["part_visibility"].items() if not active],
            lambda a, b: verify_transform(a, b, selected, lambda xyz: xyz + offset),
            precheck,
            snapshot_parameters=dict(node_ids=node_ids),
        )

    def rotate_gui_nodes(
        self, session_id: str, node_ids: list[int], axis: str, angle: float, center: list[float], units: str
    ) -> dict:
        """Rotate selected nodes around a global axis through a center in the same visible GUI; verifies all coordinates and topology, with a checkpoint before editing."""
        from .post_backend import ids
        from .service import numbers, unit_label

        ids(node_ids, "node_ids", 10000)
        if axis not in ("x", "y", "z"):
            raise ValueError("Axis must be x, y or z")
        angle = numbers([angle], 1, "angle")[0]
        center = np.asarray(numbers(center, 3, "center"))
        unit_label(units)
        selected = set(node_ids)
        index = {"x": 0, "y": 1, "z": 2}[axis]
        a, b = (index + 1) % 3, (index + 2) % 3
        theta = math.radians(angle)

        def transform(xyz):
            q = xyz - center
            result = q.copy()
            result[a], result[b] = (
                math.cos(theta) * q[a] - math.sin(theta) * q[b],
                math.sin(theta) * q[a] + math.cos(theta) * q[b],
            )
            return result + center

        commands = ["pall", nc.selection('clear'), nc.selection_target('node'), nc.selection_transfer(0)]
        commands += [nc.selection_add('node', uid, 'node') for uid in node_ids]
        commands += [
            "rotate_model " + " ".join(map(str, center)) + " %s %s" % (axis, angle),
            "rotate_model accept 0 0 0",
            nc.selection('clear'),
        ]

        def precheck(state):
            if not selected <= mesh_index(state)[0].keys():
                raise ValueError("Unknown node IDs")

        return self._gui_mesh_edit(
            session_id,
            "rotate_gui_nodes",
            dict(node_ids=node_ids, axis=axis, angle=angle, center=center.tolist(), units=units),
            lambda state, directory: commands + ["-m " + pid for pid, active in state["part_visibility"].items() if not active],
            lambda old, new: verify_transform(old, new, selected, transform),
            precheck,
            snapshot_parameters=dict(node_ids=node_ids),
        )

    def create_gui_nodes(self, session_id: str, nodes: list[dict], units: str) -> dict:
        """Create explicit user-ID nodes by importing a generated NODE fragment into the same visible GUI; existing coordinates/connectivity remain verified unchanged."""
        from .service import integer, numbers, unit_label

        unit_label(units)
        if not isinstance(nodes, list) or not 1 <= len(nodes) <= 1000:
            raise ValueError("Provide 1..1000 new nodes")
        new = {}
        for row in nodes:
            if not isinstance(row, dict) or set(row) != {"id", "coordinates"}:
                raise ValueError("Each node requires id and coordinates")
            uid = integer(row["id"], "node id")
            if uid in new:
                raise ValueError("Duplicate requested node IDs")
            new[uid] = numbers(row["coordinates"], 3, "coordinates")

        def precheck(state):
            old, _ = mesh_index(state)
            if new.keys() & old.keys() or len(new) + len(old) > 20000:
                raise ValueError("New node IDs collide or exceed the GUI verification limit")

        def commands(state, directory):
            fragment = directory / "import-nodes.k"
            lines = (
                ["*KEYWORD", "*NODE"]
                + [str(k) + "," + ",".join(map(str, v)) for k, v in new.items()]
                + ["*END"]
            )
            fragment.write_text("\n".join(lines) + "\n", encoding="ascii")
            return ["import keyword " + command_path(fragment)]

        def verify(before, after):
            old_nodes, old_elems = mesh_index(before)
            after_nodes, after_elems = mesh_index(after)
            if after_nodes.keys() != old_nodes.keys() | new.keys() or old_elems != after_elems:
                raise ValueError("Native node import changed unexpected topology")
            check_same_nodes({**old_nodes, **{k: np.asarray(v) for k, v in new.items()}}, after_nodes)
            check_same_parts(before, after)
            return dict(
                created_node_ids=sorted(new), original_mesh_preserved=True, route="native keyword import"
            )

        return self._gui_mesh_edit(
            session_id, "create_gui_nodes", dict(nodes=nodes, units=units), commands, verify, precheck
        )

    def create_gui_elements(
        self, session_id: str, element_type: str, part_id: int, elements: list[dict], units: str
    ) -> dict:
        """Import explicit tri/quad shells or hex8 solids into an existing native GUI part. Check coordinates, connectivity, IDs and nondegenerate geometry; no material/section inference."""
        from .mesh_quality import element_metrics
        from .post_backend import ids
        from .service import integer, unit_label

        unit_label(units)
        integer(part_id, "part_id")
        if (
            element_type not in ("shell", "solid")
            or not isinstance(elements, list)
            or not 1 <= len(elements) <= 1000
        ):
            raise ValueError("Provide 1..1000 shell or solid elements")
        new = {}
        for row in elements:
            if not isinstance(row, dict) or set(row) != {"id", "node_ids"}:
                raise ValueError("Each element requires id and node_ids")
            eid = integer(row["id"], "element id")
            ids(row["node_ids"], "node_ids", 8)
            conn = list(row["node_ids"])
            if len(conn) not in ((3, 4) if element_type == "shell" else (8,)) or eid in new:
                raise ValueError("Expected unique element IDs and tri/quad or hex8 connectivity")
            new[eid] = conn

        def precheck(state):
            nodes, old = mesh_index(state)
            if part_id not in state["part_ids"] or set(new) & {k[1] for k in old}:
                raise ValueError("Target part is missing or element IDs collide")
            if len(old) + len(new) > 20000:
                raise ValueError("Element import exceeds GUI verification limit")
            for conn in new.values():
                if not set(conn) <= nodes.keys():
                    raise ValueError("New connectivity references unknown nodes")
                metric = element_metrics(element_type, [nodes[n] for n in conn])
                if (
                    metric["min_edge"] <= 0
                    or metric.get("area", 1) <= 0
                    or metric.get("signed_volume", 1) <= 0
                    or metric.get("minimum_jacobian", 1) <= 0
                ):
                    raise ValueError("New element has degenerate/inverted geometry")

        def commands(state, directory):
            fragment = directory / "import-elements.k"
            lines = ["*KEYWORD", "*ELEMENT_" + element_type.upper()]
            for eid, conn in new.items():
                expanded = conn + [conn[-1]] if len(conn) == 3 else conn
                lines.append(",".join(map(str, [eid, part_id] + expanded)))
            lines.append("*END")
            fragment.write_text("\n".join(lines) + "\n", encoding="ascii")
            return ["import keyword " + command_path(fragment)]

        def verify(before, after):
            old_nodes, old_elems = mesh_index(before)
            after_nodes, after_elems = mesh_index(after)
            check_same_nodes(old_nodes, after_nodes)
            if after_elems.keys() != old_elems.keys() | {(element_type, k) for k in new}:
                raise ValueError("Native element import changed the wrong registry")
            if any(after_elems[k] != v for k, v in old_elems.items()):
                raise ValueError("Native element import changed existing connectivity")
            for eid, conn in new.items():
                actual = after_elems[(element_type, eid)]
                if element_type == "shell":
                    match = cyclic_equal(conn, shell_cycle(actual))
                else:
                    match = tuple(conn) == actual
                if not match:
                    raise ValueError("Imported connectivity differs from request")
            if set(before["part_ids"]) != set(after["part_ids"]):
                raise ValueError("Native element import changed the part registry")
            expected_members = {k: sorted(v) for k, v in before["part_elements"].items()}
            expected_members[str(part_id)] = sorted(expected_members.get(str(part_id), []) + list(new))
            if expected_members != {k: sorted(v) for k, v in after["part_elements"].items()}:
                raise ValueError("Imported elements are not in the requested part")
            return dict(
                created_element_ids=sorted(new),
                target_part=part_id,
                original_mesh_preserved=True,
                scope="Native geometry/IDs checked; target section/material compatibility is not inferred",
            )

        return self._gui_mesh_edit(
            session_id,
            "create_gui_elements",
            dict(element_type=element_type, part_id=part_id, elements=elements, units=units),
            commands,
            verify,
            precheck,
        )
