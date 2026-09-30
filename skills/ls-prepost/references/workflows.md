# Task patterns

## Generate and verify a plate

Resolve size, origin, discretization, unit label and ID ranges. `create_shell_plate` creates a new isolated model. Reopen its returned keyword artifact with `inspect_model`; expected nodes are `(nx+1)*(ny+1)` and shell elements `nx*ny`. Verify the returned IDs and coordinates, then render the returned artifact. A keyword file without material, section, load and control definitions is a mesh, not a solved engineering model.

## Numerical extraction

Inspect the available database and physical states first. Select actual user node IDs. Use a quantity-specific tool and explicit state list; report `backend`, component names and units. Verify CSV row counts and data range. Magnitude means the Euclidean norm of a vector, not a stress invariant. Unknown IDs/states must fail rather than falling back to unrelated entities.

## Extend a workflow

Search official/tutorial and local-case records. Identify input selection, state dependencies, output files and known defects. A candidate becomes supported only after implementation and meaningful tests. Geometry repair, Shell Drag, materials/contact, fragments and virtual gauges are roadmap items unless the current capability registry states otherwise.

The sources already expose useful future cases: official ball impact, element editing, ElGen and Block Mesher; local part images, mesh/ID inspection, resultant vectors, stress extraction, deleted elements, aggregate partitioning and arrays. Preserve the difference between a native operation, generated keyword data and a standalone formula plot.

