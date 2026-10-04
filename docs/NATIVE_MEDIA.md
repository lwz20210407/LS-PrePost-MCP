# Native presentation outputs

## Curve PNG and native XY readback

`export_gui_curve_plot(session_id, path, x_column, y_column, title, x_label, y_label, x_unit, y_unit)` renders one pair of explicit CSV columns in a **new native XYPlot window**, then exports PNG and numerical data. It works with an owned keyword or result session and does not overwrite an existing plot. Example engineering mappings:

| Plot | X column / unit | Y column / unit |
|---|---|---|
| Scalar history | `time` / declared model time | `value` / declared quantity unit |
| Force-displacement from tensile tool | `displacement_mm` / `mm` | `force_N` / `N` |
| Engineering stress-strain | `engineering_strain` / `1` | `engineering_stress_MPa` / `MPa` |

Titles and axis labels/units are required, with short printable ASCII labels currently supported. Units are declarations: this tool does not convert data or infer physical meaning. Original row order is retained, including backtracking/hysteresis. Bounds are 2–100,000 samples per curve and fewer than32 existing plot windows. Arbitrary curve operations, publication styling and non-ASCII typography are not included.

## Native multi-curve overlays (2026-10-05)

The existing tool now accepts `curve_label` for the first CSV and `additional_curves`, up to9 records containing exactly `path`, `x_column`, `y_column`, `label`, `x_unit`, `y_unit`. With an overlay, the first label is required and all curve labels must be unique. Axis-unit declarations must match exactly; convert data explicitly before overlaying N with kN, for example. Each curve retains its own X grid, length and row order; no sorting, interpolation or filtering occurs. Aggregate budget:500,000 samples,10 curves. This is an operation budget, not an LS-DYNA model limit.

Implementation ownership: media/engineering, WF-POST and WF-AUTO. One job-specific multi-block XY file is imported and shown as a whole in one new plot. Real GUI recording confirmed `show "file~1" 0` followed by another `show` replaces the displayed curve; it is not an append operation. Native labels use the observed `xyplot ... curvelegend` route. Existing windows are retained; no global file index is guessed.

`native.xy` contains every curve in input order, each with its own point-count header. Every block is checked against the input's float32 representation. `plotted.csv` remains the first curve for backward compatibility; `plotted-2.csv`, etc. hold the others. `data.curves` includes individual source fingerprints, column mappings, labels and numeric checks; `data.numeric_verification` remains the first-curve legacy summary. `curve_count` and `resampled=false` make the multi-curve scope explicit.

Visible4.13.4 acceptance: a previous single curve, then three curves with4/3/5 samples (including backtracking X); recorded replay changes a nested source path and produces4/5/5 samples in a new window. All curves round-trip correctly, labels/axes/PNG were visually checked, previous plot numerical data and source/model files remain unchanged. When two replay curves use the same source they intentionally overlap; the data still contains three curves. Reproducer: `tools/run_multicurve_acceptance.py`. This is synthetic presentation acceptance, not verification of arbitrary solver-derived physical quantities or every curve/style limit.

The native plotted XY values are exported back and checked against the input's **float32 representation**, with an additional relative tolerance of5e-11 for the native text output. XYPlot single precision was observed directly (e.g.0.1 becomes about0.10000000149). Overflow, erased nonzero samples and excessive subnormal rounding are rejected; the original engineering CSV remains unchanged. Metadata records the storage precision and maximum difference. `plotted.csv` contains float32-representable values; `native.xy` preserves the actual native textual output. PNG validation checks a nonblank valid image, not arbitrary physical interpretation or OCR of every label.

Synthetic engineering CSV→stress-strain→PNG and changed-area recorded replay passed in4.13.4; prior plot numerical data remained unchanged. A representative private result also passed native node-history→relative-displacement→PNG, with original state and source hashes preserved. Driver: `tools/run_gui_curve_acceptance.py --workspace <private-directory> --executable <lspp>`; optional `--source <d3plot>` enables that private native extraction check. Reusable four-step recipe: `examples/workflows/visible_gui_relative_displacement_plot.json`.

Source concepts: local standard PyLSPP/SCL Example3 (`open xydata` and `show`), [official XYPlot reference](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/lsdyna_prepost/lspp_ug-fem-post.html), and observed GUI commands for plot titles and axis labels. No local demo script is blindly executed or redistributed.

## Native movie output

`export_gui_animation(session_id, last=None, fps=10, width=1280, height=720)` exports an H264 MP4 through the current owned visible LS-PrePost session. `last=None` means the entire loaded timeline. This is a native movie, not screen recording or a Python-generated replacement.

Current certified scope is **Windows 4.13.4, starting at state 1, increment 1, forward sequence**. The optional last state is inclusive. Arbitrary starts/steps produced an unexpected initial frame and incomplete sequence in native probes; one attempt also timed out. Those modes are deliberately absent from the public tool. GIF/AVI and old versions/headless need separate work.

- Requires `ffprobe` and `ffmpeg` on PATH for independent validation; neither is downloaded, and they do not transcode the result.
- Set explicit integer fps1–60 and even width64–3840/height64–2160. Bounds are at most1800frames and600million pixel-frames; smaller budgets may be needed for complex models.
- Uses the current camera, visibility, fringe and overlays. This does not infer the quantity, units, coordinate frame or shell layer. Frame timestamps are recorded with unspecified model time units; uniform playback fps is not physical real-time scaling.
- Verifies native completion plus the exact ordered state/frame log, H264 codec, decoded frame count, resolution, fps, duration and complete error-free decoding. An existing or partially written file is not success.
- Restores and verifies the original result state and checks model counts/part IDs. Animation is left stopped with first1/last-output/increment1. It does not claim to restore a prior playing animation or its bounds.
- Output, native command/log evidence, model inventory and decode metadata belong to a fresh job directory. Failures preserve evidence and publish no validated video artifact; uncertain native requests are not replayed automatically.

