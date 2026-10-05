# F1–F10 and common pre/post operations

Audit date2026-10-03. Sources:2026R1 User's Guide sections2.3,6.2.1,6.2.11,6.3.1–3,6.3.10,6.4.1–5 and chapter10; corresponding official legacy online panels; read-only local4.13configuration and native panel/control/command observations. The guide has1070PDFpages/740outline entries; only the listed target sections were reviewed for this audit. Extracting its text is not evidence that every chapter was understood or implemented. Vendor PDF/images/raw extracted text stay outside Git.

F-keys are interface entry points. Most mappings can be customized; the local4.13configuration maps F2–F9 as shown below. F1/F10 are special fixed entries. Default mapping does not establish complete implementation of the linked panel.

| Key | Default/current entry | Operations covered now | Main remaining controls |
|---|---|---|---|
| F1 | Function-key map | Configuration/reference reviewed | Mapping dialog inspection/configuration; safe Shift+F-key workflow binding |
| F2 | SelPar/Assembly | Typed part/whole/active/scoped-inverse selection and part show/hide/isolate/all; shared-node cases and large keyword/d3plot tests | Assembly hierarchy CRUD, geometry parts,18-column tree options, searches/sorts/groups, restore/invert display and all row/context actions |
| F3 | XYPlot | Native single-curve PNG/numeric readback, scalar history/engineering CSV workflow, dependency recording/replay | Complete File/Window/curve management, multi-curve additions, clipping/interpolation, native Cross Plot controls, plot layout/styling |
| F4 | Measure | New native coordinates, node distance/components, two-node axis height,3-/4-node angles,3-point circle radius/center; keyword and representative result-state tests | Remaining items below, local axes lifecycle, measurement histories/multi-curve management, all panel options |
| F5 | Identify | Native Identify used for checked coordinate query and retained node marks | Independent all entity-type identification, XYZ marker lifecycle, result/direction/material-direction/popups/part-name options, selective/global clearing |
| F6 | ASCII | Existing bounded native GLSTAT/NODOUT/MATSUM/SPCFORC routes and engineering extraction examples | All supported database dictionaries, multi-file unload/load/selection/reverse, per-database specialized options and complete curve-window interaction |
| F7 | Color | Some display/fringe configuration routes | Part/material coloring, transparency/pick-through, custom palette/reset/save/load, all background/text/label/mesh/outline/highlight options |
| F8 | Blank | Typed standard element hide/show/isolate/reverse/owned restore, binary flag readback, complete geometry/state/part checks and managed replay; see validation boundaries in the capability record | Node glyphs, other FE types, surface/edge update and auto-apply; part flags and physical erosion remain separate |
| F9 | Fcomp | Named native field CSV/PNG with explicit state/layer/units; raw entity CSV and default MinMax display averaging distinguished; managed custom-fringe movie coverage; plain native result captions | Complete result selector/expressions, layers/material/histories/averaging/smoothing, quality/property fringe route, difference/reference-state controls and every subpanel |
| F10 | File | Keyword/d3plot/staged family open, native keyword checkpoint/save/reopen, image/movie/curve output and bounded program execution | All native open/import/export formats, model lifecycle/append/merge choices, all print/animation dialogs, dynain/export variants and every file option |

## F4 complete item audit

The observed4.13Item list contains21entries. They apply across pre/post contexts according to source availability. Keyword/project models provide single values; result models can expose histories. A raw item label or command format is not an executable certified capability.

