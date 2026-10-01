"""Mesh edits into new decks, with explicit geometry checks and native reopening."""

import math

import numpy as np

from .jobs import atomic_json, check_artifact
from .mesh_quality import from_deck, quality
from .model_deck import load_standalone


class MeshTools:
    def inspect_mesh_quality(
        self,
        model: str,
        units: str,
        max_aspect: float = 10.0,
        max_warpage: float = 15.0,
        min_scaled_jacobian: float = 0.2,
    ) -> dict:
        """Check standard linear shell/solid/beam geometry, report true IDs, orphan nodes and unsupported topologies. Does not claim full native Model Checking."""
        from .service import unit_label

        unit_label(units)
        if (
            not all(math.isfinite(v) for v in [max_aspect, max_warpage, min_scaled_jacobian])
            or max_aspect < 1
            or not 0 <= max_warpage <= 180
            or not -1 <= min_scaled_jacobian <= 1
        ):
            raise ValueError("Invalid quality thresholds")
        source = self.settings.input_path(model)

        def work(directory):
            nodes, elements = from_deck(load_standalone(source))
            report = quality(nodes, elements, max_aspect, max_warpage, min_scaled_jacobian)
            report.update(
                backend="pydyna+geometry-math",
                units=units,
                scope=report["definitions"]["scope"],
                native_model_check=False,
            )
            atomic_json(directory / "quality.json", report)
            brief = {k: v for k, v in report.items() if k not in ("elements", "unsupported", "orphan_nodes")}
            brief["orphan_count"] = len(report["orphan_nodes"])
            return brief, [check_artifact(directory / "quality.json", "json")]

        return self._post_job(
            "inspect_mesh_quality",
            dict(
                units=units,
                max_aspect=max_aspect,
                max_warpage=max_warpage,
                min_scaled_jacobian=min_scaled_jacobian,
            ),
            [source],
            work,
        )

    def transform_mesh_deck(
        self,
        model: str,
        operation: str,
        values: list[float],
        units: str,
        node_ids: list[int] | None = None,
        center: list[float] | None = None,
        native_check: bool = True,
    ) -> dict:
        """Translate/rotate/scale mesh coordinates in a new deck, then quality-check and optionally reopen in LS-PrePost. Coordinate systems and load vectors are not rotated."""
        from .deck_backend import api
        from .service import numbers

        if operation not in ("translate", "rotate", "scale"):
            raise ValueError("Unsupported transform")
        values = numbers(values, 4 if operation == "rotate" else 3, "values")
        center = np.asarray(numbers(center or [0, 0, 0], 3, "center"))
        if operation == "scale" and any(v <= 0 for v in values):
            raise ValueError(
                "Scale factors must be positive; reflection needs orientation-aware topology changes"
            )
        if operation == "rotate":
            axis = np.asarray(values[:3])
            length = np.linalg.norm(axis)
            if length == 0:
                raise ValueError("Rotation axis cannot be zero")
            axis = axis / length
            angle = math.radians(values[3])
            x, y, z = axis
            cross = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
            matrix = (
                math.cos(angle) * np.eye(3)
                + (1 - math.cos(angle)) * np.outer(axis, axis)
                + math.sin(angle) * cross
            )
        source = self.settings.input_path(model)

        def work(directory):
            _, kw = api()
            deck = load_standalone(source)
            available = {
                int(row.nid) for c in deck.keywords if isinstance(c, kw.Node) for row in c.nodes.itertuples()
            }
            selected = available if node_ids is None else set(node_ids)
            if node_ids is not None:
                from .post_backend import ids

                ids(node_ids, "node_ids", 1000000)
            if not selected or not selected <= available:
                raise ValueError("Unknown/empty node selection")
            for c in deck.keywords:
                if not isinstance(c, kw.Node):
                    continue
                frame = c.nodes.copy()
                mask = frame["nid"].isin(selected)
                points = frame.loc[mask, ["x", "y", "z"]].to_numpy(float)
                if operation == "translate":
                    points = points + values
                elif operation == "scale":
                    points = (points - center) * values + center
                else:
                    points = (points - center) @ matrix.T + center
                frame.loc[mask, ["x", "y", "z"]] = points
                c.nodes = frame
            output = directory / "model.k"
            deck.export_file(str(output))
            report = quality(*from_deck(load_standalone(output)))
            atomic_json(directory / "quality.json", report)
            data = dict(
                operation=operation,
                changed_nodes=len(selected),
                mesh_quality_passed=report["valid_within_scope"],
                failed_elements=report["failed_count"],
                backend="pydyna+geometry-math",
                scope="Mesh coordinates only; load vectors/material axes/BC coordinate systems retain their definitions",
            )
            if native_check:
                reopened = self.inspect_model(str(output))
                data["native_job_id"] = reopened["job_id"]
                if reopened["status"] != "succeeded":
                    raise ValueError("Native reopen failed")
                data["native_reopen_verified"] = True
            return data, [
                check_artifact(output, "keyword"),
                check_artifact(directory / "quality.json", "json"),
            ]

        return self._post_job(
            "transform_mesh_deck",
            dict(
                operation=operation,
                values=values,
                units=units,
                node_ids=node_ids,
                center=center.tolist(),
                native_check=native_check,
            ),
            [source],
            work,
        )

    def merge_duplicate_mesh_nodes(
        self, model: str, tolerance: float, units: str, native_check: bool = True
    ) -> dict:
        """Merge geometrically close nodes into the lowest-ID representative, updating supported element/set/nodal references. Reject unhandled node references and element collapse."""
        from itertools import product

        import pandas as pd

        from .deck_backend import api

        if not math.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("Positive finite tolerance required")
        source = self.settings.input_path(model)

        def work(directory):
            _, kw = api()
            deck = load_standalone(source)
            nodes, elements = from_deck(deck)
            cells = {}
            mapping = {}
            positions = {int(n[0]): np.asarray(n[1:]) for n in nodes}
            for uid in sorted(positions):
                xyz = positions[uid]
                scaled = xyz / tolerance
                if not np.isfinite(scaled).all():
                    raise ValueError("Coordinates/tolerance exceed spatial index numeric range")
                key = tuple(math.floor(float(v)) for v in scaled)
                candidates = []
                for delta in product((-1, 0, 1), repeat=3):
                    candidates += cells.get(tuple(key[i] + delta[i] for i in range(3)), [])
                match = next(
                    (j for j in sorted(candidates) if np.linalg.norm(xyz - positions[j]) <= tolerance), None
                )
                if match is None:
                    cells.setdefault(key, []).append(uid)
                    mapping[uid] = uid
                else:
                    mapping[uid] = match
            removed = {uid: target for uid, target in mapping.items() if uid != target}
            for element in elements:
                original = set(n for n in element["nodes"] if n)
                if len({mapping[n] for n in original}) < len(original):
                    raise ValueError("Merge would collapse an element: " + str(element["id"]))
            supported = (
                kw.Node,
                kw.ElementShell,
                kw.ElementSolid,
                kw.ElementBeam,
                kw.SetNodeList,
                kw.BoundarySpcNode,
                kw.LoadNodePoint,
                kw.DatabaseHistoryNode,
            )
            from ansys.dyna.core.lib.keyword_base import LinkType

            for c in deck.keywords:
                if isinstance(c, str):
                    raise ValueError("Raw keyword blocks prevent safe node-reference rewriting")
                node_links = [
                    name for name, kind in getattr(c, "_link_fields", {}).items() if kind == LinkType.NODE
                ]
                if node_links and not isinstance(c, supported):
                    raise ValueError("Unhandled node-reference keyword: " + type(c).__name__)
                if isinstance(c, kw.Node):
                    c.nodes = c.nodes.loc[~c.nodes["nid"].isin(removed)].copy()
                elif isinstance(c, (kw.ElementShell, kw.ElementSolid, kw.ElementBeam)):
                    frame = c.elements.copy()
                    for col in frame.columns:
                        if col in node_links or col in ("n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8"):
                            frame[col] = frame[col].map(
                                lambda x: mapping.get(int(x), int(x)) if not pd.isna(x) else x
                            )
                    c.elements = frame
                elif isinstance(c, kw.SetNodeList):
                    c.nodes = list(dict.fromkeys(mapping.get(int(x), int(x)) for x in c.nodes))
                elif isinstance(c, (kw.BoundarySpcNode, kw.LoadNodePoint)):
                    frame = c.nodes.copy()
                    frame["nid"] = frame["nid"].map(lambda x: mapping.get(int(x), int(x)))
                    if frame["nid"].duplicated().any():
                        raise ValueError("Merging would create duplicate nodal boundary/load entries")
                    c.nodes = frame
                elif isinstance(c, kw.DatabaseHistoryNode):
                    for name in node_links:
                        value = getattr(c, name, None)
                        if value in mapping:
                            setattr(c, name, mapping[value])
            output = directory / "model.k"
            deck.export_file(str(output))
            after_nodes, after_elements = from_deck(load_standalone(output))
            if len(after_nodes) != len(nodes) - len(removed):
                raise ValueError("Reimported node count mismatch")
            report = quality(after_nodes, after_elements)
            atomic_json(directory / "quality.json", report)
            atomic_json(directory / "node_map.json", {str(k): v for k, v in removed.items()})
            data = dict(
                removed_count=len(removed),
                node_count=len(after_nodes),
                mesh_quality_passed=report["valid_within_scope"],
                merge_policy="Lowest-ID existing representative within tolerance; no coordinate averaging or transitive chain expansion",
            )
            if native_check:
                opened = self.inspect_model(str(output))
                data["native_job_id"] = opened["job_id"]
                if opened["status"] != "succeeded" or opened["data"]["counts"]["nodes"] != len(after_nodes):
                    raise ValueError("Native merged mesh count verification failed")
                data["native_reopen_verified"] = True
            return data, [
                check_artifact(output, "keyword"),
                check_artifact(directory / "node_map.json", "json"),
                check_artifact(directory / "quality.json", "json"),
            ]

        return self._post_job(
            "merge_duplicate_mesh_nodes",
            dict(tolerance=tolerance, units=units, native_check=native_check),
            [source],
            work,
        )
