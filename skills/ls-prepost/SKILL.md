---
name: ls-prepost
description: Automate LS-PrePost model inspection, supported preprocessing, result extraction and image export through the LS-PrePost-MCP tools; consult versioned command and tutorial references for unsupported tasks.
---

# LS-PrePost automation

Use the installed MCP tools for actual operations. Start with `list_capabilities` and, when selecting a build, `list_installations`. `run_on_version` selects an explicit configured installation without changing the global default.

For model work, inspect before selecting entities. Tool node/element IDs are **user IDs**, not array positions. Native/public state numbers are **1-based**. The file-reader backend translates its internal indices. Use the physical time array to resolve time requests.

Choose the backend explicitly:
- Native `inspect_model`, entity queries, `create_shell_plate`, `export_keyword`, `render_snapshot` require a functioning LS-PrePost installation and, except SCL, its configured embedded Python.
- `probe_scl` checks the native SCL path without requiring embedded Python.
- `inspect_d3plot_scl` supports a bounded staged file family for older builds without Python.
- `inspect_d3plot_database`, `extract_d3plot_nodal`, and binout tools use optional LASSO; report that backend, never describe it as native LS-PrePost execution.
- `inspect_lsreader` and `extract_lsreader_nodal` use an explicitly configured independent LS-Reader interpreter. PyDYNA tools inspect decks and create/update elastic material fragments, with reimport checks.

For source/output semantics and workflow selection read [workflows](references/workflows.md). For build differences and failures read [compatibility](references/compatibility.md).

`search_commands`, `search_knowledge` and `search_workflows` return reference or candidate material. They do not make an unsupported capability executable. Inspect their status and source; do not invent API keys or claim that every GUI operation has an equivalent script call.

For generation or quantitative interpretation, obtain the unit system from the task/model context. If unknown, retain raw values with an explicit unknown-unit label and do not infer material constants or physical conclusions. Distinguish reference coordinates from deformed positions, stress components from invariants, shell layer/integration point from nodal averaging, and visible parts from physically active elements.

All task outputs belong to the job directory. A `failed` result is a failure even when an old file or an image exists elsewhere. Use `read_job` for logs and artifacts. Report what was executed, selected IDs/states, which outputs passed validation, and any unverified physical or version assumptions.

Current version limits are recorded in the capability/compatibility documentation. The 4.10 embedded vector path is blocked after failed numeric checks; use an explicitly identified file-reader backend or the tested 4.13 profile. MPP binout shard sets and include-bearing deck rewrites are not yet supported. No arbitrary script execution, persistent GUI control, or solver job tool is provided in this initial release.
