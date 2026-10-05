# Workflow planning, execution and parameter studies

This is an implemented orchestration increment supporting all three product workflows. It reuses current Service tools and native adapters; it does not replace the outstanding ModelRef, large-model access, result validity or version-support work.

`typed recipe → static preflight → shared route → operation → result/quality gate → evidence`

## Static preview

`inspect_workflow(path, parameters=None, session_id=None)` reads the recipe and returns `ready` or `invalid`, per-step owning module, dispatch route, dependencies, deferred result bindings and errors. It does not create jobs, open input models, contact a session or run native software.

`run_workflow` always performs the same preflight before opening a recorded initial model or executing any step. Missing parameters in later steps, unknown arguments, invalid concrete argument types, forward/self references, malformed result paths, missing session context and invalid check thresholds therefore fail before earlier edits can occur. Known checks still use their execution/quality gates at runtime.

References to future operation outputs remain deferred: a static preview cannot certify the existence or meaning of their fields. Their resolved argument types are checked immediately before dispatch. Operation-specific engineering constraints, file availability, active model, native build and session state remain the owning adapter's responsibility. A `ready` preview is not native or physical validation.

Session operations take their session/model context from the workflow. Do not supply `session_id`, `model`, `d3plot` or native field `path` inside a step that uses that implicit context; change models with `open_model`. Routes are `session`, `session_native` or `service`; the last calls the named service method and makes no guarantee that the method launches a native process. Existing mode-specific restrictions still apply.

## Explicit parameter studies

`run_workflow_sweep(path, cases, outputs=None, session_id=None)` accepts 1–20 explicit cases:

```json
{
  "cases": [
    {"id": "area10", "parameters": {"area_mm2": 10}},
    {"id": "area20", "parameters": {"area_mm2": 20}}
  ],
  "outputs": {
    "peak_MPa": {"step_id": "tensile", "path": ["data", "peak_engineering_stress_MPa"]}
  }
}
```

The recipe must supply its other required defaults or each case must specify them. All cases preflight before the first executes. The study freezes the recipe, then creates a fresh child workflow/job per case, without reusing earlier case results. GUI recipes must begin with `open_model`/`new_model` or carry a recorded `initial_model`; cumulative editing of a preceding case is not accepted as an independent study. Normal dirty-model protection still applies: save previous changes or explicitly choose discard in the authored recipe.

The first execution, quality or output-selector failure stops subsequent cases. Successful earlier results remain accessible; later cases are marked `skipped`. Output selectors are finite JSON scalars, with no implicit aggregation of arrays. A missing output is a failure, not a blank success. `cases.json` retains exact values/errors/child paths, `summary.csv` is a mixed-text table (not a numeric history), and `workflow.json`/`preflight.json` preserve the plan. There is no automatic retry, rollback, optimization, solver execution or crash resume.

## Business recipes and verification

- `examples/workflows/visible_gui_mesh_transform.json`: explicit input→part-associated node selection→native translation→Hex8 quality gate→checkpoint→native reopen→readback. The native check remains limited to nonempty Hex8-only meshes.
- `examples/workflows/declared_unit_tensile.json`: convert force units→relative displacement with per-source units→engineering stress/strain and work. Input curve quantities and units are declarations, not inferred from the solver.
- Existing native relative-displacement and selected-stress recipes use the same preflight/executor and may be recorded and parameterized.

`tools/run_parameter_study_acceptance.py --workspace <private-output>` checks two analytical mixed-unit engineering cases: areas10/20mm² yield peak200/100MPa with work1.8J. Adding `--executable <LS-PrePost>` explicitly opts into visible, maximized GUI testing: two synthetic Hex8 cases translate the same baseline by1/2mm, pass native quality checks, save/reopen and read back1/2mm (not cumulative3mm). Source identity and separate saved models are checked. Windows4.13.4 passed; other versions/modes are not certified by this test.

This framework does not complete native XYPlot styling/export, field-aware cloud plots or batch reports. These remain explicit priorities in [delivery plan](DELIVERY_PLAN.md).