| Item/task | Current status | Acceptance/remaining requirement |
|---|---|---|
| Coordinate | Implemented/native-tested subset | Reference keyword XYZ and explicit-state d3plot XYZ; Identify numeric output must agree with native DataCenter positions |
| Dist N2N | Implemented/native-tested subset | Distance and signed global XYZ deltas checked independently; active model tokens avoid stale model0 |
| Axis height (derived task) | Implemented/native-tested subset | Absolute/signed selected global component of native N2N delta, not total distance and not a fictional extra native menu item |
| Dist N2S | Pending | Node-to-segment/surface meaning and nearest point must be defined and checked |
| Dist P2P | Pending | Arbitrary point definitions, coordinate system and history rules |
| Dist E2E4Node | Pending | Finite-edge distance/intersection/parallel cases and native comparison |
| Angle2Node | Pending | Deformed versus undeformed edge, explicit state/reference |
| Angle3Node | Implemented/native-tested keyword subset |3D angle checked; native projected-plane numbers remain uninterpreted, including undefined projections |
| Angle4Node | Implemented/native-tested keyword subset | Two directed edges checked, including parallel synthetic case |
|3Pt Radius/circle center | Implemented/native-tested keyword subset | Native radius plus matching native center message; independent3D geometry validation; collinear points rejected |
| Area | Existing raw reference, typed common route pending | Entity/part/segment scope, active-only/display rules and shell/solid distinctions |
| Volume | Existing raw `measure_parts`, complete typed route pending | Signed/absolute/geometric/section semantics and supported domains |
| Mass | Pending | Density/section/material/unit prerequisites; no invented density |
| Inertia | Pending | About which origin/axes, tensor layout and units |
| Ang Vel | Pending | Result availability, reference frame and time units |
| Create Axes | Pending | Cartesian/cylindrical/spherical create/import/delete, origin/direction/plane definitions and persistence |
| Separation | Pending | Part-to-part/reference-state, directional sign and shell-thickness offsets |
| Dist Node to Surf | Pending | CAD/FE surface identity, nearest-point geometry and validity |
| Dist Part to Surf | Pending | Part/surface scoping and extremum witnesses |
| Dist Segm to Segm | Pending | Two segment groups, normal constraints/optimization and degeneracy |
| Dist SALE Points | Pending | ALE/SALE point-coordinate and state semantics |
| Min Area Passage/Throat | Pending | Section/flow direction, divergence/angle tolerances, result localization |

F4 also has reference-axis selection/deletion, active-elements-only, airbag reference geometry, scale factor, connected-segment selection, node/element/part/all/segment scope, cancel pick/apply/report, from-state controls, history selection and Plot/New/Padd/Clear/Raise/Pop. Those are separate controls to implement/verify, not automatically covered by the six measurement modes.

## F5/F8 detailed gaps

Identify includes nodes, parts, FE types, curves/surfaces/particles/CNRB/composite entities; supplied XYZ points, fringe value echo, element/material directions, part names, popup/no-ID/echo/airbag options, and separate node/element/part/CNRB/all clear actions. `measure_gui_geometry(...,"coordinates",...)` provides only the checked node-coordinate/Identify subset. Marker creation, persistence and cleanup must receive their own scene checks.

Blank includes entity/type selection, Apply, unblank picked part, auto-apply/auto-update, blank all, unblank all, reverse, update solid outer surfaces/edges and unblank last. Returned “active” status can also be affected by result deletion; visibility and physical erosion must remain distinct. Native Keyword and non-eroding result cases must precede claims about eroding models.

## Command and tutorial conversion

Chapter10 explicitly documents a basic command subset and directs users to recorded `lspost.cfile` for other GUI commands. The guide differentiates `-nographics` (GUI absent but internal graphics required) from `runc=` (no graphics operations). Existing SCL/Python/cfile/raw-command/macro entries remain reusable; their existence does not wrap every panel operation.

Native measurement command layouts were observed, then verified in a synthetic box and representative private result. `measure axes set0` and active-model node tokens are required by the implemented path; earlier malformed/stale-model probes are retained as failures. Wrong command messages now fail validation even when geometry counts remain plausible. Tutorials are converted into reusable operation/state/unit/ID cases and acceptance drivers; retrieved scripts are never executed just because they were found.

Priority: shared measurement/identification/visibility/annotations plus installed release workflows first; then missing common panel operations in the tables. The wider roadmap still includes Model/Mesh/Element/Post menus, geometry/CAD meshing, other versions and headless paths. This audit is an explicit gap list, not a claim of complete F-key coverage.
