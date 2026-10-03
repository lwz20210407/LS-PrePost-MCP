# Common pre/post operations

Read `docs/COMMON_OPERATIONS_COVERAGE.md` for actual F1–F10 mappings and all reviewed panel controls, including items still missing. F-keys are configurable entry points, not completeness evidence.

`measure_gui_geometry` provides native coordinates, node distance/global deltas, two-node axis height,3D3-node/4-node angles and3-point circle radius/center. Units are explicit; keywords use reference geometry, d3plot uses an explicit result state. Targets the active model. Native outputs must match independently checked coordinates and complete preservation readback. Circle centers require a matching native message; collinear points fail. Projected angles remain uninterpreted. The requested state, native overlays and measure axes/scale settings remain; optional PNG is not OCR verification of every label.

Use `set_gui_part_visibility` for part show/hide/isolate/all. `set_gui_entity_visibility` provides standard shell/solid/beam/element hide/show/isolate/reverse and owned `restore_last`, preserving geometry/state/part flags and checking every native display-active flag. None means the whole requested domain, [] an explicit empty scope. Restore checks model/state and touched flags; external changes invalidate it. Node glyphs, special entities and physical erosion masks remain separate gaps.

Full Identify/XYZ annotation lifecycle, local axes, mass/inertia, surface/segment distances and complete histories remain open. Never describe a panel-open command or raw script entry as full internal operation coverage. Measurement and visibility are shared pre/post infrastructure; broaden them from the help/control/command/tutorial matrix, not just a user's examples.
