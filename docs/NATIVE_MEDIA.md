# Native presentation outputs

## Curve PNG and native XY readback

`export_gui_curve_plot(session_id, path, x_column, y_column, title, x_label, y_label, x_unit, y_unit)` renders one pair of explicit CSV columns in a **new native XYPlot window**, then exports PNG and numerical data. It works with an owned keyword or result session and does not overwrite an existing plot. Example engineering mappings:

| Plot | X column / unit | Y column / unit |
|---|---|---|
| Scalar history | `time` / declared model time | `value` / declared quantity unit |
| Force-displacement from tensile tool | `displacement_mm` / `mm` | `force_N` / `N` |
| Engineering stress-strain | `engineering_strain` / `1` | `engineering_stress_MPa` / `MPa` |

Titles and axis labels/units are required, with short printable ASCII labels currently supported. Units are declarations: this tool does not convert data or infer physical meaning. Original row order is retained, including backtracking/hysteresis. Bounds are 2–100,000 samples and fewer than32 existing plot windows. Multi-curve overlays, arbitrary curve operations, publication styling and non-ASCII typography are not included.

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

Broader curve-window functionality and field-aware cloud-plot output remain core tasks in the [delivery plan](DELIVERY_PLAN.md).
