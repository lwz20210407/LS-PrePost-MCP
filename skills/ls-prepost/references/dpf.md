# Optional DPF route

Use DPF only as an explicitly identified optional backend; preserve the user's native LS-PrePost requirement. Read `docs/archive/2026-10/DPF_INTEGRATION.md` and probe with `probe_dpf_runtime`. A successful diagnostic job with `ready_for_runtime_attempt=false` is unavailable, not an operational DPF reader. Local client0.16.1 was found; actual Server extraction has not passed acceptance.

Use `inspect_dpf_results` to separate file availability from typed adapter support. `export_dpf_result` retains branch time-set IDs, full field labels and reported units. Keep `part`, `interface`, master/slave `idtype`, components and local beam directions distinct. Use explicit state IDs for spatial results, `entity_ids` for mesh fields, and `label_filter` for histories. Missing variables/sets/IDs or unresolved layers are errors. Do not equate DPF time IDs or source locations to LS-PrePost states/MID or reader slot1 without comparison.

Select a single label/entity/component series before plotting its `time,value` CSV columns through native `export_gui_curve_plot`. Do not join unrelated label fields by row number. Preserve absolute-peak sign and entity/time witnesses. Erosion flags describe physical active/eroded state, not GUI visibility; absence is unknown, not all-active. DPF sub-mesh/deformed rendering and arbitrary operators are not implemented by this adapter.

Installation requires a compatible separate Server and applicable vendor license conditions. The tools do not download Server, accept license terms, alter license settings, open remote services or start a solver. Entry/in-process execution is requested. Keep every private source and derived artifact local.
