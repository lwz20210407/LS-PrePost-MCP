# Changes

## 0.4.0 (development)

- Route native field/stress actions through the current visible GUI when used in a GUI workflow. Share SCL generation, ID/state matrix validation and Mises/tensor parsing with the batch backend; verify original state, selection, topology and part visibility without reopening or starting another LSPP.
- Verify selected-solid six-component stress/Mises, strain components and effective plastic strain on a representative private 4.13.4 result. Fix Windows SCL path separators without changing user preferences.

- Connect visible native node selection, component-history export and relative-displacement processing through a reusable three-step workflow; validate two component runs and native position/reference/displacement identity on one private result copy.
- Add explicit per-node/component scalar curves, bounded output counts and strict physical-time ordering. Preserve nodal FieldSpec and strict integer IDs/states. Restore and confirm GUI state through native command flow; keep animation stopped.
- Fix state-switch completion checks and application-reset working directories: history files always use owned absolute output paths.

- Unify keyword/d3plot GUI entity selection with shared user-ID contracts and verified reference/state scope. Use native bulk part selection to avoid thousands of individual node commands; retain exact ID readback.
- Preserve part visibility across selections; add all/active-parts scopes with explicit shared/orphan node and inversion semantics. Verify 9 synthetic keyword cases and 11 representative private result cases in visible 4.13.4; no alive/deletion, deformed-coordinate or full menu coverage is implied.
- Separate selection/inspection from mesh-edit checkpoints, avoiding unnecessary keyword exports while preserving dirty state and the saved recovery checkpoint.

- Add backend-aware ResultSelection/SamplingSpec/FieldSpec to native SCL and LASSO field/stress exports. Preserve immutable ordered selection provenance, sampling distinctions and actual displacement-reference transformations. These metadata contracts do not infer layer equivalence or physical units.
- Enforce strict integer entity/state/reader-index inputs at the MCP boundary for these extraction tools; reject meaningless nodal integration-point selectors.

- Implement workflow-boundary execution/check outcomes, automatic gates for mapped checks, strict scalar predicates and parameterized thresholds. Failed gates stop dependent actions while preserving original reports/checkpoints and explicit failure evidence.
- Accept prepared programs only as preparation, reject unknown/missing/unverified execution statuses, and distinguish attempted steps from completed steps. Add five reproducible synthetic file-backend gate cases and packaged MCP smoke verification.
- Verify gates in visible 4.13.4: failed checks block actual coordinate edits; explicit finding policies and thresholds survive managed recording, parameterization and replay. Provide an opt-in native acceptance driver; no hosted CI or arbitrary-version GUI certification is implied.

- Add same-session visible GUI mesh editing, duplicate-node merge, all/subset shell normal reversal, native entity selection, boolean selection, geometric predicates and native selection buffers.
- Add node/shell/part renumbering through the native dialog with mapping-log verification and scoped reference checks; handle zero padding in native node-list sets.
- Verify selection recording, parameter binding and replay against the same visible application.
- Add actual native shell Model Checking (13 selectable criteria, explicit thresholds and native statistics) and version-specific menu discovery. These do not imply full menu/solver coverage.
- Preserve existing user preferences in isolated GUI session configuration and recover exited sessions from checkpoints. Retry transient Windows manifest replacement failures without replacing the original early.

## 0.3.0

- Add trusted native command, cfile, SCL, embedded Python and macro preparation/execution with output contracts.
- Add persistent GUI sessions, checkpoints, recording/workflow templates, installation filter/template discovery and engineering curve/energy workflows.
- Track remaining preprocessing, postprocessing, menu and language-interface gaps explicitly. Native evidence is scoped by build and workflow.

## 0.2.0

- Add native solid-box meshing, planar shell extrusion, selected-node translation and element part reassignment with explicit output checks.
- Add native SCL stress/strain/nodal export, native Mises comparison, tensor invariants with explicit triaxiality/Lode definitions, and undefined hydrostatic ratios.
- Add native ASCII/XYPlot and SCLBinout curve routes, representative acceptance workflow, whole-field extrema, and owned staging cleanup.
- Add optional reader field/history-slot extraction, nested binout tables, strict numeric ASCII import and nonuniform curve calculus.
- Add coordinate-box node sets, bounded model reference checks and a prescribed-displacement shell-plate deck with native reopen.
- Add installed PyDYNA keyword/schema discovery, structured deck composition, scalar keyword editing and table-row editing with reimport checks.
- Document actual feature gaps, six PyDYNA documentation sections, source-version mismatches and private-data boundaries. Keyword catalogs and repeated tests are not feature-coverage claims.

## 0.1.0

- Initial MCP/CLI, native command/Python/SCL jobs, model/entity queries, shell plate and snapshot operations.
- Optional LASSO, LS-Reader and PyDYNA material adapters; source, command and tutorial references.
