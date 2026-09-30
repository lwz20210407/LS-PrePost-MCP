---
name: ls-prepost
description: Automate LS-PrePost model inspection, supported preprocessing, result extraction and image export through the LS-PrePost-MCP tools; consult versioned command and tutorial references for unsupported tasks.
---

# LS-PrePost automation

Use the installed MCP tools for actual operations. Start with `list_capabilities` and, when selecting a build, `list_installations`. `run_on_version` selects an explicit configured installation without changing the global default.

For model work, inspect before selecting entities. Tool node/element IDs are **user IDs**, not array positions. Native/public state numbers are **1-based**. The file-reader backend translates its internal indices. Use the physical time array to resolve time requests.

Choose the backend explicitly:
- When the user requests native LS-PrePost processing, prefer `extract_native_fields`, `extract_native_stress`, `extract_native_ascii_curve`, `extract_native_binout_curve` and `native_postprocess_case`. A library fallback is not a native pass. Read the [postprocessing contract](references/postprocessing.md) before interpreting tensors, layers or histories.
- Native `inspect_model`, entity queries, `create_shell_plate`, `export_keyword`, `render_snapshot` require a functioning LS-PrePost installation and, except SCL, its configured embedded Python.
- Native `create_solid_box`, `extrude_shell_part`, `translate_mesh_nodes`, `move_elements_to_part` perform bounded mesh generation/editing and save a new k file. Extrusion currently requires one planar XY shell part and keeps source shells. Part reassignment does not infer section/material settings; review the generated deck.
- `probe_scl` checks the native SCL path without requiring embedded Python.
- `inspect_d3plot_scl` supports a bounded staged file family for older builds without Python.
- `inspect_d3plot_database`, `extract_d3plot_nodal`, and binout tools use optional LASSO; report that backend, never describe it as native LS-PrePost execution.
- `inspect_lsreader` and `extract_lsreader_nodal` use an explicitly configured independent LS-Reader interpreter. PyDYNA tools inspect decks and create/update elastic material fragments, with reimport checks.
- `create_node_set_by_box` writes a fresh standalone deck. `validate_model_references` checks a declared subset of ID links. `create_tensile_shell_plate` uses native mesh generation, PyDYNA analysis cards and native reopen; it does not run a solver or establish quasi-static loading.
- For broader keyword work, first call `list_pydyna_keywords` / `describe_pydyna_keyword`, then `compose_keyword_deck`, `update_keyword_fields` or `update_keyword_table_row`. Use actual properties and table columns; never invent constructor kwargs. These are PyDYNA operations, followed by explicit native inspection when needed. See [PyDYNA routing](references/pydyna.md).

For source/output semantics and workflow selection read [workflows](references/workflows.md). For build differences and failures read [compatibility](references/compatibility.md).

`search_commands`, `search_knowledge` and `search_workflows` return reference or candidate material. They do not make an unsupported capability executable. Inspect their status and source; do not invent API keys or claim that every GUI operation has an equivalent script call.

For generation or quantitative interpretation, obtain the unit system from the task/model context. If unknown, retain raw values with an explicit unknown-unit label and do not infer material constants or physical conclusions. Distinguish reference coordinates from deformed positions, stress components from invariants, shell layer/integration point from nodal averaging, and visible parts from physically active elements.

All task outputs belong to the job directory. A `failed` result is a failure even when an old file or an image exists elsewhere. Use `read_job` for logs and artifacts. Report what was executed, selected IDs/states, which outputs passed validation, and any unverified physical or version assumptions.

Private engineering fixtures and their extracted data, images and detailed reports stay local. Public contributions contain generic code, synthetic tests and non-data verification summaries only. Batch samples and full-domain extrema are different products: do not describe representative-point histories as complete field output. Report `partial` results and unsupported/missing data explicitly.

For persistent GUI, installed templates, mesh editing, engineering curves and recording, read [v0.3 workflow routing](references/automation.md). Use `show_gui_session` when the user wants to watch native testing. A GUI command log alone is not evidence that model coordinates changed.

Current version limits are recorded in the capability/compatibility documentation. The 4.10 embedded vector path is blocked after failed numeric checks; use an explicitly identified file-reader backend or the tested 4.13 profile. MPP binout shard sets and include-bearing deck rewrites are not yet supported. No arbitrary script execution or solver job tool is provided. New persistent GUI tests cover Windows 4.13.4 only.