The tool is available through MCP/CLI and GUI workflows, so managed recording and parameter replay include it. A changed `last` parameter produced3then4frames in a recorded replay. A representative private57-state result exported57decodedframes; source-family hashes were unchanged. These are bounded native checks, not certification of all result types or field semantics.

Opt-in reproducible driver: `tools/run_gui_movie_acceptance.py --workspace <private-directory> --executable <lspp-exe> --source <d3plot>`. It launches/maximizes its own GUI and writes all result data only to the caller's private workspace. No private media belongs in Git.

Sources: [official Movie tutorial](https://lsdyna.ansys.com/movie1/), [official file-menu reference](https://lsdyna.ansys.com/file/), plus observed4.13.4 GUI command recording. The UI codec caption contains `H.264`, but the recorded command token is `MP4/H264`. Windows movie output uses native backslash paths; the slash-path/stepped probe is retained as failed evidence, not a certified alternative.

## Named fields, numeric evidence and native fringe PNG

`render_gui_field(session_id, entity_type, field, state, units, integration_point="mid", part_ids=None, color_range=None, averaging="minmax")` uses native SCL arrays for CSV and the custom-fringe source buffer. CSV retains raw entity sampling (`avg_opt=0` on buffer import); **display averaging defaults to the native MinMax option**, separately applied by `range avgfrng minmax`. Explicit `averaging="nodal"` or `"none"` overrides it. Raw CSV values are not averaged display samples. MinMax is an averaging choice, not a color-range policy: omitted bounds still use exported min/max with padding for constant fields, and explicit bounds remain fixed.

Model titles are retained. Result captions use the observed native quantity name (for example `Von Mises stress`), without generated unit/entity/layer/average suffixes. Derived mean stress and geometry quantities have plain declared names, not fictional native names. Units, sampling and averaging stay in metadata. `export_gui_animation` and `render_snapshot` also default to MinMax and preserve model/result titles; `set_gui_display(averaging=...)` explicitly changes the current setting and otherwise retains it.

The named-field route isolates matching/requested parts, stops animation, clears general selection overlays and retains the requested scene. Units are declarations, not conversions. Native 4.13.4 presentation regression checks the actual Fringe Range combo (`MinMax`/`None`), identical raw CSV under those two display settings, plain names in rendered PNG, recorded replay and a decoded three-frame MP4. The MinMax nodal calculation has not been independently reimplemented or certified numerically. Driver: `tools/run_fringe_presentation_acceptance.py`.

Native checks cover solid Mises, mean stress, pressure (negative mean normal stress), and node displacement magnitude computed from all three components; state changes, fixed-range recording replay and a two-state custom-field movie passed. A private model exceeding300,000 solid elements also passed full-domain Mises export and independent native six-component spot checks. Original files were unchanged. Native field validation is separate from whole-mesh edit validation.

The optional `results` extra supplies pinned LASSO2.0.4 **header validation only**: native/header entity counts and field availability flags must agree. Numeric values come from LS-PrePost. An incompatible old header is rejected without claiming that its fields are absent. Recorded point count and native full-integration status guard explicit solid point requests; reduced/default solids use selector0. Area/volume/thickness/energy density have element-scalar semantics, not shell-layer labels. Mises agreement uses component-scale float32 tolerance, including small unit systems.

Native-tested nontrivial layer semantics do not yet cover shell/tshell. File-level flags do not establish validity for each rigid/deleted/material-specific entity. Nodal selection follows display-active element connectivity; screen occlusion and cutting planes do not filter the CSV. The current field guard is one million model entities and one million retained custom-fringe scalar samples, with5,000parts; these are resource guards, not certification at those sizes. Reopening clears retained custom buffers.

For movies after custom rendering, every output state must have a verified, consistent field definition. Missing states, a raw display change or changed part/selection scope cause rejection. Per-state producer evidence and the final color range are recorded; uniform color bounds should be supplied when comparing frames. This is coverage validation, not independent dimensional/physical certification.

Drivers: `tools/run_gui_fringe_acceptance.py` for native field/replay/movie checks; `tools/run_mesh_page_acceptance.py` for a solid-only private keyword/result pair, paged reference mesh checks and large native field export. Both require explicit private output directories. Recipe: `examples/workflows/visible_gui_named_fringe.json`. Broader curve windows and physical validity remain in the [delivery plan](DELIVERY_PLAN.md).

## Solid point regression (2026-10-04)

Physical-field animation has a separate [native PNG + FFmpeg sequence contract](FIELD_MOVIES.md), with per-state deletion checks and explicit encoder provenance. It does not replace the native Movie-command interface.

The public mixed solid/shell fixture showed native SCL returning the point-1 tensor for a point-8 request despite positive full-integration status. Shared sampling validation now rejects native solid selectors2..8 before field or image dispatch. The earlier header guard was necessary but insufficient; it did not verify actual point selection. Default/point1 and shell selections retain their separate scope. See [evidence and remaining adapter work](RESULT_VALIDITY.md).
