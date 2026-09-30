"""Native mesh generation with scoped PyDYNA deck composition and native reopen."""

import math

from .jobs import check_artifact


class PreTools:
    def create_solid_sphere(
        self, center: list[float], radius: float, divisions: int, units: str, part_id: int = 1
    ) -> dict:
        """Create a native solid sphere mesh; verify new node IDs and radius before exporting a k file."""
        from .service import integer, numbers, unit_label

        p = dict(
            center=numbers(center, 3, "center"),
            radius=numbers([radius], 1, "radius", True)[0],
            divisions=integer(divisions, "divisions", 1, 20),
            units=unit_label(units),
            part_id=integer(part_id, "part_id"),
        )
        return self._native("create_sphere", p, artifacts=(("model.k", "keyword"),), export=True)

    def rotate_mesh_nodes(
        self, model: str, node_ids: list[int], axis: str, angle: float, center: list[float], units: str
    ) -> dict:
        """Rotate selected user nodes around a global X/Y/Z axis through center, verify selected/unselected coordinates and save a new deck."""
        from .post_backend import ids
        from .service import numbers, unit_label

        ids(node_ids, "node_ids", 10000)
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be x, y or z")
        p = dict(
            node_ids=node_ids,
            axis=axis,
            angle=numbers([angle], 1, "angle")[0],
            center=numbers(center, 3, "center"),
            units=unit_label(units),
        )
        return self._native("rotate_nodes", p, model, artifacts=(("model.k", "keyword"),), export=True)

    def extrude_shell_part(self, model: str, part_id: int, length: float, layers: int, units: str) -> dict:
        """Native shell-drag extrusion of a single planar XY shell part along +Z. Retains source shells, creates solids, verifies extent/counts and saves a new k file."""
        from .service import integer, numbers, unit_label

        p = dict(
            part_id=integer(part_id, "part_id"),
            length=numbers([length], 1, "length", True)[0],
            layers=integer(layers, "layers", 1, 500),
            units=unit_label(units),
        )
        return self._native("extrude_shell", p, model, artifacts=(("model.k", "keyword"),), export=True)

    def create_solid_box(
        self,
        divisions: list[int],
        size: list[float],
        units: str,
        origin: list[float] | None = None,
        part_id: int = 1,
        node_start: int = 1,
        element_start: int = 1,
    ) -> dict:
        """Create a native structured hexahedral box mesh, verify node/solid counts and save a new k file; no material/analysis inferred."""
        from .service import integer, numbers, unit_label

        if len(divisions) != 3:
            raise ValueError("Three mesh divisions required")
        dims = [integer(v, "division", 1, 500) for v in divisions]
        if math.prod(dims) > 100000:
            raise ValueError("Box exceeds 100000 elements")
        p = dict(
            divisions=dims,
            size=numbers(size, 3, "size", True),
            origin=numbers(origin or [0, 0, 0], 3, "origin"),
            units=unit_label(units),
            part_id=integer(part_id, "part_id"),
            node_start=integer(node_start, "node_start"),
            element_start=integer(element_start, "element_start"),
        )
        return self._native("create_box", p, artifacts=(("model.k", "keyword"),), export=True)

    def translate_mesh_nodes(self, model: str, node_ids: list[int], offset: list[float], units: str) -> dict:
        """Translate explicitly selected user nodes through native LS-PrePost; verify all selected/unselected coordinates and save a new k file."""
        from .post_backend import ids
        from .service import numbers, unit_label

        ids(node_ids, "node_ids", 10000)
        p = dict(node_ids=node_ids, offset=numbers(offset, 3, "offset"), units=unit_label(units))
        return self._native("translate_nodes", p, model, artifacts=(("model.k", "keyword"),), export=True)

    def move_elements_to_part(
        self, model: str, element_type: str, element_ids: list[int], part_id: int
    ) -> dict:
        """Reassign selected element user IDs to a native part and save a new k file. Does not configure target material/section."""
        from .post_backend import ids
        from .service import integer

        if element_type not in ("shell", "solid", "beam"):
            raise ValueError("Unsupported element type")
        ids(element_ids, "element_ids", 10000)
        return self._native(
            "move_elements_to_part",
            dict(element_type=element_type, element_ids=element_ids, part_id=integer(part_id, "part_id")),
            model,
            artifacts=(("model.k", "keyword"),),
            export=True,
        )

    def validate_model_references(self, model: str) -> dict:
        """Check supported standalone deck IDs/references with PyDYNA; not mesh-quality, physical or solver validation."""
        from .model_deck import validate_references

        return validate_references(self.settings.input_path(model))

    def create_node_set_by_box(
        self, model: str, set_id: int, bounds: list[float], units: str, tolerance: float = 1e-8
    ) -> dict:
        """Select reference nodes inside [xmin,ymin,zmin,xmax,ymax,zmax] and write a fresh standalone deck with SET_NODE_LIST; original preserved."""
        from .model_deck import add_box_set
        from .service import integer, numbers

        integer(set_id, "set_id")
        box = numbers(bounds, 6, "bounds")
        if any(box[i] > box[i + 3] for i in range(3)) or not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError("Invalid box bounds/tolerance")
        source = self.settings.input_path(model)

        def work(directory):
            output = directory / "model.k"
            data = add_box_set(source, output, set_id, box, tolerance)
            return data, [check_artifact(output, "keyword")]

        return self._post_job(
            "create_node_set_by_box",
            dict(set_id=set_id, bounds=box, tolerance=tolerance, units=units),
            [source],
            work,
        )

    def create_tensile_shell_plate(
        self,
        nx: int,
        ny: int,
        size: list[float],
        thickness: float,
        density: float,
        young_modulus: float,
        poisson_ratio: float,
        displacement: float,
        duration: float,
        output_interval: float,
        units: str,
    ) -> dict:
        """Native shell mesh -> PyDYNA material/section/sets/BCs/smooth displacement ramp/output cards -> native reopen. Explicit planar test deck; no solver/quasi-static certification."""
        from .deck_backend import material_values
        from .model_deck import complete_tensile_plate
        from .service import numbers, unit_label

        material = material_values(density, young_modulus, poisson_ratio)
        numbers([thickness, duration, output_interval], 3, "thickness/duration/output_interval", True)
        if not math.isfinite(displacement) or output_interval > duration:
            raise ValueError("Invalid displacement or output interval")
        unit_label(units)
        mesh = self.create_shell_plate(nx, ny, size, units)
        if mesh["status"] != "succeeded":
            return mesh
        source = self.settings.input_path(mesh["artifacts"][0]["path"])

        def work(directory):
            output = directory / "analysis.k"
            data = complete_tensile_plate(
                source, output, thickness, material, displacement, duration, output_interval
            )
            reopened = self.inspect_model(str(output))
            data.update(mesh_job_id=mesh["job_id"], reopen_job_id=reopened["job_id"])
            if (
                reopened["status"] != "succeeded"
                or reopened["data"]["counts"]["nodes"] != data["node_count"]
                or reopened["data"]["counts"]["elements"] != data["shell_count"]
            ):
                raise ValueError(
                    "Native reopen did not confirm generated mesh counts; job=" + reopened["job_id"]
                )
            data["native_reopen_verified"] = True
            return data, [check_artifact(output, "keyword")]

        return self._post_job(
            "create_tensile_shell_plate",
            dict(
                nx=nx,
                ny=ny,
                size=size,
                thickness=thickness,
                material=material,
                displacement=displacement,
                duration=duration,
                output_interval=output_interval,
                units=units,
            ),
            [source],
            work,
        )
