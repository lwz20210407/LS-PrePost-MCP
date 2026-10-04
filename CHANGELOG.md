# Changes

## 0.4.0 (development)

- Add native Segment pressure curves/named loads with explicit units, monotonic time, ID collision checks, direction reports, parameter replay and numeric/card readback. Add exterior3D and directed2D nonreflecting conditions, with R14+ negative Segment IDs and a separately verified ordered two-node-set route for R11..13. Reject overlap, reversed2D edges, incompatible formulations and allocation collisions. Native4.13.4 create/reopen checks do not certify solver absorption.

- Add selection-bound native Segment sets from conforming Hex8/Tet4 exterior faces, shell faces and directed XY boundary edges. Verify ownership against unselected/hidden neighbors, orientation and normal filtering, native connectivity/scene preservation, parameterized replay and reopen. Pressure/nonreflecting conditions remain separate work.

- Add selection-bound native node/part list-set creation, paged inspection and member replacement preserving native attributes; add explicit global SPC set/node constraint creation, ID/DOF conflict checks and native card/mesh/scene verification. Verify changed-selection/SID recording replay and native reopen. Add model-load generations to reject old selection artifacts even after reopening identical geometry.
- Preserve all CSV list members and native packed SPC-ID header/data pairs during targeted readback; emit one named SPC_NODE card per node after native multirow truncation was reproduced. Segment sets, pressure and nonreflecting boundaries remain incomplete.

- Preserve per-element display-active flags during selection. Remove `pall`, avoid native whole/by-part selection when hidden members would be omitted, and verify exact IDs plus scene digests. Add mixed-element/hidden-part/buffer/display-setup replay native regression and fail-before-dispatch limits.
- Add an evidence-based local release progress dashboard with explicit denominator history. Promote selection-driven Entity Creation sets/constraints/loads to required release work; these workflows remain incomplete and are not advertised as implemented tools.

- Extend the existing display tool with strict native absolute zoom/pan and incremental X/Y/Z view rotations. Preserve operation ordering and managed parameter replay; verify zoom/pan idempotence, changed pixels, X/inverse rotation and reference-mesh preservation in visible4.13.4. Named view persistence remains a separate incomplete feature.

- Add optional compact MCP discovery/schema/execution profile while keeping original interfaces; preserve strict validation and explicit GUI routing without silent fallback. Resolve common panels through the current menu tree, constrain command-entry fallback, and reject locked desktops before creating pending native jobs.
- Add standard element Blank operations with whole-state binary readback, geometry/state/part preservation and owned restore/replay. Optimize sparse isolation using the smaller complement. Verify mixed shell/solid/beam and representative result workflows in visible4.13.4; use fresh native keyword beam endpoints after reproducing native array-binding heap faults.
- Preserve model titles and plain native result captions. Default field PNG/snapshot/movie display averaging to MinMax, retain explicit nodal/none overrides and keep raw CSV sampling distinct. Verify native averaging control, identical raw values, recorded replay and decoded three-frame MP4.

- Add native single-curve XYPlot PNG export from explicit CSV columns, labeled axes/units, fresh plot windows and numeric readback. Preserve hysteresis row order and original engineering CSV; disclose and validate native float32 storage. Verify changed-area recording/replay, old plot data preservation and native result-history/relative-displacement-to-PNG integration.

- Add native visible-GUI H264 MP4 export with state1/step1 bounds, explicit fps/resolution, ordered native frame evidence, independent full decode validation and state restoration. Verify complete57-state timeline and3/4-frame recorded parameter replay; arbitrary start/step modes remain rejected after failed native probes.

- Unify workflow operation routing and add a non-executing `inspect_workflow` preview. Preflight every step's parameters, signatures, references and quality thresholds before any native action; validate resolved dependency types again before dispatch.
- Add bounded explicit parameter studies with all-case preflight, separate child jobs, explicit GUI baselines, failure stopping and scalar/CSV summaries. Verify two native synthetic Hex8 transform/check/save/reopen cases and analytical engineering curves; recheck native post/recording flows. Native curve-image and animation export remain core gaps.

- Add opt-in native failed-solid ID capture, per-criterion artifacts and a verified deduplicated union for localization and dependency-preserving replay. Explicitly invalidate/backup known Buffer1 metadata and preserve other slots. Invalidate stale selection identities when replacing/resetting models; prevent a d3plot session from inheriting the prior keyword's default checkpoint.

- Add six native visible Hex8 quality criteria with explicit comparison thresholds, native failure counts/percent and zero-failure capture-state evidence. Preserve part visibility and mesh; integrate automatic workflow gates and recorded-threshold replay. Verify twelve pass/fail cases plus partial failures, hidden parts and blocked edits on synthetic 4.13.4 models.

- Add explicit scalar-history unit conversion and per-source normalization before curve alignment. Preserve rational scale provenance, reject incompatible dimensions and numerical range loss, and mark legacy shared-unit assumptions. Verify a mixed-unit force/relative-displacement -> stress/strain/work recipe in CI; no solver unit inference is implied.

- Add bounded absolute global node-coordinate/axis alignment through native grouped translations. Preserve untouched nodes/topology and part flags; report affected elements and checkpoints. Verify native quality gating, coordinate-parameter recording/replay, save/reopen and explicit recovery on a synthetic visible 4.13.4 mesh.

- Preserve explicit result/artifact dependencies through managed recording and include engineering/file steps of the recorded workflow. Changed selectors now drive new extraction IDs and new curve artifacts; unresolved dependencies and failed argument resolution require review. Verify changed-node replay in visible 4.13.4.

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
